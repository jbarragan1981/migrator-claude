"""Caso de uso `convert` (spec 05): del export al árbol Markdown de la salida.

Orquesta `parse → render → write` para las CINCO categorías del export (`memories` y
`conversations` desde M1; `light_metadata`, `projects` y `frames` desde M2), de modo que
el árbol de salida es ya el de CLAUDE.md §5. Una categoría que el export no traiga no
genera una carpeta vacía: simplemente no aparece, y el README generado solo enumera lo
que de verdad se escribió.

Decisiones de este módulo:

* **Nada de I/O propio.** Cada byte que se escribe pasa por el puerto `MarkdownSink`
  (ADR-0006), que quien llama inyecta: `FilesystemSink` desde el CLI, un `ZipSink` en
  M3, un doble en los tests. El caso de uso no sabe si detrás hay un disco; solo sabe
  qué ruta relativa le corresponde a cada texto, y el texto lo arma `rendering/`.
* **Un solo `Report` para toda la corrida.** Los dos parsers acumulan en él sus errores,
  advertencias y conteos; un ítem ilegible nunca detiene la conversión (CLAUDE.md §1.3)
  y acaba como una línea de `_report/errors.jsonl`.
* **El orden de las categorías no es casual.** Los proyectos se parsean ANTES que las
  conversaciones (son 32 archivos pequeños y caben enteros en memoria) para que cada
  conversación pueda nombrar su proyecto mientras se escribe; y se ESCRIBEN después,
  porque su `project.md` enumera las conversaciones que lo referencian y esa lista solo
  está completa cuando terminó el streaming. El cruce vive en `usecases/links.py`
  (spec 03, projects CA-4); si un `project_uuid` no resuelve, la conversación se escribe
  igual con su uuid crudo y la corrida deja UNA advertencia agregada.
* **Conversaciones en streaming.** Se usa `conversations_parser.parse` (perezoso), no
  `parse_sorted`: lo único que se retiene en memoria es una fila diminuta por
  conversación para el `_index.md`, que se ordena al final. El orden de ESCRITURA no
  importa porque la ruta de cada archivo depende solo de su propia conversación, salvo
  cuando dos quieren la misma: ahí `ConversationPaths` desempata y avisa, en vez de
  dejar que la segunda pise a la primera.
* **Determinismo (CLAUDE.md §1.4).** No se llama al reloj en ningún momento. La única
  fecha de la salida que no sale de un ítem es la del manifiesto (cuándo generó
  Anthropic el export), y si no hay manifiesto simplemente no se imprime.
* **El inventario se guarda con la salida.** `_report/inventory.json` deja constancia de
  qué traía el export que se convirtió, y sus advertencias (categorías ausentes, partes
  que faltan) entran en el `Report` de la corrida en vez de perderse.
* **Progreso: un `Callable`, todavía no un puerto.** Ver ADR-0006, sección
  "`ProgressReporter`: todavía no".
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import Environment

from claude_export_md.adapters.parsers import conversations as conversations_parser
from claude_export_md.adapters.parsers import frames as frames_parser
from claude_export_md.adapters.parsers import light_metadata as light_metadata_parser
from claude_export_md.adapters.parsers import memories as memories_parser
from claude_export_md.adapters.parsers import projects as projects_parser
from claude_export_md.adapters.sink_json import dumps_errors, dumps_inventory, dumps_summary
from claude_export_md.domain.dates import parse_timestamp
from claude_export_md.domain.entities import (
    Account,
    Conversation,
    Frame,
    Memory,
    ParseError,
    Report,
)
from claude_export_md.domain.inventory import Inventory
from claude_export_md.errors import CorruptFileError
from claude_export_md.ports.sink import MarkdownSink
from claude_export_md.ports.source import ExportSource
from claude_export_md.rendering.conversations import ConversationPaths, render_conversation
from claude_export_md.rendering.filters import iso_utc
from claude_export_md.rendering.index import (
    ERRORS_PATH,
    INDEX_NAME,
    INVENTORY_PATH,
    README_NAME,
    SUMMARY_PATH,
    IndexEntry,
    account_entry,
    conversation_entry,
    frame_entry,
    memory_entry,
    project_entry,
    render_index,
    render_readme,
)
from claude_export_md.rendering.render import (
    account_path_warnings,
    assign_account_paths,
    assign_frame_paths,
    assign_output_paths,
    build_environment,
    project_output_path,
    render_account,
    render_frame,
    render_memory,
    render_project,
)
from claude_export_md.usecases.inventory import build_inventory
from claude_export_md.usecases.links import ProjectLinker

logger = logging.getLogger(__name__)

#: Categorías que esta versión sabe convertir, en el orden en que se convierten.
CONVERTED_CATEGORIES = (
    memories_parser.CATEGORY,
    light_metadata_parser.CATEGORY,
    projects_parser.CATEGORY,
    conversations_parser.CATEGORY,
    frames_parser.CATEGORY,
)

#: Clave del manifiesto que dice cuándo generó Anthropic el export.
MANIFEST_CREATED_AT = "created_at"

#: `(categoría, ítems procesados hasta ahora)`. Lo usa el CLI para su barra de progreso;
#: el núcleo no sabe nada de consolas ni de barras.
ProgressCallback = Callable[[str, int], None]


@dataclass(frozen=True, slots=True)
class ConvertResult:
    """Qué produjo la conversión. Todo lo interesante para el CLI y para la API."""

    #: `MarkdownSink.location`: la carpeta, el zip… donde quedó el árbol.
    destination: str
    report: Report
    inventory: Inventory
    #: Rutas escritas, relativas a la raíz del sink y en formato POSIX.
    files: tuple[str, ...]
    export_created_at: str | None = None

    @property
    def counts(self) -> dict[str, int]:
        """Ítems convertidos por categoría."""
        return dict(sorted(self.report.counts.items()))

    @property
    def error_count(self) -> int:
        return len(self.report.errors)

    @property
    def warning_count(self) -> int:
        return len(self.report.warnings)

    @property
    def errors_file(self) -> str:
        """Dónde quedó el detalle de los ítems que no se pudieron parsear."""
        return ERRORS_PATH


def export_created_at(source: ExportSource) -> str | None:
    """Cuándo generó Anthropic el export, según el manifiesto; `None` si no se sabe.

    Es la única fecha "de la corrida" admisible en la salida (CLAUDE.md §5): describe el
    export, no el momento en que se ejecutó la herramienta. Un manifiesto ausente o
    ilegible no es un error: simplemente no hay fecha que mostrar.
    """
    try:
        manifest = source.manifest()
    except CorruptFileError:
        return None
    if manifest is None:
        return None
    parsed, _assumed = parse_timestamp((manifest.model_extra or {}).get(MANIFEST_CREATED_AT))
    return iso_utc(parsed)


def convert(
    source: ExportSource,
    sink: MarkdownSink,
    templates: Path | str | None = None,
    overwrite: bool = False,
    progress: ProgressCallback | None = None,
) -> ConvertResult:
    """Convierte el export y lo escribe en `sink`; devuelve qué pasó.

    Lanza `UnknownFormatError` si el origen no parece un export de Claude.ai y
    `OutputNotEmptyError` si el destino ya tiene contenido y no se pidió `overwrite`
    (spec 05 CA-3); en ese caso no se escribe absolutamente nada. Cualquier otro
    problema es de un ítem concreto y viaja en `ConvertResult.report`.
    """
    sink.ensure_writable(overwrite)
    # Antes que nada: si no se reconoce el formato, esto lanza y no se escribe nada.
    inventory = build_inventory(source)
    report = Report()
    for warning in inventory.warnings:
        report.add_warning(warning)
    environment = build_environment(templates)
    files: list[str] = []

    # Las rutas de las memorias se reparten una sola vez: las usan el sink y el índice.
    memories = assign_output_paths(
        _collect(memories_parser.parse(source, report), memories_parser.CATEGORY, progress)
    )
    files.extend(_write_memories(memories, sink, environment))

    accounts = assign_account_paths(
        _collect(
            light_metadata_parser.parse(source, report), light_metadata_parser.CATEGORY, progress
        )
    )
    files.extend(_write_accounts(accounts, sink, environment, report))

    # Los proyectos se parsean ANTES que las conversaciones (para poder nombrarlos en
    # cada una) y se escriben DESPUÉS (para enumerar las que apuntan a cada proyecto).
    linker = ProjectLinker(
        sorted(
            _collect(projects_parser.parse(source, report), projects_parser.CATEGORY, progress),
            key=projects_parser.sort_key,
        )
    )

    entries: list[IndexEntry] = []
    files.extend(
        _write_conversations(
            conversations_parser.parse(source, report),
            sink,
            environment,
            report,
            entries,
            linker,
            progress,
        )
    )

    project_entries: list[IndexEntry] = []
    files.extend(_write_projects(linker, sink, environment, project_entries))
    for warning in linker.warnings:
        report.add_warning(warning)

    frames = assign_frame_paths(
        sorted(
            _collect(frames_parser.parse(source, report), frames_parser.CATEGORY, progress),
            key=frames_parser.sort_key,
        )
    )
    files.extend(_write_frames(frames, sink, environment))

    created_at = export_created_at(source)
    sink.write(
        INDEX_NAME,
        render_index(
            conversations=entries,
            memories=[
                # Las memorias de proyecto (ADR-0005) también saben a quién pertenecen.
                memory_entry(memory, path, linker.link(memory.project_id))
                for memory, path in memories
            ],
            projects=project_entries,
            frames=[frame_entry(frame, path) for frame, path in frames],
            accounts=[account_entry(account, path) for account, path in accounts],
            environment=environment,
        ),
    )
    files.append(INDEX_NAME)
    sink.write(
        README_NAME,
        render_readme(
            source=inventory.root,
            format_version=inventory.format_version,
            counts=dict(report.counts),
            export_created_at=created_at,
            missing_categories=inventory.missing_categories,
            environment=environment,
        ),
    )
    files.append(README_NAME)
    files.extend(
        _write_report(sink, _summary(inventory, report, created_at), report.errors, inventory)
    )
    logger.info(
        "Conversión terminada: %d archivos, %d ítems con error", len(files), len(report.errors)
    )
    return ConvertResult(
        destination=sink.location,
        report=report,
        inventory=inventory,
        files=tuple(files),
        export_created_at=created_at,
    )


# --------------------------------------------------------------- render → sink


def _write_memories(
    memories: Sequence[tuple[Memory, str]],
    sink: MarkdownSink,
    environment: Environment | None = None,
) -> list[str]:
    """Escribe `memories/…` y devuelve las rutas, en orden de escritura.

    Recibe las memorias con su ruta ya asignada por
    `rendering.render.assign_output_paths`: depende solo de `Memory.path`, nunca del
    orden ni del momento de la corrida.
    """
    env = environment if environment is not None else build_environment()
    written: list[str] = []
    for memory, path in memories:
        sink.write(path, render_memory(memory, env))
        written.append(path)
    logger.info("Memorias escritas: %d", len(written))
    return written


def _write_accounts(
    accounts: Sequence[tuple[Account, str]],
    sink: MarkdownSink,
    environment: Environment | None,
    report: Report,
) -> list[str]:
    """Escribe `account/account.md` (spec 04) y devuelve las rutas.

    Con más de una cuenta ninguna se queda la ruta fija y queda dicho en el `Report`
    (ver las decisiones de `rendering/render.py`).
    """
    env = environment if environment is not None else build_environment()
    written: list[str] = []
    for account, path in accounts:
        sink.write(path, render_account(account, env))
        written.append(path)
    for warning in account_path_warnings([account for account, _path in accounts]):
        report.add_warning(warning)
    logger.info("Cuentas escritas: %d", len(written))
    return written


def _write_projects(
    linker: ProjectLinker,
    sink: MarkdownSink,
    environment: Environment | None,
    entries: list[IndexEntry],
) -> list[str]:
    """Escribe `projects/<slug>/{project.md,docs/…}` y anota el índice.

    Se llama cuando ya pasaron todas las conversaciones: solo entonces el `project.md`
    puede enumerar las que apuntan a él (spec 03, projects CA-4).
    """
    env = environment if environment is not None else build_environment()
    written: list[str] = []
    for resolved in linker.resolved():
        for path, markdown in render_project(
            resolved.project, env, resolved.directory, resolved.conversations
        ):
            sink.write(path, markdown)
            written.append(path)
        entries.append(
            project_entry(
                resolved.project, project_output_path(resolved.project, resolved.directory)
            )
        )
    logger.info("Proyectos escritos: %d archivos", len(written))
    return written


def _write_frames(
    frames: Sequence[tuple[Frame, str]],
    sink: MarkdownSink,
    environment: Environment | None,
) -> list[str]:
    """Escribe `frames/<slug>.md` y devuelve las rutas, en orden de escritura."""
    env = environment if environment is not None else build_environment()
    written: list[str] = []
    for frame, path in frames:
        sink.write(path, render_frame(frame, env))
        written.append(path)
    logger.info("Artefactos escritos: %d", len(written))
    return written


def _write_conversations(
    conversations: Iterable[Conversation],
    sink: MarkdownSink,
    environment: Environment | None,
    report: Report,
    entries: list[IndexEntry],
    linker: ProjectLinker,
    progress: ProgressCallback | None = None,
) -> list[str]:
    """Escribe `conversations/YYYY/MM/…` a medida que se parsean y anota el índice.

    Consume el parseo de forma perezosa (una conversación a la vez) para que convertir
    un export de ~98 MB no exija tener los 291 Markdown en memoria: de cada una solo
    sobrevive su fila diminuta del `_index.md`, en `entries`. Detrás de cada `.md` van
    sus artefactos extraídos (spec 04 CA-5), en
    `<mismo nombre sin .md>/artifacts/NN-<nombre>.<ext>`.
    """
    env = environment if environment is not None else build_environment()
    paths = ConversationPaths()
    written: list[str] = []
    for conversation in conversations:
        path = paths.assign(conversation)
        # El cruce se hace con la ruta YA asignada: el `project.md` tiene que enlazar el
        # archivo que de verdad se escribió, no la ruta natural sin desempatar.
        project = linker.record(conversation, path)
        entries.append(conversation_entry(conversation, path, project))
        rendered = render_conversation(conversation, env, path, project)
        sink.write(rendered.path, rendered.markdown)
        written.append(rendered.path)
        for artifact in rendered.artifacts:
            sink.write(artifact.path, artifact.content)
            written.append(artifact.path)
        _emit(progress, conversations_parser.CATEGORY, len(entries))
    _emit(progress, conversations_parser.CATEGORY, len(entries))
    for warning in paths.warnings:
        report.add_warning(warning)
    logger.info("Conversaciones escritas: %d archivos", len(written))
    return written


def _write_report(
    sink: MarkdownSink,
    summary: Mapping[str, Any],
    errors: Iterable[ParseError] = (),
    inventory: Inventory | None = None,
) -> list[str]:
    """Escribe `_report/{summary.json, errors.jsonl, inventory.json}` (spec 04 CA-8).

    `errors.jsonl` se escribe siempre, aunque esté vacío: así el árbol de salida tiene
    la misma forma haya habido problemas o no, y el mensaje del CLI puede apuntar a un
    archivo que existe.
    """
    written = [
        (SUMMARY_PATH, dumps_summary(summary)),
        (ERRORS_PATH, dumps_errors(errors)),
    ]
    if inventory is not None:
        written.append((INVENTORY_PATH, dumps_inventory(inventory)))
    for path, content in written:
        sink.write(path, content)
    return [path for path, _content in written]


# ------------------------------------------------------------------- auxiliares


def _emit(progress: ProgressCallback | None, category: str, done: int) -> None:
    if progress is not None:
        progress(category, done)


def _collect[T](
    items: Iterable[T], category: str, progress: ProgressCallback | None = None
) -> list[T]:
    """Consume un parser entero informando del progreso y devuelve sus ítems.

    Se usa con las categorías pequeñas (memorias, cuentas, proyectos y artefactos), que
    caben en memoria y hacen falta completas: para desempatar rutas, para cruzar las
    conversaciones con su proyecto y para ordenarlas canónicamente. Las conversaciones,
    que son el archivo grande, NO pasan por aquí: se escriben en streaming.
    """
    collected: list[T] = []
    for item in items:
        collected.append(item)
        _emit(progress, category, len(collected))
    _emit(progress, category, len(collected))
    return collected


def _summary(inventory: Inventory, report: Report, created_at: str | None) -> dict[str, Any]:
    """Contenido de `_report/summary.json` (spec 04 CA-8).

    Lleva los conteos por categoría y el número de errores, que es lo que pide el spec,
    más el contexto mínimo para saber qué export se convirtió. Las advertencias van
    enteras (no solo contadas): son pocas y son lo que el usuario necesita leer cuando
    algo salió raro pero la corrida terminó bien.
    """
    return {
        "categories": dict(sorted(report.counts.items())),
        "converted_categories": list(CONVERTED_CATEGORIES),
        "error_count": len(report.errors),
        "errors_file": ERRORS_PATH,
        "export_created_at": created_at,
        "format_version": inventory.format_version,
        "missing_categories": list(inventory.missing_categories),
        "source": inventory.root,
        "warning_count": len(report.warnings),
        "warnings": list(report.warnings),
    }


__all__ = [
    "CONVERTED_CATEGORIES",
    "MANIFEST_CREATED_AT",
    "ConvertResult",
    "ProgressCallback",
    "convert",
    "export_created_at",
]

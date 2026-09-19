"""Render de una `Conversation` a Markdown (spec 04, CA-1..CA-6, CA-9, CA-10).

Módulo puro: arma texto, no escribe nada (eso es `adapters/sink_filesystem.py`) y no
mira el reloj (CA-10). Reutiliza el entorno Jinja2 y los filtros comunes de
`rendering/render.py` y `rendering/filters.py`, que nacieron con `memories`.

Decisiones que el export no trae resueltas:

* **Nombre del archivo** — `conversations/YYYY/MM/YYYY-MM-DD_<slug>_<uuid8>.md`
  (CLAUDE.md §5). La fecha es `created_at` y, si falta, `updated_at`; si no hay ninguna
  no se inventa una: la conversación va a `conversations/sin-fecha/<slug>_<uuid8>.md`.
  El `uuid8` son los 8 primeros caracteres alfanuméricos del `uuid`; si el identificador
  fuera más corto se usa un hash corto y estable, para que siempre haya desempate.
  Dos conversaciones pueden aun así querer el mismo archivo (mismo día, mismo título y
  mismos 8 caracteres): de eso se ocupa `ConversationPaths`, que le da a la segunda el
  hash corto de su `id` y deja una advertencia. Nunca se sobrescribe en silencio
  (CLAUDE.md §1.3).
* **Título** — `name` puede venir vacío (spec 03 CA-4). El frontmatter muestra entonces
  `Conversación sin título`, y el slug del archivo cae en `sin-titulo`; el valor
  original (`""`) no se pierde porque no hay nada que perder.
* **Turnos** — un `##` por mensaje con emoji y hora `HH:MM` en UTC (CA-3). Los bloques
  de texto se insertan tal cual (ya son Markdown); `thinking`, `tool_use`, `tool_result`
  y cualquier tipo que no conozcamos van dentro de `<details>` para no ensuciar la
  lectura (CA-4, regla 6 del skill).
* **Qué se ve de un bloque no textual** — lo legible primero (el razonamiento, la
  entrada de la herramienta, el texto del resultado) y después sus metadatos como JSON.
  De los metadatos se quitan las claves de primer nivel que valen `null`, que en el
  export real son la mayoría (integraciones y MCP sin usar) y no dicen nada: el bloque
  completo sigue íntegro en `ContentBlock.payload`, que es el dominio; el `.md` es una
  vista. Lo que NO se poda es el interior de `input`/`display_content`, que son de
  esquema libre (spec 03 CA-3).
* **Campos desconocidos** — los de la conversación van bajo `extra:` en el frontmatter
  (CA-C4). Los de un mensaje (`parent_message_uuid`, …) no se imprimen, pero la
  plantilla recibe la entidad entera en `turn.message` por si alguien los quiere.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any

from jinja2 import Environment

from claude_export_md.domain.entities import (
    BLOCK_TEXT,
    BLOCK_THINKING,
    BLOCK_TOOL_RESULT,
    BLOCK_TOOL_USE,
    SENDER_ASSISTANT,
    SENDER_HUMAN,
    ContentBlock,
    Conversation,
    Message,
)
from claude_export_md.rendering.artifacts import ARTIFACTS_DIR, ArtifactCollector
from claude_export_md.rendering.filters import (
    code_fence,
    hhmm,
    iso_utc,
    jsonable,
    short_hash,
    slugify,
)
from claude_export_md.rendering.links import ProjectLink, relative_link
from claude_export_md.rendering.render import MARKDOWN_SUFFIX, build_environment

#: Plantilla y `type` de frontmatter de una conversación.
CONVERSATION_TEMPLATE = "conversation.md.j2"
TYPE_CONVERSATION = "conversation"

#: Carpetas de la salida (CLAUDE.md §5).
CONVERSATIONS_DIR = "conversations"
#: Dónde van las conversaciones que el export trajo sin ninguna fecha.
UNDATED_DIR = "sin-fecha"

#: Título de una conversación a la que el usuario nunca le puso nombre.
UNTITLED = "Conversación sin título"

#: Advertencia de dos conversaciones que querían el mismo archivo (ver `ConversationPaths`).
COLLISION_WARNING = (
    "Dos conversaciones querían escribir {wanted}; la del uuid {id} se guardó como "
    "{path} para no pisar a la anterior"
)

#: Etiquetas del frontmatter.
TAG_CONVERSATION = "conversation"
TAG_PROJECT = "project"

#: Encabezado de cada turno (spec 04 CA-3).
HEADING_HUMAN = "👤 Usuario"
HEADING_ASSISTANT = "🤖 Claude"
HEADING_UNKNOWN = "💬 Mensaje"
HEADING_OTHER = "💬 {sender}"
HEADING_SEPARATOR = " — "

#: Resumen visible de cada `<details>`, por tipo de bloque.
SUMMARY_THINKING = "🧠 Razonamiento"
SUMMARY_TOOL_USE = "🔧 Uso de herramienta"
SUMMARY_TOOL_RESULT = "📋 Resultado"
SUMMARY_UNKNOWN = "❓ Bloque"
SUMMARY_ERROR = " (error)"

#: Etiquetas de las secciones dentro de un `<details>`.
LABEL_SUMMARIES = "**Resumen**"
LABEL_INPUT = "**Entrada**"
LABEL_OUTPUT = "**Salida**"
LABEL_METADATA = "**Metadatos**"
LABEL_CONTENT = "**Contenido**"

#: Campo de `extra` que pone el parser y que en el frontmatter va al primer nivel.
SOURCE_FILE_KEY = "source_file"

#: Claves de cada tipo de bloque que se muestran aparte y no repiten en los metadatos.
_THINKING_KEYS = frozenset({"thinking", "summaries"})
_TOOL_USE_KEYS = frozenset({"input", "message", "name"})
_TOOL_RESULT_KEYS = frozenset({"content", "name"})

_NON_ALNUM = re.compile(r"[^a-z0-9]")
#: Longitud del `uuid8` del nombre de archivo (skill `markdown-template`, regla 3).
UUID8_LENGTH = 8

_PART_SEPARATOR = "\n\n"


# ------------------------------------------------------------- resultado


@dataclass(frozen=True, slots=True)
class RenderedFile:
    """Un archivo listo para escribir, con su ruta relativa a la raíz de la salida."""

    path: str
    content: str


@dataclass(frozen=True, slots=True)
class RenderedConversation:
    """El `.md` de una conversación y los artefactos que se le extrajeron (CA-5)."""

    path: str
    markdown: str
    artifacts: tuple[RenderedFile, ...] = ()


# --------------------------------------------------------- título y ruta


def conversation_title(conversation: Conversation) -> str:
    """Título legible; `name` vacío o ausente se muestra como `Conversación sin título`."""
    title = (conversation.title or "").strip()
    return title or UNTITLED


def _uuid8(identifier: str) -> str:
    """Los 8 primeros caracteres alfanuméricos del uuid, o un hash corto si no llegan."""
    compact = _NON_ALNUM.sub("", identifier.lower())
    return compact[:UUID8_LENGTH] if len(compact) >= UUID8_LENGTH else short_hash(identifier)


def conversation_date(conversation: Conversation) -> datetime | None:
    """Fecha con la que se archiva la conversación: creación y, si falta, actualización."""
    when = conversation.created_at or conversation.updated_at
    return when.astimezone(UTC) if when is not None else None


def conversation_stem(conversation: Conversation) -> str:
    """`YYYY-MM-DD_<slug>_<uuid8>` (sin la fecha si el export no trajo ninguna)."""
    # Se slugifica el `name` del export, no el título de respaldo: un `name` vacío cae
    # en `sin-titulo` (el fallback de `slugify`) en vez de repetir la frase entera.
    slug = slugify(conversation.title or "")
    name = f"{slug}_{_uuid8(conversation.id)}"
    when = conversation_date(conversation)
    return name if when is None else f"{when:%Y-%m-%d}_{name}"


def conversation_output_path(conversation: Conversation) -> str:
    """Ruta del `.md` relativa a la raíz de la salida (CLAUDE.md §5)."""
    stem = conversation_stem(conversation)
    when = conversation_date(conversation)
    folder = UNDATED_DIR if when is None else f"{when:%Y}/{when:%m}"
    return f"{CONVERSATIONS_DIR}/{folder}/{stem}{MARKDOWN_SUFFIX}"


class ConversationPaths:
    """Reparte las rutas de salida sin que dos conversaciones se pisen en disco.

    Dos conversaciones del mismo día, con el mismo título y con los mismos 8 primeros
    caracteres alfanuméricos del `uuid` producen la MISMA ruta. Sin desempate la
    segunda sobrescribía a la primera en silencio, que es justo lo que CLAUDE.md §1.3
    prohíbe.

    A diferencia de las memorias (`render.assign_output_paths`, que ve la colección
    entera y le da el hash a AMBAS), las conversaciones se escriben en streaming
    (CLAUDE.md §4): no se pueden contar las colisiones de antemano sin juntar las ~291
    conversaciones en memoria. Por eso el desempate es incremental: la primera que
    reclama una ruta se la queda y las siguientes reciben el hash corto de su `id`
    (más un contador si hasta el `id` estaba repetido). Sigue siendo determinista
    porque el orden de lectura del export lo es, y cada colisión deja una advertencia
    en `warnings` para que el `Report` de la corrida la cuente.
    """

    def __init__(self) -> None:
        self._taken: set[str] = set()
        #: Una línea por colisión, lista para `Report.add_warning`.
        self.warnings: list[str] = []

    def assign(self, conversation: Conversation) -> str:
        """Ruta definitiva de la conversación, ya libre de colisiones."""
        wanted = conversation_output_path(conversation)
        if wanted not in self._taken:
            self._taken.add(wanted)
            return wanted
        path = self._free_name(wanted, conversation.id)
        self.warnings.append(COLLISION_WARNING.format(wanted=wanted, id=conversation.id, path=path))
        self._taken.add(path)
        return path

    def _free_name(self, wanted: str, identifier: str) -> str:
        stem = wanted.removesuffix(MARKDOWN_SUFFIX)
        candidate = f"{stem}-{short_hash(identifier)}{MARKDOWN_SUFFIX}"
        attempt = 2
        # Solo hace falta si el export trae el MISMO uuid dos veces: el hash coincide.
        while candidate in self._taken:
            candidate = f"{stem}-{short_hash(identifier)}-{attempt}{MARKDOWN_SUFFIX}"
            attempt += 1
        return candidate


def conversation_tags(conversation: Conversation) -> list[str]:
    tags = [TAG_CONVERSATION]
    if conversation.project_id:
        tags.append(TAG_PROJECT)
    return tags


# ------------------------------------------------------------------ turnos


def message_heading(message: Message) -> str:
    """`👤 Usuario — 14:32` (sin hora si el mensaje no trae fecha)."""
    label = _sender_label(message.sender)
    time = hhmm(message.created_at)
    return f"{label}{HEADING_SEPARATOR}{time}" if time else label


def _sender_label(sender: str | None) -> str:
    if sender == SENDER_HUMAN:
        return HEADING_HUMAN
    if sender == SENDER_ASSISTANT:
        return HEADING_ASSISTANT
    if sender:
        return HEADING_OTHER.format(sender=sender)
    return HEADING_UNKNOWN


def _json_block(value: Any) -> str:  # noqa: ANN401 - payload de esquema libre
    """Un valor del export como bloque JSON, siempre con las claves ordenadas (CA-1)."""
    dumped = json.dumps(jsonable(value), ensure_ascii=False, indent=2, sort_keys=True, default=str)
    return code_fence(dumped, "json")


def _without_nulls(payload: dict[str, Any], shown: frozenset[str]) -> dict[str, Any]:
    """Metadatos que quedan por mostrar: sin lo ya visible y sin los `null` de primer nivel."""
    return {
        key: value
        for key, value in sorted(payload.items())
        if key not in shown and value is not None
    }


def _sections(*parts: str) -> str:
    return _PART_SEPARATOR.join(part for part in parts if part)


def _labelled(label: str, value: Any) -> str:  # noqa: ANN401 - payload de esquema libre
    return f"{label}\n\n{_json_block(value)}" if value else ""


def _thinking_part(block: ContentBlock) -> dict[str, str]:
    summaries = [
        item["summary"]
        for item in block.payload.get("summaries") or []
        if isinstance(item, dict) and isinstance(item.get("summary"), str)
    ]
    listed = "\n".join(f"- {summary}" for summary in summaries)
    thinking = block.payload.get("thinking")
    return {
        "kind": block.type,
        "summary": SUMMARY_THINKING,
        "body": _sections(
            f"{LABEL_SUMMARIES}\n\n{listed}" if listed else "",
            thinking.strip() if isinstance(thinking, str) else "",
            _labelled(LABEL_METADATA, _without_nulls(block.payload, _THINKING_KEYS)),
        ),
    }


def _tool_use_part(block: ContentBlock) -> dict[str, str]:
    name = block.payload.get("name")
    message = block.payload.get("message")
    return {
        "kind": block.type,
        "summary": _with_name(SUMMARY_TOOL_USE, name, prefix=": "),
        "body": _sections(
            message.strip() if isinstance(message, str) else "",
            _labelled(LABEL_INPUT, block.payload.get("input")),
            _labelled(LABEL_METADATA, _without_nulls(block.payload, _TOOL_USE_KEYS)),
        ),
    }


def _tool_result_part(block: ContentBlock) -> dict[str, str]:
    name = block.payload.get("name")
    summary = _with_name(SUMMARY_TOOL_RESULT, name, prefix=" de ")
    if block.payload.get("is_error"):
        summary += SUMMARY_ERROR
    output = "\n\n".join(
        item["text"]
        for item in block.payload.get("content") or []
        if isinstance(item, dict) and isinstance(item.get("text"), str) and item["text"]
    )
    return {
        "kind": block.type,
        "summary": summary,
        "body": _sections(
            f"{LABEL_OUTPUT}\n\n{code_fence(output)}" if output else "",
            _labelled(LABEL_METADATA, _without_nulls(block.payload, _TOOL_RESULT_KEYS)),
        ),
    }


def _unknown_part(block: ContentBlock) -> dict[str, str]:
    """Un tipo de bloque que no conocemos se ve entero, no se descarta (CLAUDE.md §1.3)."""
    return {
        "kind": block.type,
        "summary": f"{SUMMARY_UNKNOWN} <code>{block.type}</code>",
        "body": _labelled(LABEL_CONTENT, _without_nulls(block.payload, frozenset()))
        or LABEL_CONTENT,
    }


def _with_name(label: str, name: Any, prefix: str) -> str:  # noqa: ANN401 - valor del export
    return f"{label}{prefix}<code>{name}</code>" if isinstance(name, str) and name else label


def _parts(message: Message, collector: ArtifactCollector) -> list[dict[str, str]]:
    """Los bloques del mensaje como partes renderizables, en el orden del export (CA-1)."""
    if not message.blocks:
        text = message.text.strip()
        return [{"kind": BLOCK_TEXT, "text": collector.extract(text)}] if text else []
    parts: list[dict[str, str]] = []
    for block in message.blocks:
        if block.type == BLOCK_TEXT:
            text = block.text.strip()
            if text:
                parts.append({"kind": BLOCK_TEXT, "text": collector.extract(text)})
        elif block.type == BLOCK_THINKING:
            parts.append(_thinking_part(block))
        elif block.type == BLOCK_TOOL_USE:
            parts.append(_tool_use_part(block))
        elif block.type == BLOCK_TOOL_RESULT:
            parts.append(_tool_result_part(block))
        else:
            parts.append(_unknown_part(block))
    return parts


# ------------------------------------------------------------------ render


def conversation_context(
    conversation: Conversation,
    collector: ArtifactCollector,
    project: ProjectLink | None = None,
    path: str | None = None,
) -> dict[str, Any]:
    """Variables que ve `conversation.md.j2` (documentadas en la propia plantilla).

    `project` es el proyecto ya resuelto por `usecases/links.py` (spec 03, projects
    CA-4) y `path`, la ruta de ESTE archivo, necesaria para calcular el enlace relativo
    hasta el `project.md`. Sin proyecto resuelto solo queda el `project_id` crudo, que es
    lo que trae el export.
    """
    extra = dict(conversation.model_extra or {})
    source_file = extra.pop(SOURCE_FILE_KEY, None)
    turns = [
        {
            "heading": message_heading(message),
            "message": message,
            "parts": _parts(message, collector),
        }
        for message in conversation.messages
    ]
    return {
        "conversation": conversation,
        "id": conversation.id,
        "type": TYPE_CONVERSATION,
        "title": conversation_title(conversation),
        "created_at": iso_utc(conversation.created_at),
        "updated_at": iso_utc(conversation.updated_at),
        "source_file": source_file,
        "project_id": conversation.project_id,
        "project_title": None if project is None else project.title,
        "project_link": (
            None
            if project is None
            else relative_link(
                path if path is not None else conversation_output_path(conversation), project.path
            )
        ),
        # CA-4: `""` se emite; solo `None` (campo ausente) se omite.
        "summary": conversation.summary,
        "message_count": len(conversation.messages),
        "tags": conversation_tags(conversation),
        "extra": jsonable(extra),
        "turns": turns,
    }


def render_conversation(
    conversation: Conversation,
    environment: Environment | None = None,
    path: str | None = None,
    project: ProjectLink | None = None,
) -> RenderedConversation:
    """Markdown de la conversación más los artefactos que se le sacaron del cuerpo.

    `path` permite imponer la ruta que ya asignó un `ConversationPaths` (para que el
    `.md`, la carpeta de artefactos y la fila del `_index.md` digan lo mismo); si no se
    pasa, se calcula la ruta natural de la conversación. `project` es el proyecto al que
    pertenece, ya resuelto por `usecases/links.py`.
    """
    env = environment if environment is not None else build_environment()
    if path is None:
        path = conversation_output_path(conversation)
    folder = PurePosixPath(path).stem
    collector = ArtifactCollector(folder)
    # El contexto se arma antes de renderizar porque es al armarlo cuando se extraen
    # los artefactos: la plantilla ya recibe el cuerpo con los enlaces puestos.
    context = conversation_context(conversation, collector, project, path)
    rendered = env.get_template(CONVERSATION_TEMPLATE).render(**context)
    parent = PurePosixPath(path).parent
    return RenderedConversation(
        path=path,
        markdown=rendered.rstrip("\n") + "\n",
        artifacts=tuple(
            RenderedFile(
                path=f"{parent}/{folder}/{ARTIFACTS_DIR}/{artifact.name}",
                content=artifact.content,
            )
            for artifact in collector.artifacts
        ),
    )


def render_conversations(
    conversations: Iterable[Conversation], environment: Environment | None = None
) -> Iterator[RenderedConversation]:
    """Render perezoso: permite escribir en streaming sin juntar los 291 Markdown."""
    env = environment if environment is not None else build_environment()
    for conversation in conversations:
        yield render_conversation(conversation, env)


__all__ = [
    "COLLISION_WARNING",
    "CONVERSATIONS_DIR",
    "CONVERSATION_TEMPLATE",
    "TYPE_CONVERSATION",
    "UNDATED_DIR",
    "UNTITLED",
    "ConversationPaths",
    "RenderedConversation",
    "RenderedFile",
    "build_environment",
    "conversation_context",
    "conversation_date",
    "conversation_output_path",
    "conversation_stem",
    "conversation_tags",
    "conversation_title",
    "message_heading",
    "render_conversation",
    "render_conversations",
]

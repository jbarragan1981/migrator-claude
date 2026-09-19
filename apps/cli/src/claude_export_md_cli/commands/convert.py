"""`claude-export-md convert <ruta> <salida> [--templates DIR] [--overwrite] [--quiet]`.

Este módulo solo presenta: parsear, renderizar y escribir es todo de `claude_export_md`
(core). Aquí se decide qué ve el usuario y con qué código de salida termina el proceso
(spec 05):

* **0** — la conversión terminó, aunque haya habido ítems ilegibles: son datos del
  export que no se pudieron leer, no un fallo de la herramienta (CA-2). El resumen dice
  cuántos fueron y apunta a `_report/errors.jsonl`.
* **2** — no se pudo ni empezar: origen irreconocible, zip corrupto como origen o
  carpeta de salida no vacía sin `--overwrite` (CA-3, CA-8). Siempre un mensaje de una
  línea en stderr, nunca un traceback.

Flags del spec que esta versión NO implementa todavía (documentado en spec 05 y en
`docs/specs/STATUS.md`): `--only`, `--strict` y `--json`.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from claude_export_md import (
    ClaudeExportMdError,
    FilesystemSink,
    OutputNotEmptyError,
    create_source,
)
from claude_export_md.usecases.convert import (
    ConvertResult,
    ProgressCallback,
)
from claude_export_md.usecases.convert import (
    convert as run_convert,
)

stdout = Console()
stderr = Console(stderr=True)

#: Cuántas FAMILIAS de advertencia se muestran antes de remitir al informe completo.
MAX_WARNINGS = 5

#: Lo que distingue dos avisos del mismo tipo: rutas, uuids, índices y cantidades. Al
#: borrarlos queda la "forma" del mensaje, que es lo que se agrupa (ver `group_warnings`).
_VARIABLE = re.compile(r"\S*[\d/\\]\S*")


@contextmanager
def _reporter(quiet: bool) -> Iterator[ProgressCallback | None]:
    """Progreso por categoría mientras dura la conversión (CA-4).

    Sin TTY o con `--quiet` no se informa nada durante la corrida: solo el resumen
    final, que es lo que un script puede leer.
    """
    if quiet or not stdout.is_terminal:
        yield None
        return
    with stdout.status("Convirtiendo…") as status:

        def advance(category: str, done: int) -> None:
            status.update(f"Convirtiendo {category}… {done}")

        yield advance


def _summary_table(result: ConvertResult) -> Table:
    # El título no lleva la ruta: rich la partiría en varias líneas para centrarla.
    table = Table(title="Conversión terminada")
    table.add_column("Categoría")
    table.add_column("Ítems", justify="right")
    for category, count in result.counts.items():
        table.add_row(category, str(count))
    table.add_row("archivos escritos", str(len(result.files)))
    return table


def group_warnings(warnings: Sequence[str]) -> list[str]:
    """Una línea por FAMILIA de aviso, las menos repetidas primero.

    Truncar la lista cruda escondía lo accionable: con 8 proyectos, tres avisos idénticos
    de "documento sin contenido" ocupaban el cupo y dejaban fuera al de proyectos
    huérfanos y al de credenciales, que salen UNA vez cada uno. Aquí los mensajes que
    solo cambian en la ruta o en el uuid cuentan como uno (`_VARIABLE`), se muestra el
    primero de la familia con cuántos más hay detrás, y el orden pone delante a los que
    aparecen pocas veces, que son los que el usuario puede accionar.

    El detalle completo, sin agrupar, sigue en `_report/summary.json`.
    """
    families: dict[str, list[str]] = {}
    for warning in warnings:
        families.setdefault(_VARIABLE.sub("·", warning), []).append(warning)
    ordered = sorted(enumerate(families.values()), key=lambda item: (len(item[1]), item[0]))
    return [_warning_line(family) for _first_seen, family in ordered]


def _warning_line(family: Sequence[str]) -> str:
    """El primer aviso de la familia y, si hay más, cuántos quedan detrás."""
    others = len(family) - 1
    if not others:
        return family[0]
    return f"{family[0]} (+{others} {'similar' if others == 1 else 'similares'})"


def warning_summary(warnings: Sequence[str], limit: int = MAX_WARNINGS) -> list[str]:
    """Lo que el usuario ve de las advertencias: familias agrupadas y el resto contado.

    Se trunca por FAMILIA, no por advertencia cruda: así el cupo no se lo comen N copias
    del mismo aviso y el informe no promete "y 6 más" que en realidad son el mismo.
    """
    lines = group_warnings(warnings)
    if len(lines) <= limit:
        return lines
    remaining = len(lines) - limit
    plural = "tipo" if remaining == 1 else "tipos"
    return [*lines[:limit], f"… y {remaining} {plural} de aviso más en _report/summary.json"]


def _report_problems(result: ConvertResult) -> None:
    """Advertencias y errores a stderr; nunca cambian el código de salida (CA-2)."""
    for line in warning_summary(result.report.warnings):
        stderr.print(f"[yellow]Aviso:[/yellow] {line}")
    if result.error_count:
        plural = "ítems" if result.error_count != 1 else "ítem"
        stderr.print(
            f"[yellow]{result.error_count} {plural} con error[/yellow] → _report/errors.jsonl"
        )


def convert(
    ruta: Annotated[
        Path,
        typer.Argument(
            exists=True,
            help="Carpeta del export, un .zip o el member-manifest-*.json.",
            show_default=False,
        ),
    ],
    salida: Annotated[
        Path,
        typer.Argument(
            help="Carpeta donde escribir el árbol Markdown. Debe estar vacía o no existir.",
            show_default=False,
        ),
    ],
    templates: Annotated[
        Path | None,
        typer.Option(
            "--templates",
            exists=True,
            file_okay=False,
            help="Carpeta con plantillas propias que reemplazan a las de la librería.",
        ),
    ] = None,
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", help="Escribe aunque la salida ya tenga contenido."),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", help="Sin progreso: solo el resumen final."),
    ] = False,
) -> None:
    """Convierte una exportación de Claude.ai en una carpeta de Markdown navegable."""
    try:
        # El destino concreto lo elige esta capa: el core solo conoce el puerto
        # `MarkdownSink` (ADR-0006). En M3 la API pasará un `ZipSink` aquí mismo.
        with _reporter(quiet) as progress:
            result = run_convert(
                create_source(ruta),
                FilesystemSink(salida),
                templates=templates,
                overwrite=overwrite,
                progress=progress,
            )
    except OutputNotEmptyError as exc:
        # El problema es la SALIDA, no el export: se nombra la carpeta que hay que mirar.
        stderr.print(f"[red]No se puede escribir en {salida}:[/red] {exc.reason}")
        raise typer.Exit(code=2) from exc
    except ClaudeExportMdError as exc:
        # Formato desconocido o zip corrupto como origen: mensaje limpio, código 2.
        stderr.print(f"[red]No se pudo convertir {ruta}:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    if quiet:
        # typer.echo y no rich: rich parte las rutas largas en varias líneas.
        typer.echo(f"{len(result.files)} archivos escritos en {salida}")
    else:
        stdout.print(_summary_table(result))
        typer.echo(f"Salida: {salida}")
        typer.echo(f"Índice: {salida / '_index.md'}")
    _report_problems(result)
    raise typer.Exit(code=0)

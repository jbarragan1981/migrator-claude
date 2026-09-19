"""`claude-export-md inventory <ruta> [--out inventory.json] [--json]` (spec 05).

Este módulo solo presenta: el descubrimiento, el muestreo y la escritura viven en
`claude_export_md` (core). Las advertencias van a stderr para que `--json` deje
stdout limpio para scripts (CA-5).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from claude_export_md import (
    ClaudeExportMdError,
    Inventory,
    build_inventory,
    create_source,
    dumps_inventory,
    write_inventory,
)

stdout = Console()
stderr = Console(stderr=True)


def _summary_table(inventory: Inventory) -> Table:
    table = Table(title=f"Inventario de {inventory.root} ({inventory.format_version})")
    table.add_column("Categoría")
    table.add_column("Partes", justify="right")
    table.add_column("Archivos", justify="right")
    table.add_column("Tamaño (KB)", justify="right")
    table.add_column("Raíz")
    table.add_column("Ítems (aprox.)", justify="right")
    for name, category in inventory.categories.items():
        count = category.approx_item_count
        items = "?" if count is None else f"{count}{'' if category.item_count_exact else ' ~'}"
        table.add_row(
            name,
            ", ".join(str(part) for part in category.parts),
            str(category.file_count),
            f"{category.total_bytes / 1024:.1f}",
            category.root_type,
            items,
        )
    return table


def inventory(
    ruta: Annotated[
        Path,
        typer.Argument(
            exists=True,
            help="Carpeta del export, un .zip o el member-manifest-*.json.",
            show_default=False,
        ),
    ],
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Escribe el inventario como JSON en esta ruta."),
    ] = None,
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Imprime únicamente el JSON en stdout (para scripts)."),
    ] = False,
) -> None:
    """Describe qué trae un export de Claude.ai sin convertirlo ni modificarlo."""
    try:
        result = build_inventory(create_source(ruta))
    except ClaudeExportMdError as exc:
        # Cualquier error de la librería (formato desconocido, zip corrupto como origen…)
        # se presenta como un mensaje limpio con código 2, nunca como traceback.
        stderr.print(f"[red]No se pudo inventariar {ruta}:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    if out is not None:
        write_inventory(result, out)

    if as_json:
        typer.echo(dumps_inventory(result), nl=False)
    else:
        stdout.print(_summary_table(result))
        if out is not None:
            # typer.echo y no rich: rich parte las rutas largas en varias líneas.
            typer.echo(f"Inventario escrito en {out}")

    for warning in result.warnings:
        stderr.print(f"[yellow]Aviso:[/yellow] {warning}")
    # Las categorías o partes ausentes son una advertencia, nunca un error (CA-2).
    raise typer.Exit(code=0)

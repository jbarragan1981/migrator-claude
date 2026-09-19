from __future__ import annotations

import typer

from claude_export_md_cli.commands.inventory import inventory

app = typer.Typer(
    name="claude-export-md",
    help="Convierte una exportación de datos de Claude.ai en Markdown navegable.",
    no_args_is_help=True,
)


@app.callback()
def cli() -> None:
    """Punto de entrada.

    Obliga a Typer a tratar la app como grupo de subcomandos: sin este callback,
    con un único comando registrado, `inventory` se interpretaría como argumento.
    """


app.command("inventory")(inventory)


if __name__ == "__main__":
    app()

from __future__ import annotations

import typer

from claude_export_md_cli.main import app


def test_app_is_typer_app() -> None:
    assert isinstance(app, typer.Typer)

"""Tests del subcomando `claude-export-md inventory` (spec 05)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from claude_export_md_cli.main import app

runner = CliRunner()

CONVERSATIONS = json.dumps(
    [
        {
            "uuid": "11111111-1111-4111-8111-111111111111",
            "name": "Conversacion sintetica",
            "created_at": "2026-01-02T10:00:00.000000Z",
            "chat_messages": [{"uuid": "m1", "sender": "human", "text": "hola"}],
        }
    ]
)


@pytest.fixture
def export_dir(tmp_path: Path) -> Path:
    """Export sintético con 4 de las 5 categorías (sin `frames-000`)."""
    root = tmp_path / "export con acentós y espacios"
    (root / "conversations-000").mkdir(parents=True)
    (root / "conversations-000" / "conversations.json").write_text(CONVERSATIONS, encoding="utf-8")
    (root / "projects-000").mkdir()
    (root / "projects-000" / "projects.json").write_text("[]", encoding="utf-8")
    (root / "memories-000" / "people").mkdir(parents=True)
    (root / "memories-000" / "profile.md").write_text("# Perfil\n", encoding="utf-8")
    (root / "memories-000" / "people" / "ana.md").write_text("# Ana\n", encoding="utf-8")
    (root / "light_metadata-000").mkdir()
    (root / "light_metadata-000" / "light_metadata.json").write_text(
        '{"account": {}, "settings": {}}', encoding="utf-8"
    )
    return root


def test_inventory_prints_human_summary(export_dir: Path) -> None:
    result = runner.invoke(app, ["inventory", str(export_dir)])

    assert result.exit_code == 0
    assert "conversations" in result.stdout
    assert "memories" in result.stdout


def test_ca2_missing_category_warns_and_exits_zero(export_dir: Path) -> None:
    result = runner.invoke(app, ["inventory", str(export_dir)])

    assert result.exit_code == 0
    assert "frames" in result.stderr
    assert "ausente" in result.stderr.lower()


def test_ca5_json_flag_prints_only_json(export_dir: Path) -> None:
    result = runner.invoke(app, ["inventory", str(export_dir), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["format_version"] == "batched-manifest"
    assert sorted(payload["categories"]) == [
        "conversations",
        "light_metadata",
        "memories",
        "projects",
    ]


def test_out_writes_file_and_is_deterministic(export_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "salida" / "inventory.json"

    first = runner.invoke(app, ["inventory", str(export_dir), "--out", str(out)])
    assert first.exit_code == 0
    assert out.exists()
    content = out.read_bytes()

    second = runner.invoke(app, ["inventory", str(export_dir), "--out", str(out)])
    assert second.exit_code == 0
    assert out.read_bytes() == content
    assert str(out) in first.stdout


def test_out_plus_json_keeps_stdout_pure(export_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "inventory.json"
    result = runner.invoke(app, ["inventory", str(export_dir), "--out", str(out), "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == json.loads(out.read_text(encoding="utf-8"))


def test_missing_path_exits_with_code_2(tmp_path: Path) -> None:
    result = runner.invoke(app, ["inventory", str(tmp_path / "no-existe")])
    assert result.exit_code == 2


def test_corrupt_zip_as_source_exits_with_code_2(tmp_path: Path) -> None:
    """Un zip roto es `CorruptFileError`: mensaje limpio, código 2, sin traceback."""
    broken = tmp_path / "conversations-000.zip"
    broken.write_bytes(b"esto no es un zip")

    result = runner.invoke(app, ["inventory", str(broken)])

    assert result.exit_code == 2
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert "Traceback" not in result.stderr
    assert "conversations-000.zip" in result.stderr


def test_inventory_output_never_shows_memory_leaf_filenames(export_dir: Path) -> None:
    """Ni la tabla ni el JSON del CLI exponen `people/<persona>.md` (ADR-0004)."""
    result = runner.invoke(app, ["inventory", str(export_dir), "--json"])

    assert result.exit_code == 0
    assert "ana" not in result.stdout
    assert "memories-000/people/*.md" in result.stdout


def test_unknown_format_exits_with_code_2(tmp_path: Path) -> None:
    empty = tmp_path / "vacio"
    empty.mkdir()
    result = runner.invoke(app, ["inventory", str(empty)])
    assert result.exit_code == 2
    assert "reconoc" in result.stderr.lower()

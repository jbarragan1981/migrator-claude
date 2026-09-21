"""Tests del subcomando `claude-export-md convert` (spec 05 CA-1..CA-4, CA-6, CA-8)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from claude_export_md_cli.commands.convert import MAX_WARNINGS, group_warnings, warning_summary
from claude_export_md_cli.main import app

runner = CliRunner()

#: Un export mínimo con las dos categorías que M1 sabe convertir, más un ítem roto.
CONVERSATIONS = json.dumps(
    [
        {
            "uuid": "11111111-1111-4111-8111-111111111111",
            "name": "Conversación con acentós",
            "created_at": "2026-01-02T10:00:00.000000Z",
            "chat_messages": [{"uuid": "m1", "sender": "human", "text": "hola"}],
        },
        {"name": "Ítem sin uuid", "chat_messages": []},
    ]
)
MEMORIES = json.dumps(
    {
        "account_uuid": "11111111-2222-4333-8444-555555555555",
        "conversations_memory": "Prefiere respuestas directas.\n",
        "memory_files": [{"path": "/profile.md", "content": "# Perfil\n"}],
    }
)


@pytest.fixture
def export_dir(tmp_path: Path) -> Path:
    """CA-6: la raíz lleva espacios y acentos a propósito."""
    root = tmp_path / "export con acentós y espacios"
    (root / "conversations-000").mkdir(parents=True)
    (root / "conversations-000" / "conversations.json").write_text(CONVERSATIONS, encoding="utf-8")
    (root / "memories-000" / "memories").mkdir(parents=True)
    (root / "memories-000" / "memories" / "cuenta.json").write_text(MEMORIES, encoding="utf-8")
    return root


@pytest.fixture
def out(tmp_path: Path) -> Path:
    return tmp_path / "salida con espacios"


def tree(root: Path) -> set[str]:
    return {path.relative_to(root).as_posix() for path in sorted(root.rglob("*")) if path.is_file()}


def test_ca1_convert_writes_the_tree_and_exits_zero(export_dir: Path, out: Path) -> None:
    result = runner.invoke(app, ["convert", str(export_dir), str(out)])

    assert result.exit_code == 0
    assert {"README.md", "_index.md", "_report/summary.json"} <= tree(out)
    assert "memories/profile.md" in tree(out)
    assert "conversations/2026/01/2026-01-02_conversacion-con-acentos_11111111.md" in tree(out)


def test_ca1_the_summary_is_printed(export_dir: Path, out: Path) -> None:
    result = runner.invoke(app, ["convert", str(export_dir), str(out)])

    assert "conversations" in result.stdout
    assert "memories" in result.stdout


def test_ca2_parse_errors_do_not_change_the_exit_code(export_dir: Path, out: Path) -> None:
    """CA-2: con ítems ilegibles termina en 0 y dice dónde está el detalle."""
    result = runner.invoke(app, ["convert", str(export_dir), str(out)])
    message = result.stdout + result.stderr

    assert result.exit_code == 0
    assert "1 ítem" in message
    assert "_report/errors.jsonl" in message
    assert (out / "_report" / "errors.jsonl").read_text(encoding="utf-8").count("\n") == 1


def test_ca3_a_non_empty_output_fails_with_code_2_and_touches_nothing(
    export_dir: Path, out: Path
) -> None:
    out.mkdir(parents=True)
    (out / "lo-que-ya-estaba.md").write_text("mío", encoding="utf-8")

    result = runner.invoke(app, ["convert", str(export_dir), str(out)])

    assert result.exit_code == 2
    assert "--overwrite" in result.stderr
    assert "Traceback" not in result.stderr
    assert tree(out) == {"lo-que-ya-estaba.md"}


def test_ca3_overwrite_converts_into_a_non_empty_output(export_dir: Path, out: Path) -> None:
    out.mkdir(parents=True)
    (out / "lo-que-ya-estaba.md").write_text("mío", encoding="utf-8")

    result = runner.invoke(app, ["convert", str(export_dir), str(out), "--overwrite"])

    assert result.exit_code == 0
    assert (out / "_index.md").is_file()


def test_ca4_quiet_prints_only_the_final_summary(export_dir: Path, out: Path) -> None:
    result = runner.invoke(app, ["convert", str(export_dir), str(out), "--quiet"])

    assert result.exit_code == 0
    assert "Convirtiendo" not in result.stdout
    assert str(out) in result.stdout


def test_ca8_an_unrecognised_export_is_a_one_line_error_with_code_2(tmp_path: Path) -> None:
    empty = tmp_path / "vacio"
    empty.mkdir()

    result = runner.invoke(app, ["convert", str(empty), str(tmp_path / "salida")])

    assert result.exit_code == 2
    assert "Traceback" not in result.stderr
    assert "reconoc" in result.stderr.lower()


def test_a_missing_source_exits_with_code_2(tmp_path: Path) -> None:
    result = runner.invoke(app, ["convert", str(tmp_path / "no-existe"), str(tmp_path / "out")])

    assert result.exit_code == 2


def test_two_runs_produce_the_same_bytes(export_dir: Path, tmp_path: Path) -> None:
    """Spec 04 CA-1 desde el CLI: convertir dos veces da exactamente lo mismo."""
    first, second = tmp_path / "a", tmp_path / "b"

    assert runner.invoke(app, ["convert", str(export_dir), str(first)]).exit_code == 0
    assert runner.invoke(app, ["convert", str(export_dir), str(second)]).exit_code == 0

    assert tree(first) == tree(second)
    for relative in tree(first):
        assert (first / relative).read_bytes() == (second / relative).read_bytes()


def test_user_templates_are_used(export_dir: Path, out: Path, tmp_path: Path) -> None:
    templates = tmp_path / "mis-plantillas"
    templates.mkdir()
    (templates / "memory.md.j2").write_text("---\nid: {{ id }}\n---\n\nMÍO\n", encoding="utf-8")

    result = runner.invoke(
        app, ["convert", str(export_dir), str(out), "--templates", str(templates)]
    )

    assert result.exit_code == 0
    assert (out / "memories" / "profile.md").read_text(encoding="utf-8").endswith("MÍO\n")


# ----------------------------------- advertencias: agrupar antes de truncar (CA-2)


def test_repeated_warnings_collapse_into_one_line() -> None:
    """Un mismo aviso repetido ocupa una línea, no N (bug de la revisión de M2)."""
    lines = group_warnings(["a.json: sin `uuid`", "a.json: sin `uuid`", "algo único"])

    assert lines == ["algo único", "a.json: sin `uuid` (+1 similar)"]


def test_warnings_of_the_same_shape_collapse_even_with_different_names() -> None:
    """La familia es el mensaje sin rutas ni identificadores: cambia el archivo, no el aviso."""
    lines = group_warnings(
        [
            "projects-000/projects/a.json: el documento docs[0] no trae `uuid`",
            "projects-000/projects/b.json: el documento docs[1] no trae `uuid`",
            "projects-000/projects/c.json: el documento docs[0] no trae `uuid`",
        ]
    )

    assert lines == [
        "projects-000/projects/a.json: el documento docs[0] no trae `uuid` (+2 similares)"
    ]


def test_the_distinct_warnings_are_shown_before_the_repeated_ones() -> None:
    """Lo accionable (una sola vez) no puede quedar detrás de 50 líneas iguales."""
    repeated = [f"projects-000/projects/{index}.json: sin `uuid`" for index in range(50)]
    unique = "2 conversaciones apuntan a 1 proyecto que este export no trae"

    lines = group_warnings([*repeated, unique])

    assert lines[0] == unique


def test_no_warning_is_invented_when_there_are_none() -> None:
    assert group_warnings([]) == []


def test_the_summary_truncates_by_family_and_counts_the_rest() -> None:
    """Se muestran hasta MAX_WARNINGS familias; el resto se cuenta, no se repite."""
    families = [f"aviso de tipo {chr(ord('a') + index)}" for index in range(8)]

    lines = warning_summary(families)

    assert lines[:MAX_WARNINGS] == families[:MAX_WARNINGS]
    assert lines[-1] == "… y 3 tipos de aviso más en _report/summary.json"


def test_the_last_family_left_out_is_said_in_singular() -> None:
    families = [f"aviso de tipo {chr(ord('a') + index)}" for index in range(MAX_WARNINGS + 1)]

    assert warning_summary(families)[-1] == "… y 1 tipo de aviso más en _report/summary.json"


def test_nothing_is_truncated_when_the_families_fit() -> None:
    families = [f"aviso de tipo {chr(ord('a') + index)}" for index in range(MAX_WARNINGS)]

    assert warning_summary(families) == families


def test_the_actionable_warning_is_visible_with_many_projects(tmp_path: Path, out: Path) -> None:
    """Caso exacto de la revisión: los avisos de docs sin contenido tapaban al huérfano."""
    root = tmp_path / "export"
    projects = root / "projects-000" / "projects"
    projects.mkdir(parents=True)
    for index in range(8):
        uuid = f"{index}0000000-1111-4222-8333-444444444444"
        (projects / f"{uuid}.json").write_text(
            json.dumps(
                {
                    "uuid": uuid,
                    "name": f"Proyecto {index}",
                    "created_at": "2026-01-02T03:04:05.000000Z",
                    "docs": [{"uuid": f"doc-{index}", "filename": f"notas-{index}.md"}],
                }
            ),
            encoding="utf-8",
        )
    (root / "conversations-000").mkdir(parents=True)
    (root / "conversations-000" / "conversations.json").write_text(
        json.dumps(
            [
                {
                    "uuid": "11111111-1111-4111-8111-111111111111",
                    "name": "Huérfana",
                    "created_at": "2026-01-02T10:00:00.000000Z",
                    "project_uuid": "99999999-9999-4999-8999-999999999999",
                    "chat_messages": [],
                }
            ]
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["convert", str(root), str(out)])
    # rich parte las líneas largas: se comparan sin tener en cuenta dónde cortó.
    message = " ".join(result.stderr.split())

    assert result.exit_code == 0
    assert "99999999-9999-4999-8999-999999999999" in message
    assert "8 documentos de 8 proyectos" in message

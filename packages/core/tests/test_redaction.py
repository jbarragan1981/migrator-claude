"""Reglas de redacción del inventario (ADR-0004).

El inventario describe FORMA, no contenido. Un nombre de archivo hoja de una carpeta
de Markdown (`memories-000/people/<persona>.md`) ES contenido: nunca se serializa.
"""

from __future__ import annotations

import pytest

from claude_export_md.domain.redaction import describe_path, redact_text


@pytest.mark.parametrize(
    "path",
    [
        "conversations-000/conversations.json",
        "conversations-001.json",
        "conversations-000.zip!/conversations.json",
        "users.json",
    ],
)
def test_predictable_names_keep_their_literal_path(path: str) -> None:
    """Nombre = categoría (± sufijo de parte) → no depende del contenido del usuario."""
    category = "users" if path == "users.json" else "conversations"
    assert describe_path(path, category) == (path, None)


def test_markdown_leaf_name_is_collapsed_into_a_pattern() -> None:
    assert describe_path("memories-000/people/ana-real.md", "memories") == (
        None,
        "memories-000/people/*.md",
    )


def test_zip_member_leaf_name_is_collapsed_too() -> None:
    assert describe_path("memories-000.zip!/people/ana-real.md", "memories") == (
        None,
        "memories-000.zip!/people/*.md",
    )


def test_root_level_leaf_name_is_collapsed_without_directory() -> None:
    assert describe_path("notas-de-ana.md", "memories") == (None, "*.md")


def test_extensionless_leaf_name_uses_a_bare_star() -> None:
    assert describe_path("frames-000/CAPTURA-de-ana", "frames") == (None, "frames-000/*")


def test_extension_is_lowercased_so_the_grouping_is_stable() -> None:
    assert describe_path("frames-000/Ana.PNG", "frames") == (None, "frames-000/*.png")


def test_directory_segments_that_look_like_a_uuid_are_masked() -> None:
    path = "frames-000/11111111-1111-4111-8111-111111111111/captura.png"
    assert describe_path(path, "frames") == (None, "frames-000/<uuid>/*.png")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("11111111-1111-4111-8111-111111111111", "<uuid>"),
        ("user_11111111-1111-4111-8111-111111111111", "user_<uuid>"),
        ("ana@example.com", "<email>"),
        ("owner:ana@example.com", "owner:<email>"),
        ("conversations", "conversations"),
    ],
)
def test_redact_text_masks_uuids_and_emails(value: str, expected: str) -> None:
    assert redact_text(value) == expected

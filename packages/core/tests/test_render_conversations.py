"""Render Markdown de `conversations` (spec 04: CA-1..CA-6, CA-9, CA-10).

El snapshot (`syrupy`) es la red de seguridad del formato: si cambia una línea del
Markdown generado, el test falla y hay que mirar el diff a ojo antes de actualizarlo.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import frontmatter
import pytest
from syrupy.assertion import SnapshotAssertion

from claude_export_md.adapters.parsers import conversations as parser
from claude_export_md.adapters.source_folder import FolderSource
from claude_export_md.domain.entities import ContentBlock, Conversation, Message, Report
from claude_export_md.rendering.artifacts import (
    ARTIFACT_MIN_LINES,
    ArtifactCollector,
    extension_for,
)
from claude_export_md.rendering.conversations import (
    ConversationPaths,
    RenderedConversation,
    build_environment,
    conversation_output_path,
    conversation_title,
    render_conversation,
    render_conversations,
)
from claude_export_md.rendering.filters import code_fence, hhmm

CONV_1 = "a1a1a1a1-1111-4000-8000-000000000001"
CONV_2 = "b2b2b2b2-2222-4000-8000-000000000002"
CONV_3 = "c3c3c3c3-3333-4000-8000-000000000003"
CONV_4 = "d4d4d4d4-4444-4000-8000-000000000004"
PROJECT = "ffffffff-0000-4000-8000-000000000001"

CONV_1_DIR = "2026-01-15_analisis-nandu-q3_a1a1a1a1"


@pytest.fixture
def conversations(fixtures_dir: Path) -> list[Conversation]:
    source = FolderSource(fixtures_dir / "conversations-batched")
    return parser.parse_sorted(source, Report())


@pytest.fixture
def rendered(conversations: list[Conversation]) -> dict[str, RenderedConversation]:
    environment = build_environment()
    return {
        conversation.id: render_conversation(conversation, environment)
        for conversation in conversations
    }


def meta(markdown: str) -> dict[str, Any]:
    """Frontmatter ya parseado. `python-frontmatter` tipa los valores como `object`."""
    return cast(dict[str, Any], frontmatter.loads(markdown).metadata)


def body(markdown: str) -> str:
    return frontmatter.loads(markdown).content


def conversation(**fields: Any) -> Conversation:  # noqa: ANN401
    """Conversación mínima para probar una regla suelta sin arrastrar el fixture."""
    return Conversation.model_validate({"id": CONV_1, **fields})


def text_message(text: str, sender: str = "assistant") -> Message:
    return Message.model_validate(
        {
            "id": "m1",
            "sender": sender,
            "blocks": [ContentBlock.from_raw({"type": "text", "text": text})],
        }
    )


# --------------------------------------------------------- CA-3 encabezados


def test_ca3_headings_name_the_speaker_with_the_time(
    rendered: dict[str, RenderedConversation],
) -> None:
    """CA-3: `## 👤 Usuario` / `## 🤖 Claude` con el timestamp en `HH:MM`."""
    markdown = rendered[CONV_1].markdown

    assert "## 👤 Usuario — 14:32" in markdown
    assert "## 🤖 Claude — 14:33" in markdown


def test_the_time_of_the_heading_is_utc(rendered: dict[str, RenderedConversation]) -> None:
    """El export trae `+02:00`; el encabezado muestra la hora ya normalizada."""
    assert "## 👤 Usuario — 06:05" in rendered[CONV_2].markdown


def test_a_message_without_date_has_a_heading_without_time(
    rendered: dict[str, RenderedConversation],
) -> None:
    markdown = rendered[CONV_3].markdown

    assert "## 👤 Usuario\n" in markdown
    assert "—" not in markdown.split("## 👤 Usuario\n")[1].split("\n")[0]


def test_an_unknown_sender_keeps_its_own_name() -> None:
    """Solo se conocen `human` y `assistant`; cualquier otro se muestra tal cual."""
    markdown = render_conversation(
        conversation(messages=[text_message("hola", sender="system")])
    ).markdown

    assert "## 💬 system" in markdown


def test_a_message_without_sender_gets_a_neutral_heading() -> None:
    markdown = render_conversation(
        conversation(messages=[Message.model_validate({"id": "m1", "text": "hola"})])
    ).markdown

    assert "## 💬 Mensaje" in markdown


def test_hhmm_formats_utc_and_propagates_none() -> None:
    assert hhmm(datetime(2026, 1, 15, 14, 32, 5, tzinfo=UTC)) == "14:32"
    assert hhmm(None) is None


def test_text_of_a_message_is_inserted_verbatim(
    rendered: dict[str, RenderedConversation],
) -> None:
    """Regla 5 del skill: el texto ya es Markdown, no se escapa ni se reindenta."""
    assert "Podes revisar `scripts/ventas.py` y decirme que esta mal?" in rendered[CONV_1].markdown


def test_a_message_without_blocks_still_renders_its_text() -> None:
    """Si el export no trajo `content[]`, el `text` plano es lo único que hay."""
    markdown = render_conversation(
        conversation(
            messages=[Message.model_validate({"id": "m", "sender": "human", "text": "ey"})]
        )
    ).markdown

    assert "ey" in body(markdown)


# ------------------------------------------------------------- CA-4 details


def test_ca4_tool_use_is_collapsed_into_details(
    rendered: dict[str, RenderedConversation],
) -> None:
    """CA-4: `tool_use` va dentro de `<details>`."""
    markdown = rendered[CONV_1].markdown

    assert "<summary>🔧 Uso de herramienta: <code>read_file</code></summary>" in markdown
    assert markdown.count("<details>") == markdown.count("</details>") == 3


def test_ca4_details_do_not_break_the_surrounding_markdown(
    rendered: dict[str, RenderedConversation],
) -> None:
    """El frontmatter sigue siendo válido y el texto posterior sigue siendo Markdown."""
    post = frontmatter.loads(rendered[CONV_1].markdown)

    assert post.metadata["id"] == CONV_1
    assert "\n\n</details>\n" in post.content
    assert "## 🤖 Claude" in post.content


def test_thinking_and_tool_result_have_their_own_summary(
    rendered: dict[str, RenderedConversation],
) -> None:
    markdown = rendered[CONV_1].markdown

    assert "<summary>🧠 Razonamiento</summary>" in markdown
    assert "<summary>📋 Resultado de <code>read_file</code></summary>" in markdown


def test_an_unknown_block_type_is_shown_instead_of_dropped(
    rendered: dict[str, RenderedConversation],
) -> None:
    """CLAUDE.md §1.3: un tipo que no conocemos se ve, no desaparece."""
    markdown = rendered[CONV_2].markdown

    assert "<summary>❓ Bloque <code>vision_preview</code></summary>" in markdown
    assert "Un bloque de un tipo que todavia no conocemos" in markdown


def test_the_thinking_summaries_are_listed(rendered: dict[str, RenderedConversation]) -> None:
    markdown = rendered[CONV_1].markdown

    assert "- Revisar el script antes de responder" in markdown
    assert "El usuario tiene un script lento." in markdown


def test_the_free_form_tool_input_is_shown_as_json(
    rendered: dict[str, RenderedConversation],
) -> None:
    """CA-3: `input` no tiene claves fijas, así que se muestra entero como JSON."""
    markdown = rendered[CONV_1].markdown

    assert '"path": "/home/usuaria/proyecto/scripts/ventas.py"' in markdown
    assert '"description": "Leer el script de ventas"' in markdown


def test_the_tool_result_text_is_readable_and_its_metadata_survives(
    rendered: dict[str, RenderedConversation],
) -> None:
    markdown = rendered[CONV_1].markdown

    assert "linea 60 del archivo scripts/ventas.py" in markdown
    assert '"output_format_category": "txt"' in markdown


def test_null_fields_of_a_block_are_not_printed(
    rendered: dict[str, RenderedConversation],
) -> None:
    """Un `null` no aporta nada al lector; el dato completo vive en el dominio."""
    assert "mcp_server_url" not in rendered[CONV_1].markdown


def block_message(*blocks: dict[str, Any]) -> Message:
    return Message.model_validate(
        {
            "id": "m1",
            "sender": "assistant",
            "blocks": [ContentBlock.from_raw(block) for block in blocks],
        }
    )


def test_a_failed_tool_result_says_so_in_its_summary() -> None:
    """`is_error` se ve sin desplegar el `<details>`: es lo primero que se busca."""
    markdown = render_conversation(
        conversation(
            messages=[
                block_message(
                    {
                        "type": "tool_result",
                        "name": "bash",
                        "is_error": True,
                        "content": [{"type": "text", "text": "command not found"}],
                    }
                )
            ]
        )
    ).markdown

    assert "<summary>📋 Resultado de <code>bash</code> (error)</summary>" in markdown
    assert "command not found" in markdown


def test_a_tool_block_without_name_keeps_a_generic_summary() -> None:
    markdown = render_conversation(
        conversation(
            messages=[
                block_message({"type": "tool_use", "input": {"q": 1}}, {"type": "tool_result"})
            ]
        )
    ).markdown

    assert "<summary>🔧 Uso de herramienta</summary>" in markdown
    assert "<summary>📋 Resultado</summary>" in markdown


def test_an_empty_block_still_produces_a_details_with_a_label() -> None:
    """Un bloque sin nada dentro se ve vacío, no desaparece sin dejar rastro."""
    markdown = render_conversation(
        conversation(messages=[block_message({"type": "raro"})])
    ).markdown

    assert "<summary>❓ Bloque <code>raro</code></summary>" in markdown
    assert "**Contenido**" in markdown


def test_an_empty_text_block_adds_nothing() -> None:
    markdown = render_conversation(
        conversation(messages=[block_message({"type": "text", "text": "   "})])
    ).markdown

    assert body(markdown).count("\n\n") == 1


def test_a_code_fence_inside_a_block_does_not_break_the_wrapper() -> None:
    """Si el texto ya trae ```, la cerca del envoltorio tiene que ser más larga."""
    fenced = code_fence("```python\nx = 1\n```", "json")

    assert fenced.startswith("````json\n")
    assert fenced.endswith("\n````")


# ----------------------------------------------------------- CA-5 artefactos


def fenced(lines: int, language: str = "python") -> str:
    cuerpo = "\n".join(f"linea {n}" for n in range(1, lines + 1))
    return f"Mira esto:\n\n```{language}\n{cuerpo}\n```\n\nY ya."


def test_ca5_a_long_code_block_is_written_as_a_file(
    rendered: dict[str, RenderedConversation],
) -> None:
    """CA-5: el artefacto va a `artifacts/01-<slug>.<ext>`."""
    artifacts = rendered[CONV_1].artifacts

    assert [artifact.path for artifact in artifacts] == [
        f"conversations/2026/01/{CONV_1_DIR}/artifacts/01-ventas.py"
    ]
    assert artifacts[0].content.startswith('"""Informe de ventas del trimestre."""')
    assert artifacts[0].content.endswith("\n")


def test_ca5_the_body_links_to_the_artifact_with_a_relative_path(
    rendered: dict[str, RenderedConversation],
) -> None:
    """CA-5 + regla 4 del skill: el enlace funciona en Obsidian, VS Code y GitHub."""
    markdown = rendered[CONV_1].markdown

    assert f"]({CONV_1_DIR}/artifacts/01-ventas.py)" in markdown
    assert "def por_region" not in markdown


def test_a_short_code_block_stays_inline(rendered: dict[str, RenderedConversation]) -> None:
    """Solo se extrae lo largo: un par de líneas se leen mejor donde estaban."""
    markdown = rendered[CONV_1].markdown

    assert "```bash\nuv run python scripts/ventas.py" in markdown


def test_the_threshold_is_the_one_of_the_skill() -> None:
    """Umbral = 40 líneas (skill regla 7); satisface el ejemplo de 120 de la spec 04 CA-5."""
    assert ARTIFACT_MIN_LINES == 40


def test_a_block_exactly_at_the_threshold_is_not_extracted() -> None:
    collector = ArtifactCollector("carpeta")

    result = collector.extract(fenced(ARTIFACT_MIN_LINES))

    assert collector.artifacts == []
    assert result.count("\n") == fenced(ARTIFACT_MIN_LINES).count("\n")


def test_one_line_over_the_threshold_is_extracted() -> None:
    collector = ArtifactCollector("carpeta")

    result = collector.extract(fenced(ARTIFACT_MIN_LINES + 1))

    assert len(collector.artifacts) == 1
    assert collector.artifacts[0].lines == ARTIFACT_MIN_LINES + 1
    assert "linea 41" not in result
    assert "Mira esto:" in result and "Y ya." in result


def test_artifacts_are_numbered_in_order_of_appearance() -> None:
    collector = ArtifactCollector("carpeta")

    collector.extract(fenced(50, "python"))
    collector.extract(fenced(50, "sql"))

    assert [artifact.name for artifact in collector.artifacts] == ["01-python.py", "02-sql.sql"]
    assert collector.artifacts[1].link == "carpeta/artifacts/02-sql.sql"


def test_the_name_comes_from_a_file_named_just_before_the_fence() -> None:
    """`Te dejo `scripts/ventas.py`:` + ```python → `01-ventas.py`, no `01-python.py`."""
    collector = ArtifactCollector("carpeta")

    collector.extract("Te dejo `scripts/ventas.py`:\n\n" + fenced(50))

    assert collector.artifacts[0].name == "01-ventas.py"


def test_an_inline_code_that_is_not_a_file_name_is_ignored() -> None:
    """La pista solo vale si la extensión coincide con el lenguaje de la cerca."""
    collector = ArtifactCollector("carpeta")

    collector.extract("Usa `pandas.DataFrame` asi:\n\n" + fenced(50))

    assert collector.artifacts[0].name == "01-python.py"


def test_a_fence_without_language_becomes_a_txt() -> None:
    collector = ArtifactCollector("carpeta")

    collector.extract(fenced(50, ""))

    assert collector.artifacts[0].name == "01-artefacto.txt"


@pytest.mark.parametrize(
    ("language", "suffix"),
    [
        ("python", ".py"),
        ("Python", ".py"),
        ("ts", ".ts"),
        ("html", ".html"),
        ("svg", ".svg"),
        ("desconocido", ".txt"),
        ("", ".txt"),
    ],
)
def test_extension_is_inferred_from_the_fence_language(language: str, suffix: str) -> None:
    assert extension_for(language) == suffix


def test_a_tilde_fence_is_extracted_too() -> None:
    collector = ArtifactCollector("carpeta")
    cuerpo = "\n".join(f"linea {n}" for n in range(1, 60))

    result = collector.extract(f"~~~python\n{cuerpo}\n~~~")

    assert len(collector.artifacts) == 1
    assert "linea 59" not in result


def test_an_unclosed_fence_is_left_alone() -> None:
    """Sin cierre no se sabe dónde acaba el artefacto: se deja el texto tal cual."""
    collector = ArtifactCollector("carpeta")
    text = "```python\n" + "\n".join(f"linea {n}" for n in range(1, 60))

    assert collector.extract(text) == text
    assert collector.artifacts == []


def test_backticks_inside_the_artifact_survive_the_extraction() -> None:
    collector = ArtifactCollector("carpeta")
    cuerpo = "\n".join(["```", *[f"linea {n}" for n in range(1, 60)]])

    collector.extract(f"````markdown\n{cuerpo}\n````")

    assert collector.artifacts[0].content.startswith("```\n")


# ------------------------------------------------------------ CA-6 slug/ruta


def test_ca6_the_path_uses_the_date_the_slug_and_the_uuid8(
    rendered: dict[str, RenderedConversation],
) -> None:
    """CA-6 + CLAUDE.md §5: `conversations/YYYY/MM/YYYY-MM-DD_<slug>_<uuid8>.md`."""
    assert rendered[CONV_1].path == f"conversations/2026/01/{CONV_1_DIR}.md"


def test_an_empty_title_still_produces_a_name(
    rendered: dict[str, RenderedConversation],
) -> None:
    assert rendered[CONV_2].path == "conversations/2026/02/2026-02-03_sin-titulo_b2b2b2b2.md"


def test_a_conversation_without_date_goes_to_its_own_folder(
    rendered: dict[str, RenderedConversation],
) -> None:
    """Sin `created_at` no hay `YYYY/MM`: no se inventa una fecha."""
    assert rendered[CONV_3].path == "conversations/sin-fecha/charla-sin-fecha_c3c3c3c3.md"


def test_the_updated_date_is_used_when_there_is_no_creation_date() -> None:
    rendered = render_conversation(
        conversation(title="Solo actualizada", updated_at="2026-05-04T03:02:01Z")
    )

    assert rendered.path == "conversations/2026/05/2026-05-04_solo-actualizada_a1a1a1a1.md"


def test_an_id_too_short_for_a_uuid8_falls_back_to_a_hash() -> None:
    """El identificador del export es un uuid, pero el nombre no puede depender de eso."""
    rendered = render_conversation(Conversation(id="ab", title="Corta"))

    assert rendered.path.endswith(".md")
    assert "_ab." not in rendered.path


def test_the_title_of_an_untitled_conversation_says_so() -> None:
    assert conversation_title(conversation(title="")) == "Conversación sin título"
    assert conversation_title(conversation(title=None)) == "Conversación sin título"
    assert conversation_title(conversation(title="Hola")) == "Hola"


def test_output_path_is_stable_for_the_same_conversation(
    conversations: list[Conversation],
) -> None:
    assert [conversation_output_path(c) for c in conversations] == [
        conversation_output_path(c) for c in conversations
    ]


# ------------------------------------------------- colisiones de ruta


#: Dos uuids distintos con los MISMOS 8 primeros caracteres alfanuméricos: mismo día y
#: mismo título dan exactamente la misma ruta de salida.
TWIN_A = "a1a1a1a1-0000-4000-8000-000000000001"
TWIN_B = "a1a1a1a1-0000-4000-8000-000000000002"


def twins() -> list[Conversation]:
    return [
        Conversation.model_validate(
            {"id": uuid, "title": "Ventas", "created_at": "2026-01-15T10:00:00Z"}
        )
        for uuid in (TWIN_A, TWIN_B)
    ]


def test_two_conversations_that_want_the_same_path_do_not_overwrite_each_other() -> None:
    """CLAUDE.md §1.3: nada se pierde en silencio, tampoco por un nombre repetido."""
    first, second = twins()
    paths = ConversationPaths()

    assigned = [paths.assign(first), paths.assign(second)]

    assert assigned[0] == "conversations/2026/01/2026-01-15_ventas_a1a1a1a1.md"
    assert assigned[1] != assigned[0]
    assert assigned[1].startswith("conversations/2026/01/2026-01-15_ventas_a1a1a1a1-")
    assert assigned[1].endswith(".md")


def test_a_path_collision_is_reported_as_a_warning() -> None:
    """Desambiguar no basta: el usuario tiene que enterarse de por qué hay un sufijo."""
    first, second = twins()
    paths = ConversationPaths()
    paths.assign(first)
    paths.assign(second)

    assert len(paths.warnings) == 1
    assert "2026-01-15_ventas_a1a1a1a1.md" in paths.warnings[0]
    assert TWIN_B in paths.warnings[0]


def test_a_path_that_nobody_claimed_yet_is_left_alone() -> None:
    paths = ConversationPaths()

    assert paths.assign(conversation(title="Sola")) == conversation_output_path(
        conversation(title="Sola")
    )
    assert paths.warnings == []


def test_even_a_duplicated_uuid_gets_its_own_file() -> None:
    """El hash desempata por `id`; con el MISMO `id` hace falta además un contador."""
    twin = twins()[0]
    paths = ConversationPaths()

    assigned = [paths.assign(twin) for _ in range(3)]

    assert len(set(assigned)) == 3
    assert len(paths.warnings) == 2


def test_the_disambiguated_conversation_renders_at_its_new_path() -> None:
    """El `.md` y la carpeta de sus artefactos siguen a la ruta ya desempatada."""
    first, second = twins()
    paths = ConversationPaths()
    paths.assign(first)
    path = paths.assign(second)

    rendered = render_conversation(second, build_environment(), path)

    assert rendered.path == path


# -------------------------------------------------------------- frontmatter


def test_ca2_frontmatter_is_valid_and_has_the_required_fields(
    rendered: dict[str, RenderedConversation],
) -> None:
    """Spec 04 CA-2: parseable y con los campos obligatorios."""
    for result in rendered.values():
        metadata = meta(result.markdown)

        assert set(metadata) >= {
            "id",
            "type",
            "title",
            "created_at",
            "updated_at",
            "source_file",
            "tags",
        }
        assert metadata["type"] == "conversation"


def test_frontmatter_carries_dates_source_and_counts(
    rendered: dict[str, RenderedConversation],
) -> None:
    metadata = meta(rendered[CONV_1].markdown)

    assert metadata["created_at"] == "2026-01-15T14:32:05Z"
    assert metadata["updated_at"] == "2026-01-15T15:10:47Z"
    assert metadata["source_file"] == "conversations-000/conversations.json"
    assert metadata["message_count"] == 2
    assert metadata["title"] == "Analisis Nandu / Q3"


def test_the_project_link_is_in_the_frontmatter_and_in_the_tags(
    rendered: dict[str, RenderedConversation],
) -> None:
    """CA-2 del parser, visible en la salida."""
    metadata = meta(rendered[CONV_2].markdown)

    assert metadata["project_id"] == PROJECT
    assert "project" in metadata["tags"]


def test_a_conversation_without_project_has_no_project_id_key(
    rendered: dict[str, RenderedConversation],
) -> None:
    assert "project_id" not in meta(rendered[CONV_1].markdown)


def test_an_empty_summary_is_emitted_and_a_missing_one_is_not(
    rendered: dict[str, RenderedConversation],
) -> None:
    """CA-4: `""` no es lo mismo que `null` y la salida lo refleja."""
    assert meta(rendered[CONV_2].markdown)["summary"] == ""
    assert "summary" not in meta(rendered[CONV_3].markdown)


def test_unknown_fields_end_up_under_extra(
    rendered: dict[str, RenderedConversation],
) -> None:
    """CA-C4: `account` no está en el modelo y aparece bajo `extra:`."""
    extra = meta(rendered[CONV_1].markdown)["extra"]

    assert extra["account"] == {"uuid": "11111111-2222-4333-8444-555555555555"}
    assert "source_file" not in extra


def test_an_awkward_title_does_not_break_the_yaml() -> None:
    markdown = render_conversation(conversation(title='a: "b"\nc')).markdown

    assert meta(markdown)["title"] == 'a: "b"\nc'


def test_a_conversation_without_messages_renders_only_its_header(
    rendered: dict[str, RenderedConversation],
) -> None:
    """La conversación de `chat_messages` ilegible sigue siendo un `.md` válido."""
    assert meta(rendered[CONV_4].markdown)["message_count"] == 0
    assert "##" not in body(rendered[CONV_4].markdown)


# --------------------------------------------------- CA-10 nada de la corrida


def test_ca10_output_has_no_generation_date_or_tool_version(
    rendered: dict[str, RenderedConversation],
) -> None:
    today = datetime.now(tz=UTC).date().isoformat()

    for result in rendered.values():
        assert today not in result.markdown
        assert "claude_export_md" not in result.markdown


# ------------------------------------------------------- CA-1 determinismo


def test_ca1_two_renders_are_byte_identical(conversations: list[Conversation]) -> None:
    first = [render_conversation(c) for c in conversations]
    second = [render_conversation(c) for c in conversations]

    assert [r.markdown.encode("utf-8") for r in first] == [
        r.markdown.encode("utf-8") for r in second
    ]
    assert [[(a.path, a.content) for a in r.artifacts] for r in first] == [
        [(a.path, a.content) for a in r.artifacts] for r in second
    ]


def test_render_conversations_is_lazy(conversations: list[Conversation]) -> None:
    """Se puede escribir en streaming: no hace falta materializar los 291 Markdown."""
    results = render_conversations(conversations)

    assert next(iter(results)).path.startswith("conversations/")


# --------------------------------------------------------- CA-9 plantillas


def test_ca9_user_template_overrides_the_default(tmp_path: Path) -> None:
    (tmp_path / "conversation.md.j2").write_text("MÍA: {{ title }}\n", encoding="utf-8")

    markdown = render_conversation(conversation(title="Hola"), build_environment(tmp_path)).markdown

    assert markdown == "MÍA: Hola\n"


# ------------------------------------------------------------------ snapshot


def test_snapshot_of_every_conversation(
    rendered: dict[str, RenderedConversation], snapshot: SnapshotAssertion
) -> None:
    assert {result.path: result.markdown for result in rendered.values()} == snapshot


def test_snapshot_of_the_extracted_artifacts(
    rendered: dict[str, RenderedConversation], snapshot: SnapshotAssertion
) -> None:
    assert {
        artifact.path: artifact.content
        for result in rendered.values()
        for artifact in result.artifacts
    } == snapshot

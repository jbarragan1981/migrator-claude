"""Render Markdown de `projects` → `projects/<slug>/{project.md,docs/<slug>.md}`.

Spec 04 (CA-1 determinismo, CA-2 frontmatter, CA-6 slug, CA-9 plantillas, CA-10 nada de
la corrida) y spec 03 `projects` CA-2 (instrucciones vacías) y CA-3 (documento sin
contenido: hay que DECIRLO, no dejar una sección vacía).

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

from claude_export_md.domain.entities import Project, ProjectDoc
from claude_export_md.rendering.render import (
    DOC_CONTENT_UNAVAILABLE,
    PROJECTS_DIR,
    assign_project_dirs,
    build_environment,
    project_dir,
    project_doc_paths,
    project_output_path,
    project_title,
    render_project,
    render_projects,
)

PROJECT_1 = "11111111-2222-4333-8444-555555555555"
PROJECT_2 = "99999999-8888-4777-8666-555555555555"
CREATOR = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
DOC_1 = "d0c0d0c0-1111-4222-8333-444444444444"
DOC_2 = "d0c0d0c0-5555-4666-8777-888888888888"

CREATED = "2026-01-02T03:04:05Z"
UPDATED = "2026-02-03T04:05:06Z"


def make_doc(**values: Any) -> ProjectDoc:
    return ProjectDoc.model_validate(
        {
            "id": DOC_1,
            "filename": "Guía de estilo.md",
            "created_at": CREATED,
            "content": None,
            **values,
        }
    )


def make_project(**values: Any) -> Project:
    return Project.model_validate(
        {
            "id": PROJECT_1,
            "name": "Proyecto Sintético",
            "description": "Un proyecto de prueba",
            "instructions": "Responde siempre en español.",
            "created_at": CREATED,
            "updated_at": UPDATED,
            "creator_id": CREATOR,
            "docs": [],
            "conversation_ids": [],
            "is_private": True,
            "source_file": f"projects-000/projects/{PROJECT_1}.json",
            **values,
        }
    )


@pytest.fixture
def project() -> Project:
    return make_project()


def meta(markdown: str) -> dict[str, Any]:
    """Frontmatter ya parseado. `python-frontmatter` tipa los valores como `object`."""
    return cast(dict[str, Any], frontmatter.loads(markdown).metadata)


def files(project: Project) -> dict[str, str]:
    """`{ruta: markdown}` de todo lo que genera un proyecto (su `.md` y sus docs)."""
    return dict(render_project(project))


# --------------------------------------------------------- CA-2 frontmatter


def test_ca2_frontmatter_of_the_project_has_the_required_fields(project: Project) -> None:
    """CA-2: parseable con `python-frontmatter` y con los campos obligatorios."""
    markdown = files(project)[f"{PROJECTS_DIR}/proyecto-sintetico/project.md"]

    metadata = meta(markdown)

    assert set(metadata) >= {
        "id",
        "type",
        "title",
        "created_at",
        "updated_at",
        "source_file",
        "tags",
    }
    assert metadata["type"] == "project"
    assert metadata["id"] == PROJECT_1
    assert metadata["created_at"] == CREATED
    assert metadata["updated_at"] == UPDATED
    assert metadata["source_file"] == f"projects-000/projects/{PROJECT_1}.json"
    assert metadata["tags"] == ["project"]


def test_ca2_frontmatter_of_a_doc_declares_which_project_it_belongs_to() -> None:
    """Un doc es una entidad propia (`type: project_doc`) enlazada a su proyecto."""
    rendered = files(make_project(docs=[make_doc()]))

    metadata = meta(rendered[f"{PROJECTS_DIR}/proyecto-sintetico/docs/guia-de-estilo.md"])

    assert metadata["type"] == "project_doc"
    assert metadata["id"] == DOC_1
    assert metadata["project_id"] == PROJECT_1
    assert metadata["created_at"] == CREATED
    assert metadata["source_file"] == f"projects-000/projects/{PROJECT_1}.json"


def test_unknown_fields_are_visible_under_extra(project: Project) -> None:
    markdown = files(project)[f"{PROJECTS_DIR}/proyecto-sintetico/project.md"]

    metadata = meta(markdown)

    assert metadata["extra"]["is_private"] is True
    assert "source_file" not in metadata["extra"]


def test_an_awkward_name_does_not_break_the_yaml() -> None:
    """Un nombre con `:`, comillas y saltos de línea sigue siendo YAML válido."""
    rendered = render_project(make_project(name='a: "b"\nc'))

    assert meta(rendered[0][1])["title"] == 'a: "b"\nc'


# ------------------------------------------------------------------ título


def test_the_title_is_the_name_of_the_project(project: Project) -> None:
    assert project_title(project) == "Proyecto Sintético"


def test_a_project_without_name_gets_an_explicit_title_not_an_invented_one() -> None:
    """`name` vacío o ausente: se dice que no tiene nombre, no se inventa uno."""
    assert project_title(make_project(name="")) == "Proyecto sin título"
    assert project_title(make_project(name=None)) == "Proyecto sin título"


def test_a_project_without_name_falls_back_to_the_slug_of_the_untitled_label() -> None:
    """CA-6: el nombre del archivo cae en el fallback de `slugify`, no en la frase entera."""
    assert project_dir(make_project(name="")) == f"{PROJECTS_DIR}/sin-titulo"


# -------------------------------------------------------------- rutas (CA-6)


def test_each_project_gets_its_own_folder_with_project_md_inside(project: Project) -> None:
    """CLAUDE.md §5: `projects/<slug-proyecto>/project.md`."""
    assert project_dir(project) == f"{PROJECTS_DIR}/proyecto-sintetico"
    assert project_output_path(project) == f"{PROJECTS_DIR}/proyecto-sintetico/project.md"


def test_the_docs_of_a_project_hang_from_its_folder() -> None:
    """CLAUDE.md §5: `projects/<slug>/docs/<slug-doc>.md`."""
    project = make_project(docs=[make_doc()])

    paths = [path for _doc, path in project_doc_paths(project, project_dir(project))]

    assert paths == [f"{PROJECTS_DIR}/proyecto-sintetico/docs/guia-de-estilo.md"]


def test_a_doc_without_filename_uses_its_identifier() -> None:
    """No se inventa un nombre: si no hay `filename`, el archivo lleva el id del doc."""
    project = make_project(docs=[make_doc(filename=None)])

    paths = [path for _doc, path in project_doc_paths(project, project_dir(project))]

    assert paths == [f"{PROJECTS_DIR}/proyecto-sintetico/docs/{DOC_1}.md"]


def test_two_projects_whose_name_slugifies_the_same_never_share_a_folder() -> None:
    """Dos nombres distintos pueden dar el mismo slug; ninguno puede pisar al otro."""
    projects = [
        make_project(name="Q3: Ventas"),
        make_project(id=PROJECT_2, name="Q3 / Ventas"),
    ]

    directories = [directory for _project, directory in assign_project_dirs(projects)]

    assert len(set(directories)) == 2
    assert all(directory.startswith(f"{PROJECTS_DIR}/q3-ventas-") for directory in directories)


def test_the_folder_of_each_project_does_not_depend_on_the_order() -> None:
    """Mismo criterio que las memorias: el desempate depende del `id`, no de la posición."""
    projects = [
        make_project(name="Q3: Ventas"),
        make_project(id=PROJECT_2, name="Q3 / Ventas"),
    ]

    def by_id(pairs: list[tuple[Project, str]]) -> dict[str, str]:
        return {project.id: directory for project, directory in pairs}

    assert by_id(assign_project_dirs(projects)) == by_id(
        assign_project_dirs(list(reversed(projects)))
    )


def test_two_docs_whose_filename_slugifies_the_same_never_share_a_file() -> None:
    project = make_project(
        docs=[make_doc(filename="Guía.md"), make_doc(id=DOC_2, filename="guia!.md")]
    )

    paths = [path for _doc, path in project_doc_paths(project, project_dir(project))]

    assert len(set(paths)) == 2
    assert all("/docs/guia-" in path for path in paths)


# --------------------------------------------------------------- cuerpo


def test_the_body_shows_the_name_the_description_and_the_instructions(project: Project) -> None:
    body = frontmatter.loads(render_project(project)[0][1]).content

    assert "# Proyecto Sintético" in body
    assert "Un proyecto de prueba" in body
    assert "Responde siempre en español." in body


def test_ca2_empty_instructions_are_shown_as_empty_and_not_omitted() -> None:
    """Spec 03 CA-2: `""` es un valor del export; la sección se imprime y lo dice."""
    markdown = render_project(make_project(instructions=""))[0][1]

    assert "Instrucciones" in markdown
    assert "vacías" in markdown


def test_instructions_that_the_export_does_not_bring_leave_no_section() -> None:
    """`None` sí es ausencia: no se imprime una sección que hable de algo inexistente."""
    markdown = render_project(make_project(instructions=None))[0][1]

    assert "Instrucciones" not in markdown


def test_instructions_are_inserted_as_markdown_without_escaping() -> None:
    markdown = render_project(make_project(instructions="## Reglas\n\n- **Una**"))[0][1]

    assert "## Reglas" in markdown
    assert "- **Una**" in markdown


# ------------------------------------------------- CA-3 docs sin contenido


def test_ca3_the_project_lists_its_docs_with_a_relative_link() -> None:
    markdown = files(make_project(docs=[make_doc()]))[
        f"{PROJECTS_DIR}/proyecto-sintetico/project.md"
    ]

    assert "docs/guia-de-estilo.md" in markdown
    assert "Guía de estilo.md" in markdown


def test_ca3_a_doc_without_content_says_so_in_its_own_file() -> None:
    """Spec 03 CA-3: nunca vacío en silencio ni contenido inventado."""
    markdown = files(make_project(docs=[make_doc()]))[
        f"{PROJECTS_DIR}/proyecto-sintetico/docs/guia-de-estilo.md"
    ]

    assert DOC_CONTENT_UNAVAILABLE in markdown


def test_ca3_the_table_of_the_project_also_says_that_the_content_is_missing() -> None:
    markdown = files(make_project(docs=[make_doc()]))[
        f"{PROJECTS_DIR}/proyecto-sintetico/project.md"
    ]

    assert "No disponible" in markdown


def test_ca3_a_doc_that_did_bring_content_renders_it_verbatim() -> None:
    """Si un export futuro resuelve el contenido, es Markdown y se inserta sin tocar."""
    content = "# Guía\n\n- **Regla** con `código`\n"
    rendered = files(make_project(docs=[make_doc(content=content)]))

    markdown = rendered[f"{PROJECTS_DIR}/proyecto-sintetico/docs/guia-de-estilo.md"]

    assert content.strip() in markdown
    assert DOC_CONTENT_UNAVAILABLE not in markdown


def test_a_project_without_docs_says_so_instead_of_leaving_an_empty_section(
    project: Project,
) -> None:
    rendered = files(project)

    assert len(rendered) == 1
    markdown = rendered[f"{PROJECTS_DIR}/proyecto-sintetico/project.md"]
    assert "no tiene documentos" in markdown


# ----------------------------------------------------- enlace con conversaciones


def test_a_project_without_linked_conversations_says_so(project: Project) -> None:
    """CA-4: el enlace lo resuelve `convert` desde `conversations`; aquí no hay ninguno."""
    markdown = render_project(project)[0][1]

    assert "Ninguna conversación" in markdown


def test_the_conversations_resolved_by_convert_are_listed() -> None:
    """Cuando `convert` puebla `conversation_ids`, el proyecto las enumera."""
    markdown = render_project(make_project(conversation_ids=["abc-123", "def-456"]))[0][1]

    assert "abc-123" in markdown
    assert "def-456" in markdown


# ----------------------------------------------- CA-10 nada de la corrida


def test_ca10_output_has_no_generation_date_or_tool_version() -> None:
    markdown = "\n".join(text for _path, text in render_project(make_project(docs=[make_doc()])))
    today = datetime.now(tz=UTC).date().isoformat()

    assert today not in markdown
    assert "claude_export_md" not in markdown
    assert "0.1.0" not in markdown


# ------------------------------------------------------ CA-1 determinismo


def test_ca1_two_renders_are_byte_identical() -> None:
    projects = [make_project(docs=[make_doc()]), make_project(id=PROJECT_2, name="Otro")]

    first = render_projects(projects)
    second = render_projects(projects)

    assert first == second
    assert [markdown.encode("utf-8") for _path, markdown in first] == [
        markdown.encode("utf-8") for _path, markdown in second
    ]


def test_render_projects_returns_every_file_of_every_project() -> None:
    rendered = render_projects(
        [make_project(docs=[make_doc(), make_doc(id=DOC_2, filename="b.md")])]
    )

    assert len(rendered) == 3
    assert all(path.endswith(".md") for path, _markdown in rendered)


# --------------------------------------------------------- CA-9 plantillas


def test_ca9_user_template_overrides_the_default(tmp_path: Path, project: Project) -> None:
    (tmp_path / "project.md.j2").write_text("MÍO: {{ title }}\n", encoding="utf-8")

    rendered = render_project(project, build_environment(tmp_path))

    assert rendered[0][1] == "MÍO: Proyecto Sintético\n"


# ------------------------------------------------------------------ snapshot


def test_snapshot_of_a_project_with_docs(snapshot: SnapshotAssertion) -> None:
    projects = [
        make_project(docs=[make_doc(), make_doc(id=DOC_2, filename="notas.md", content="Hola.")]),
        make_project(id=PROJECT_2, name="Otro", description="", instructions=""),
    ]

    assert dict(render_projects(projects)) == snapshot

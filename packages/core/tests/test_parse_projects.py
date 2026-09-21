"""Parser de `projects` (spec 03, sección `projects` CA-1..CA-5 y comunes CA-C1..CA-C5).

Un test por regla. Los fixtures son sintéticos (contenido inventado); el fixture real
anonimizado de `v2026-batched/` solo se usa para comprobar que el parser aguanta la
FORMA del export real, nunca para verificar contenido (está anonimizado a `<str:N>`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from claude_export_md.adapters.parsers import projects as parser
from claude_export_md.adapters.source_folder import FolderSource
from claude_export_md.domain.entities import Project, Report

REAL_FIXTURES = Path(__file__).parent / "fixtures" / "v2026-batched" / "projects"

PROJECT_1 = "11111111-2222-4333-8444-555555555555"
PROJECT_2 = "99999999-8888-4777-8666-555555555555"
CREATOR = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
DOC_1 = "d0c0d0c0-1111-4222-8333-444444444444"


# ------------------------------------------------------------------ utilidades


def parse_folder(root: Path) -> tuple[list[Project], Report]:
    report = Report()
    return list(parser.parse(FolderSource(root), report)), report


def write_project(root: Path, payload: Any, name: str = PROJECT_1, part: int = 0) -> Path:  # noqa: ANN401
    """Escribe un `projects-<part>/projects/<name>.json` sintético dentro de `root`."""
    directory = root / f"projects-{part:03d}" / "projects"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def one_project(**extra: Any) -> dict[str, Any]:
    return {
        "uuid": PROJECT_1,
        "name": "Proyecto Sintético",
        "description": "Un proyecto de prueba",
        "is_private": True,
        "is_starter_project": False,
        "prompt_template": "Responde siempre en español.",
        "created_at": "2026-01-02T03:04:05.000000Z",
        "updated_at": "2026-02-03T04:05:06.000000Z",
        "creator": {"uuid": CREATOR, "full_name": "Persona Sintética"},
        "docs": [],
        **extra,
    }


def projects_extra(root: Path) -> dict[str, Any]:
    """`extra` del primer proyecto de la carpeta (los campos que la entidad no mapea)."""
    projects, _ = parse_folder(root)
    return dict(projects[0].model_extra or {})


def one_doc(**extra: Any) -> dict[str, Any]:
    return {
        "uuid": DOC_1,
        "filename": "guia-de-estilo.md",
        "created_at": "2026-01-05T06:07:08.000000Z",
        **extra,
    }


# ------------------------------------------------- CA-1 un archivo por proyecto


def test_ca1_each_file_is_one_project_not_an_array(tmp_path: Path) -> None:
    """CA-1: el parser itera N archivos; no busca ítems dentro de un array."""
    write_project(tmp_path, one_project(), name=PROJECT_1)
    write_project(tmp_path, one_project(uuid=PROJECT_2, name="Otro"), name=PROJECT_2)

    projects, report = parse_folder(tmp_path)

    assert [project.id for project in projects] == [PROJECT_1, PROJECT_2]
    assert report.errors == []
    assert report.counts == {"projects": 2}


def test_ca1_name_and_description_are_mapped(tmp_path: Path) -> None:
    write_project(tmp_path, one_project())

    projects, _ = parse_folder(tmp_path)

    assert projects[0].name == "Proyecto Sintético"
    assert projects[0].description == "Un proyecto de prueba"
    assert projects[0].created_at is not None
    assert projects[0].updated_at is not None


# ------------------------------------------- CA-2 prompt_template → instructions


def test_ca2_prompt_template_becomes_the_instructions(tmp_path: Path) -> None:
    """CA-2: el *system prompt* del proyecto llega a `Project.instructions`."""
    write_project(tmp_path, one_project())

    projects, _ = parse_folder(tmp_path)

    assert projects[0].instructions == "Responde siempre en español."
    assert "prompt_template" not in (projects[0].model_extra or {})


def test_ca2_an_empty_prompt_template_is_not_treated_as_absent(tmp_path: Path) -> None:
    """CA-2: `""` es un valor del export (instrucciones vacías), no un campo ausente."""
    write_project(tmp_path, one_project(prompt_template=""))

    projects, _ = parse_folder(tmp_path)

    assert projects[0].instructions == ""
    assert projects[0].instructions is not None


def test_a_missing_prompt_template_leaves_instructions_none(tmp_path: Path) -> None:
    """Sin la clave sí hay ausencia: `None` y `""` no significan lo mismo."""
    payload = one_project()
    del payload["prompt_template"]
    write_project(tmp_path, payload)

    projects, _ = parse_folder(tmp_path)

    assert projects[0].instructions is None


# ----------------------------------------------- CA-3 docs[] sin contenido real


def test_ca3_a_doc_only_brings_metadata_so_its_content_is_unavailable(tmp_path: Path) -> None:
    """CA-3: `content=None` significa *el export no trae el texto* (ADR-0005)."""
    write_project(tmp_path, one_project(docs=[one_doc()]))

    projects, _ = parse_folder(tmp_path)

    doc = projects[0].docs[0]
    assert doc.id == DOC_1
    assert doc.filename == "guia-de-estilo.md"
    assert doc.created_at is not None
    assert doc.content is None


def test_ca3_docs_without_content_leave_one_aggregated_warning(tmp_path: Path) -> None:
    """CA-3: nunca en silencio (CLAUDE.md §1.3), pero UNA línea por corrida, no por doc.

    Repetir el mismo mensaje una vez por documento tapaba las advertencias accionables
    de la corrida en el resumen del CLI (mismo criterio que `ORPHAN_PROJECTS_WARNING`).
    """
    write_project(tmp_path, one_project(docs=[one_doc(), one_doc(uuid="otro", filename="b.md")]))
    write_project(
        tmp_path,
        one_project(uuid=PROJECT_2, docs=[one_doc(uuid="c", filename="c.md")]),
        name=PROJECT_2,
    )

    projects, report = parse_folder(tmp_path)

    assert [len(project.docs) for project in projects] == [2, 1]
    assert report.warnings == [
        parser.DOCS_WITHOUT_CONTENT_WARNING.format(
            docs="3 documentos", projects="2 proyectos", verb="llegan"
        )
    ]


def test_ca3_one_single_doc_without_content_is_said_in_singular(tmp_path: Path) -> None:
    """Ni "1 documentos" ni "1 proyectos": el mensaje concuerda (detalle de revisión)."""
    write_project(tmp_path, one_project(docs=[one_doc()]))

    _projects, report = parse_folder(tmp_path)

    assert report.warnings == [
        parser.DOCS_WITHOUT_CONTENT_WARNING.format(
            docs="1 documento", projects="1 proyecto", verb="llega"
        )
    ]


def test_ca3_the_aggregated_warning_only_counts_the_docs_that_survived_the_dedupe(
    tmp_path: Path,
) -> None:
    """Bug de revisión: dos partes con el mismo `uuid` avisaban dos veces por el mismo doc.

    El proyecto repetido se descarta en `parse()` (CA-C1) DESPUÉS de armarse, así que la
    advertencia no puede nacer dentro de `_doc`: nombraría documentos que nunca se
    escriben.
    """
    write_project(tmp_path, one_project(docs=[one_doc()]), part=0)
    write_project(tmp_path, one_project(docs=[one_doc()]), part=1)

    projects, report = parse_folder(tmp_path)

    assert [project.id for project in projects] == [PROJECT_1]
    without_content = [w for w in report.warnings if "contenido" in w]
    assert without_content == [
        parser.DOCS_WITHOUT_CONTENT_WARNING.format(
            docs="1 documento", projects="1 proyecto", verb="llega"
        )
    ]


def test_ca3_a_doc_that_did_bring_content_is_kept_and_not_warned(tmp_path: Path) -> None:
    """Si algún export futuro resuelve el contenido, se usa tal cual y no se avisa."""
    write_project(tmp_path, one_project(docs=[one_doc(content="# Guía\n\nTexto.")]))

    projects, report = parse_folder(tmp_path)

    assert projects[0].docs[0].content == "# Guía\n\nTexto."
    assert report.warnings == []


def test_ca3_a_project_without_docs_has_none_and_does_not_warn(tmp_path: Path) -> None:
    """`docs: []` es lo normal en el export real (2 de 3 proyectos de la muestra)."""
    write_project(tmp_path, one_project(docs=[]))

    projects, report = parse_folder(tmp_path)

    assert projects[0].docs == []
    assert report.warnings == []
    assert report.errors == []


def test_docs_are_emitted_in_the_order_of_the_export(tmp_path: Path) -> None:
    write_project(
        tmp_path,
        one_project(docs=[one_doc(uuid="a", filename="a.md"), one_doc(uuid="b", filename="b.md")]),
    )

    projects, _ = parse_folder(tmp_path)

    assert [doc.id for doc in projects[0].docs] == ["a", "b"]


# ------------------------------------- CA-4 el enlace con conversaciones no es aquí


def test_ca4_the_link_with_conversations_is_not_built_from_the_project_file(
    tmp_path: Path,
) -> None:
    """CA-4: el enlace va al revés (`conversations[].project_uuid`); aquí no hay de dónde."""
    write_project(tmp_path, one_project())

    projects, _ = parse_folder(tmp_path)

    assert projects[0].conversation_ids == []


# --------------------------------------------------- CA-5 creator es un objeto


def test_ca5_only_the_uuid_of_the_creator_is_taken_as_reference(tmp_path: Path) -> None:
    """CA-5: `creator` es `{uuid, full_name}`; la referencia es `creator.uuid`."""
    write_project(tmp_path, one_project())

    projects, _ = parse_folder(tmp_path)

    assert projects[0].creator_id == CREATOR


def test_ca5_the_rest_of_the_creator_is_preserved_without_duplicating_the_uuid(
    tmp_path: Path,
) -> None:
    """El `full_name` no se pierde; el `uuid` no se repite porque ya es `creator_id`."""
    write_project(tmp_path, one_project())

    extra = projects_extra(tmp_path)

    assert extra["creator"] == {"full_name": "Persona Sintética"}


def test_ca5_a_creator_that_is_not_an_object_is_kept_raw_with_a_warning(tmp_path: Path) -> None:
    """CA-5 al revés: no se asume que `creator` sea el uuid plano; se conserva y se avisa."""
    write_project(tmp_path, one_project(creator=CREATOR))

    projects, report = parse_folder(tmp_path)

    assert projects[0].creator_id is None
    assert (projects[0].model_extra or {})["creator_raw"] == CREATOR
    assert any("creator" in warning for warning in report.warnings)


def test_a_project_without_creator_is_still_a_project(tmp_path: Path) -> None:
    """Todo es opcional salvo el identificador (CLAUDE.md §1.3)."""
    payload = one_project()
    del payload["creator"]
    write_project(tmp_path, payload)

    projects, report = parse_folder(tmp_path)

    assert projects[0].creator_id is None
    assert report.warnings == []


def test_a_project_without_the_docs_key_has_no_documents(tmp_path: Path) -> None:
    """Sin la clave `docs` no hay documentos, y eso no es un error."""
    payload = one_project()
    del payload["docs"]
    write_project(tmp_path, payload)

    projects, report = parse_folder(tmp_path)

    assert projects[0].docs == []
    assert report.errors == []


def test_a_creator_object_without_uuid_leaves_no_reference(tmp_path: Path) -> None:
    write_project(tmp_path, one_project(creator={"full_name": "Persona Sintética"}))

    projects, _ = parse_folder(tmp_path)

    assert projects[0].creator_id is None
    assert (projects[0].model_extra or {})["creator"] == {"full_name": "Persona Sintética"}


# ------------------------------------------------------- CA-C2 ítem corrupto


def test_cac2_a_broken_file_is_reported_and_the_run_continues(tmp_path: Path) -> None:
    """CA-C2: un archivo ilegible no detiene la corrida."""
    write_project(tmp_path, one_project(uuid=PROJECT_2), name=PROJECT_2)
    directory = tmp_path / "projects-000" / "projects"
    (directory / f"{PROJECT_1}.json").write_text('{"uuid": "a"', encoding="utf-8")

    projects, report = parse_folder(tmp_path)

    assert [project.id for project in projects] == [PROJECT_2]
    assert len(report.errors) == 1
    assert report.errors[0].category == "projects"
    assert report.errors[0].source_file is not None


def test_cac2_a_project_without_uuid_is_reported_and_skipped(tmp_path: Path) -> None:
    """Sin identificador no hay entidad (CLAUDE.md §1.3: todo opcional salvo el id)."""
    payload = one_project()
    del payload["uuid"]
    write_project(tmp_path, payload)

    projects, report = parse_folder(tmp_path)

    assert projects == []
    assert len(report.errors) == 1
    assert "uuid" in report.errors[0].reason


def test_cac2_a_root_that_is_neither_object_nor_array_is_reported(tmp_path: Path) -> None:
    write_project(tmp_path, "soy una cadena")

    projects, report = parse_folder(tmp_path)

    assert projects == []
    assert len(report.errors) == 1


def test_a_root_array_is_read_as_several_projects_with_a_warning(tmp_path: Path) -> None:
    """Tolerancia al formato legacy (`projects.json` con array): no cero en silencio."""
    write_project(tmp_path, [one_project(), one_project(uuid=PROJECT_2)])

    projects, report = parse_folder(tmp_path)

    assert [project.id for project in projects] == [PROJECT_1, PROJECT_2]
    assert report.errors == []
    assert any("array" in warning for warning in report.warnings)


def test_cac2_an_item_of_an_array_root_that_is_not_an_object_is_reported(tmp_path: Path) -> None:
    write_project(tmp_path, ["no soy un objeto", one_project()])

    projects, report = parse_folder(tmp_path)

    assert [project.id for project in projects] == [PROJECT_1]
    assert [error.item_id for error in report.errors] == ["item[0]"]


def test_cac2_a_doc_that_is_not_an_object_is_reported_and_the_project_survives(
    tmp_path: Path,
) -> None:
    """Un doc con forma rara no borra el proyecto: el resto de sus datos siguen sirviendo."""
    write_project(tmp_path, one_project(docs=["no soy un objeto", one_doc()]))

    projects, report = parse_folder(tmp_path)

    assert [doc.id for doc in projects[0].docs] == [DOC_1]
    assert len(report.errors) == 1
    assert report.errors[0].item_id == f"{PROJECT_1}/docs[0]"


def test_cac2_docs_that_is_not_an_array_is_reported(tmp_path: Path) -> None:
    write_project(tmp_path, one_project(docs={"uuid": DOC_1}))

    projects, report = parse_folder(tmp_path)

    assert projects[0].docs == []
    assert len(report.errors) == 1
    assert "docs" in (report.errors[0].item_id or "")


def test_a_doc_without_uuid_keeps_its_metadata_with_a_synthetic_id(tmp_path: Path) -> None:
    """Perder el nombre del doc por un identificador ausente sería peor que inventarlo.

    Mismo criterio que un mensaje sin `uuid` en `conversations`: id sintético,
    determinista, marcado en `extra` y avisado.
    """
    write_project(tmp_path, one_project(docs=[one_doc(uuid=None)]))

    projects, report = parse_folder(tmp_path)

    doc = projects[0].docs[0]
    assert doc.id == f"{PROJECT_1}#docs[0]"
    assert doc.filename == "guia-de-estilo.md"
    assert (doc.model_extra or {})["synthetic_id"] is True
    assert any("docs[0]" in warning for warning in report.warnings)


def test_a_doc_content_of_an_unexpected_shape_is_kept_as_an_unknown_field(
    tmp_path: Path,
) -> None:
    """No se fuerza el tipo: el valor original queda a la vista y el contenido, ausente."""
    write_project(tmp_path, one_project(docs=[one_doc(content={"texto": "hola"})]))

    projects, report = parse_folder(tmp_path)

    doc = projects[0].docs[0]
    assert doc.content is None
    assert (doc.model_extra or {})["content_raw"] == {"texto": "hola"}
    assert report.warnings != []


def test_a_file_that_is_not_json_is_skipped_with_a_warning(tmp_path: Path) -> None:
    directory = tmp_path / "projects-000" / "projects"
    directory.mkdir(parents=True)
    (directory / "notas.md").write_text("# no soy JSON", encoding="utf-8")

    projects, report = parse_folder(tmp_path)

    assert projects == []
    assert report.warnings != []


def test_oversized_file_is_reported_instead_of_loaded(tmp_path: Path, monkeypatch: Any) -> None:  # noqa: ANN401
    """El techo de `json.load` también aplica aquí (los 32 archivos reales suman 22 KB)."""
    write_project(tmp_path, one_project())
    monkeypatch.setattr(parser, "MAX_JSON_BYTES", 1)

    projects, report = parse_folder(tmp_path)

    assert projects == []
    assert len(report.errors) == 1
    assert "bytes" in report.errors[0].reason


# --------------------------------------------------------- CA-C1 multi-parte


def test_cac1_parts_are_concatenated_without_duplicating(tmp_path: Path) -> None:
    """CA-C1: partes 0..n en orden y sin repetir `uuid`."""
    write_project(tmp_path, one_project(), part=0)
    write_project(tmp_path, one_project(), name=PROJECT_1, part=1)
    write_project(tmp_path, one_project(uuid=PROJECT_2), name=PROJECT_2, part=1)

    projects, report = parse_folder(tmp_path)

    assert [project.id for project in projects] == [PROJECT_1, PROJECT_2]
    assert any(PROJECT_1 in warning for warning in report.warnings)


# ------------------------------------------------ CA-C4 campos desconocidos


def test_cac4_unknown_fields_are_preserved(tmp_path: Path) -> None:
    """`is_private`, `is_starter_project` y cualquier otro campo acaban en `extra`."""
    write_project(tmp_path, one_project(color="azul"))

    extra = projects_extra(tmp_path)

    assert extra["is_private"] is True
    assert extra["is_starter_project"] is False
    assert extra["color"] == "azul"


def test_the_source_file_of_each_project_is_annotated(tmp_path: Path) -> None:
    """El frontmatter obligatorio (spec 04) pide `source_file` y el dominio no ve el disco."""
    write_project(tmp_path, one_project())

    extra = projects_extra(tmp_path)

    assert extra["source_file"] == f"projects-000/projects/{PROJECT_1}.json"


# ------------------------------------------------------------ CA-C5 orden


def test_cac5_parse_sorted_orders_by_date_then_id(tmp_path: Path) -> None:
    """CA-C5: orden canónico por `created_at` y, a igualdad, por `id`."""
    write_project(tmp_path, one_project(created_at="2026-05-05T00:00:00Z"), name=PROJECT_1)
    write_project(
        tmp_path,
        one_project(uuid=PROJECT_2, created_at="2026-01-01T00:00:00Z"),
        name=PROJECT_2,
    )

    report = Report()
    ordered = parser.parse_sorted(FolderSource(tmp_path), report)

    assert [project.id for project in ordered] == [PROJECT_2, PROJECT_1]


def test_cac5_projects_without_date_go_last(tmp_path: Path) -> None:
    """A una fecha ausente no se le inventa un valor: el proyecto va al final."""
    payload = one_project(uuid=PROJECT_2)
    del payload["created_at"]
    write_project(tmp_path, payload, name=PROJECT_2)
    write_project(tmp_path, one_project(), name=PROJECT_1)

    ordered = parser.parse_sorted(FolderSource(tmp_path), Report())

    assert [project.id for project in ordered] == [PROJECT_1, PROJECT_2]


def test_cac5_two_runs_produce_the_same_order(tmp_path: Path) -> None:
    write_project(tmp_path, one_project(), name=PROJECT_1)
    write_project(tmp_path, one_project(uuid=PROJECT_2), name=PROJECT_2)

    first, _ = parse_folder(tmp_path)
    second, _ = parse_folder(tmp_path)

    assert [project.id for project in first] == [project.id for project in second]


# ----------------------------------------------------- forma del export real


def test_the_real_anonymised_export_shape_parses(tmp_path: Path) -> None:
    """Los 3 fixtures reales (anonimizados a `<str:N>`) se parsean: solo la FORMA.

    Cada uno va en su propia carpeta porque el anonimizador en modo estructura sustituye
    TODOS los uuid por `<str:36>`: juntos serían tres proyectos con el mismo id y el
    parser —con razón— se quedaría con el primero.
    """
    samples = sorted(REAL_FIXTURES.glob("sample-*.json"))
    assert len(samples) == 3

    for sample in samples:
        directory = tmp_path / sample.stem / "projects-000" / "projects"
        directory.mkdir(parents=True)
        (directory / sample.name).write_text(sample.read_text(encoding="utf-8"), encoding="utf-8")

        projects, report = parse_folder(tmp_path / sample.stem)

        assert len(projects) == 1
        assert report.errors == []
        assert projects[0].creator_id is not None
        # CA-3: el doc de sample-01 llega sin contenido; los otros dos no traen docs.
        assert all(doc.content is None for doc in projects[0].docs)


def test_the_real_fixture_with_a_doc_warns_that_its_content_is_missing(tmp_path: Path) -> None:
    """CA-3 contra el fixture real: el único doc de la muestra deja su advertencia."""
    sample = REAL_FIXTURES / "sample-01.json"
    directory = tmp_path / "projects-000" / "projects"
    directory.mkdir(parents=True)
    (directory / sample.name).write_text(sample.read_text(encoding="utf-8"), encoding="utf-8")

    projects, report = parse_folder(tmp_path)

    assert len(projects[0].docs) == 1
    assert len(report.warnings) == 1
    assert "contenido" in report.warnings[0]


def test_an_unreadable_date_does_not_invalidate_the_project(tmp_path: Path) -> None:
    """El fixture anonimizado trae `<str:32>` donde iba la fecha: el proyecto sigue valiendo."""
    write_project(tmp_path, one_project(created_at="<str:32>"))

    projects, report = parse_folder(tmp_path)

    assert projects[0].created_at is None
    assert (projects[0].model_extra or {})["created_at_raw"] == "<str:32>"
    assert report.errors == []

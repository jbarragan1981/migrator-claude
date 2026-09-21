"""Parser de `frames` (spec 03, sección `frames` CA-1..CA-3 y comunes CA-C1..CA-C5).

Un test por regla. Los fixtures son sintéticos (contenido inventado); el fixture real
anonimizado de `v2026-batched/` solo se usa para comprobar que el parser aguanta la
FORMA del export real, nunca para verificar contenido (está anonimizado a `<str:N>`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from claude_export_md.adapters.parsers import frames as parser
from claude_export_md.adapters.source_folder import FolderSource
from claude_export_md.domain.entities import Frame, Report

REAL_FIXTURES = Path(__file__).parent / "fixtures" / "v2026-batched" / "frames"

FRAME_1 = "f1f1f1f1-1111-4222-8333-444444444444"
FRAME_2 = "f2f2f2f2-5555-4666-8777-888888888888"
ACCOUNT = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
VERSION_1 = "ver_00000000001"
VERSION_2 = "ver_00000000002"


# ------------------------------------------------------------------ utilidades


def parse_folder(root: Path) -> tuple[list[Frame], Report]:
    report = Report()
    return list(parser.parse(FolderSource(root), report)), report


def write_frame(root: Path, payload: Any, name: str = FRAME_1, part: int = 0) -> Path:  # noqa: ANN401
    """Escribe un `frames-<part>/artifacts/<name>/<name>.json` sintético dentro de `root`."""
    directory = root / f"frames-{part:03d}" / "artifacts" / name
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def one_version(**extra: Any) -> dict[str, Any]:
    return {
        "id": VERSION_1,
        "title": "Informe de ventas Q3",
        "description": "Un documento con el resumen de ventas del trimestre.",
        "created_at": "2026-01-02T03:04:05.000000Z",
        **extra,
    }


def one_frame(**extra: Any) -> dict[str, Any]:
    return {
        "id": FRAME_1,
        "kind": "document",
        "visibility": "private",
        "owner_account": ACCOUNT,
        "updated_at": "2026-02-03T04:05:06.000000Z",
        "active_version": VERSION_1,
        "versions": [one_version()],
        **extra,
    }


def frames_extra(root: Path) -> dict[str, Any]:
    """`extra` del primer artefacto de la carpeta (los campos que la entidad no mapea)."""
    parsed, _ = parse_folder(root)
    return dict(parsed[0].model_extra or {})


# --------------------------------------------- CA-1 un archivo por artefacto


def test_ca1_each_file_is_one_frame_not_an_array(tmp_path: Path) -> None:
    """CA-1: el parser itera N archivos de `frames-000/artifacts/`, uno por artefacto."""
    write_frame(tmp_path, one_frame(), name=FRAME_1)
    write_frame(tmp_path, one_frame(id=FRAME_2), name=FRAME_2)

    parsed, report = parse_folder(tmp_path)

    assert [frame.id for frame in parsed] == [FRAME_1, FRAME_2]
    assert report.errors == []
    assert report.counts == {"frames": 2}


def test_ca1_the_observed_fields_are_mapped(tmp_path: Path) -> None:
    """CA-1: `id`, `kind`, `visibility`, `owner_account`, `updated_at` y `active_version`."""
    write_frame(tmp_path, one_frame())

    parsed, _ = parse_folder(tmp_path)

    frame = parsed[0]
    assert frame.id == FRAME_1
    assert frame.kind == "document"
    assert frame.visibility == "private"
    assert frame.owner_account == ACCOUNT
    assert frame.updated_at is not None
    assert frame.active_version == VERSION_1


def test_ca1_the_versions_are_preserved_with_their_metadata(tmp_path: Path) -> None:
    write_frame(tmp_path, one_frame())

    parsed, _ = parse_folder(tmp_path)

    version = parsed[0].versions[0]
    assert version.id == VERSION_1
    assert version.title == "Informe de ventas Q3"
    assert version.description == "Un documento con el resumen de ventas del trimestre."
    assert version.created_at is not None


# ------------------------------------------ CA-2 el contenido real no viaja


def test_ca2_the_payload_keeps_the_whole_json_as_it_came(tmp_path: Path) -> None:
    """CA-2: ningún campo trae el contenido; hasta saber dónde vive, no se pierde nada."""
    raw = one_frame(color="azul")
    write_frame(tmp_path, raw)

    parsed, _ = parse_folder(tmp_path)

    assert parsed[0].payload == raw


def test_ca2_no_observed_field_brings_the_content_of_the_artifact(tmp_path: Path) -> None:
    """CA-2: la entidad no inventa un campo de contenido que el export no trae."""
    write_frame(tmp_path, one_frame())

    parsed, _ = parse_folder(tmp_path)

    assert not {"content", "body", "code", "text"} & set(parsed[0].payload)
    assert "content" not in Frame.model_fields


def test_ca2_frames_without_content_leave_one_aggregated_warning(tmp_path: Path) -> None:
    """Nunca en silencio (CLAUDE.md §1.3), pero UNA línea por corrida, no por artefacto.

    Mismo criterio que `projects.docs[]` y que `ORPHAN_PROJECTS_WARNING`: repetir el
    mismo mensaje 17 veces tapaba las advertencias accionables en el resumen del CLI.
    """
    write_frame(tmp_path, one_frame(), name=FRAME_1)
    write_frame(tmp_path, one_frame(id=FRAME_2), name=FRAME_2)

    _parsed, report = parse_folder(tmp_path)

    assert report.warnings == [
        parser.FRAMES_WITHOUT_CONTENT_WARNING.format(frames="2 artefactos", verb="llegan")
    ]


def test_ca2_one_single_frame_without_content_is_said_in_singular(tmp_path: Path) -> None:
    write_frame(tmp_path, one_frame())

    _parsed, report = parse_folder(tmp_path)

    assert report.warnings == [
        parser.FRAMES_WITHOUT_CONTENT_WARNING.format(frames="1 artefacto", verb="llega")
    ]


def test_ca2_the_aggregated_warning_only_counts_the_frames_that_survived_the_dedupe(
    tmp_path: Path,
) -> None:
    """Bug de revisión: dos partes con el mismo `id` avisaban dos veces del mismo artefacto.

    El repetido se descarta en `parse()` (CA-C1) DESPUÉS de armarse, así que la
    advertencia no puede nacer dentro de `_frame`: hablaría de un archivo que no existe.
    """
    write_frame(tmp_path, one_frame(), part=0)
    write_frame(tmp_path, one_frame(), part=1)

    parsed, report = parse_folder(tmp_path)

    assert [frame.id for frame in parsed] == [FRAME_1]
    without_content = [w for w in report.warnings if "contenido" in w]
    assert without_content == [
        parser.FRAMES_WITHOUT_CONTENT_WARNING.format(frames="1 artefacto", verb="llega")
    ]


# ----------------------------------------------- CA-3 versions[] y la activa


def test_ca3_a_frame_with_several_versions_keeps_them_in_order(tmp_path: Path) -> None:
    """CA-3: se observaron de 1 a 3 versiones; van todas y en el orden del export."""
    versions = [
        one_version(id=VERSION_1),
        one_version(id=VERSION_2, title="Informe de ventas Q3 (v2)"),
        one_version(id="ver_00000000003", title="Informe de ventas Q3 (v3)"),
    ]
    write_frame(tmp_path, one_frame(versions=versions, active_version=VERSION_2))

    parsed, report = parse_folder(tmp_path)

    assert [version.id for version in parsed[0].versions] == [
        VERSION_1,
        VERSION_2,
        "ver_00000000003",
    ]
    assert report.errors == []


def test_ca3_the_active_version_is_resolved_against_the_ids_of_versions(tmp_path: Path) -> None:
    """CA-3: `active_version` referencia uno de los `versions[].id`."""
    write_frame(
        tmp_path,
        one_frame(
            versions=[one_version(id=VERSION_1), one_version(id=VERSION_2, title="Segunda")],
            active_version=VERSION_2,
        ),
    )

    parsed, report = parse_folder(tmp_path)

    active = parsed[0].active()
    assert active is not None
    assert active.id == VERSION_2
    assert active.title == "Segunda"
    assert [w for w in report.warnings if "active_version" in w] == []


def test_ca3_an_active_version_that_matches_nothing_is_a_warning_not_an_exception(
    tmp_path: Path,
) -> None:
    """CA-3 explícito: se tolera que no coincida; el artefacto se emite igual."""
    write_frame(tmp_path, one_frame(active_version="ver_99999999999"))

    parsed, report = parse_folder(tmp_path)

    assert len(parsed) == 1
    assert parsed[0].active_version == "ver_99999999999"
    assert parsed[0].active() is None
    assert report.errors == []
    assert any("active_version" in warning for warning in report.warnings)


def test_a_frame_without_active_version_is_not_warned_about(tmp_path: Path) -> None:
    """Sin `active_version` no hay nada que no coincida: no se avisa de una ausencia."""
    payload = one_frame()
    del payload["active_version"]
    write_frame(tmp_path, payload)

    parsed, report = parse_folder(tmp_path)

    assert parsed[0].active_version is None
    assert parsed[0].active() is None
    assert [w for w in report.warnings if "active_version" in w] == []


def test_an_active_version_of_an_unexpected_shape_is_kept_raw_with_a_warning(
    tmp_path: Path,
) -> None:
    """No se fuerza el tipo: el valor original queda a la vista, como `creator_raw`."""
    write_frame(tmp_path, one_frame(active_version={"id": VERSION_1}))

    parsed, report = parse_folder(tmp_path)

    assert parsed[0].active_version is None
    assert (parsed[0].model_extra or {})["active_version_raw"] == {"id": VERSION_1}
    assert any("active_version" in warning for warning in report.warnings)


def test_a_frame_without_versions_is_still_a_frame(tmp_path: Path) -> None:
    """La muestra siempre traía versiones, pero un array vacío no invalida el artefacto."""
    write_frame(tmp_path, one_frame(versions=[], active_version=None))

    parsed, report = parse_folder(tmp_path)

    assert parsed[0].versions == []
    assert report.errors == []


def test_a_frame_without_the_versions_key_has_no_versions(tmp_path: Path) -> None:
    """Sin la clave `versions` no hay versiones, y eso no es un error (CLAUDE.md §1.3)."""
    payload = one_frame()
    del payload["versions"]
    write_frame(tmp_path, payload)

    parsed, report = parse_folder(tmp_path)

    assert parsed[0].versions == []
    assert report.errors == []
    # La `active_version` que ya no puede coincidir con nada sí se avisa (CA-3).
    assert any("active_version" in warning for warning in report.warnings)


def test_a_version_without_id_keeps_its_metadata_with_a_synthetic_id(tmp_path: Path) -> None:
    """Mismo criterio que un doc sin `uuid`: perder el título sería peor que dar un id."""
    write_frame(tmp_path, one_frame(versions=[one_version(id=None)]))

    parsed, report = parse_folder(tmp_path)

    version = parsed[0].versions[0]
    assert version.id == f"{FRAME_1}#versions[0]"
    assert version.title == "Informe de ventas Q3"
    assert (version.model_extra or {})["synthetic_id"] is True
    assert any("versions[0]" in warning for warning in report.warnings)


def test_unknown_fields_of_a_version_are_preserved(tmp_path: Path) -> None:
    write_frame(tmp_path, one_frame(versions=[one_version(author="Claude")]))

    parsed, _ = parse_folder(tmp_path)

    assert (parsed[0].versions[0].model_extra or {})["author"] == "Claude"


# --------------------------------------------------------- CA-C2 ítem corrupto


def test_cac2_a_broken_file_is_reported_and_the_run_continues(tmp_path: Path) -> None:
    """CA-C2: un archivo ilegible no detiene la corrida."""
    write_frame(tmp_path, one_frame(id=FRAME_2), name=FRAME_2)
    directory = tmp_path / "frames-000" / "artifacts" / FRAME_1
    directory.mkdir(parents=True)
    (directory / f"{FRAME_1}.json").write_text('{"id": "a"', encoding="utf-8")

    parsed, report = parse_folder(tmp_path)

    assert [frame.id for frame in parsed] == [FRAME_2]
    assert len(report.errors) == 1
    assert report.errors[0].category == "frames"
    assert report.errors[0].source_file is not None


def test_cac2_a_frame_without_id_is_reported_and_skipped(tmp_path: Path) -> None:
    """Sin identificador no hay entidad (CLAUDE.md §1.3: todo opcional salvo el id)."""
    payload = one_frame()
    del payload["id"]
    write_frame(tmp_path, payload)

    parsed, report = parse_folder(tmp_path)

    assert parsed == []
    assert len(report.errors) == 1
    assert "id" in report.errors[0].reason


def test_cac2_a_root_that_is_neither_object_nor_array_is_reported(tmp_path: Path) -> None:
    write_frame(tmp_path, "soy una cadena")

    parsed, report = parse_folder(tmp_path)

    assert parsed == []
    assert len(report.errors) == 1


def test_a_root_array_is_read_as_several_frames_with_a_warning(tmp_path: Path) -> None:
    """Misma tolerancia que en `projects`: no devolver cero artefactos en silencio."""
    write_frame(tmp_path, [one_frame(), one_frame(id=FRAME_2)])

    parsed, report = parse_folder(tmp_path)

    assert [frame.id for frame in parsed] == [FRAME_1, FRAME_2]
    assert report.errors == []
    assert any("array" in warning for warning in report.warnings)


def test_cac2_an_item_of_an_array_root_that_is_not_an_object_is_reported(tmp_path: Path) -> None:
    write_frame(tmp_path, ["no soy un objeto", one_frame()])

    parsed, report = parse_folder(tmp_path)

    assert [frame.id for frame in parsed] == [FRAME_1]
    assert [error.item_id for error in report.errors] == ["item[0]"]


def test_cac2_a_version_that_is_not_an_object_is_reported_and_the_frame_survives(
    tmp_path: Path,
) -> None:
    """Una versión con forma rara no borra el artefacto: el resto sigue sirviendo."""
    write_frame(tmp_path, one_frame(versions=["no soy un objeto", one_version()]))

    parsed, report = parse_folder(tmp_path)

    assert [version.id for version in parsed[0].versions] == [VERSION_1]
    assert len(report.errors) == 1
    assert report.errors[0].item_id == f"{FRAME_1}/versions[0]"


def test_cac2_versions_that_is_not_an_array_is_reported(tmp_path: Path) -> None:
    write_frame(tmp_path, one_frame(versions={"id": VERSION_1}))

    parsed, report = parse_folder(tmp_path)

    assert parsed[0].versions == []
    assert len(report.errors) == 1
    assert "versions" in (report.errors[0].item_id or "")


def test_a_file_that_is_not_json_is_skipped_with_a_warning(tmp_path: Path) -> None:
    directory = tmp_path / "frames-000" / "artifacts" / FRAME_1
    directory.mkdir(parents=True)
    (directory / "notas.md").write_text("# no soy JSON", encoding="utf-8")

    parsed, report = parse_folder(tmp_path)

    assert parsed == []
    assert report.warnings != []


def test_oversized_file_is_reported_instead_of_loaded(tmp_path: Path, monkeypatch: Any) -> None:  # noqa: ANN401
    """El techo de `json.load` también aplica aquí (los 17 archivos reales suman 11 KB)."""
    write_frame(tmp_path, one_frame())
    monkeypatch.setattr(parser, "MAX_JSON_BYTES", 1)

    parsed, report = parse_folder(tmp_path)

    assert parsed == []
    assert len(report.errors) == 1
    assert "bytes" in report.errors[0].reason


# --------------------------------------------------------- CA-C1 multi-parte


def test_cac1_parts_are_concatenated_without_duplicating(tmp_path: Path) -> None:
    """CA-C1: partes 0..n en orden y sin repetir `id`."""
    write_frame(tmp_path, one_frame(), part=0)
    write_frame(tmp_path, one_frame(), name=FRAME_1, part=1)
    write_frame(tmp_path, one_frame(id=FRAME_2), name=FRAME_2, part=1)

    parsed, report = parse_folder(tmp_path)

    assert [frame.id for frame in parsed] == [FRAME_1, FRAME_2]
    assert any(FRAME_1 in warning for warning in report.warnings)


# ------------------------------------------------ CA-C4 campos desconocidos


def test_cac4_unknown_fields_are_preserved(tmp_path: Path) -> None:
    """Un campo que hoy no reconocemos acaba en `extra` y de ahí al frontmatter."""
    write_frame(tmp_path, one_frame(color="azul"))

    extra = frames_extra(tmp_path)

    assert extra["color"] == "azul"


def test_the_source_file_of_each_frame_is_annotated(tmp_path: Path) -> None:
    """El frontmatter obligatorio (spec 04) pide `source_file` y el dominio no ve el disco."""
    write_frame(tmp_path, one_frame())

    extra = frames_extra(tmp_path)

    assert extra["source_file"] == f"frames-000/artifacts/{FRAME_1}/{FRAME_1}.json"


# ------------------------------------------------------------ CA-C5 orden


def test_cac5_parse_sorted_orders_by_updated_at_then_id(tmp_path: Path) -> None:
    """CA-C5: el artefacto no trae `created_at` propio; el orden canónico es `updated_at`."""
    write_frame(tmp_path, one_frame(updated_at="2026-05-05T00:00:00Z"), name=FRAME_1)
    write_frame(tmp_path, one_frame(id=FRAME_2, updated_at="2026-01-01T00:00:00Z"), name=FRAME_2)

    ordered = parser.parse_sorted(FolderSource(tmp_path), Report())

    assert [frame.id for frame in ordered] == [FRAME_2, FRAME_1]


def test_cac5_frames_without_date_go_last(tmp_path: Path) -> None:
    """A una fecha ausente no se le inventa un valor: el artefacto va al final."""
    payload = one_frame(id=FRAME_2)
    del payload["updated_at"]
    write_frame(tmp_path, payload, name=FRAME_2)
    write_frame(tmp_path, one_frame(), name=FRAME_1)

    ordered = parser.parse_sorted(FolderSource(tmp_path), Report())

    assert [frame.id for frame in ordered] == [FRAME_1, FRAME_2]


def test_cac5_two_frames_with_the_same_date_are_ordered_by_id(tmp_path: Path) -> None:
    write_frame(tmp_path, one_frame(id=FRAME_2), name=FRAME_2)
    write_frame(tmp_path, one_frame(), name=FRAME_1)

    ordered = parser.parse_sorted(FolderSource(tmp_path), Report())

    assert [frame.id for frame in ordered] == [FRAME_1, FRAME_2]


def test_cac5_two_runs_produce_the_same_order(tmp_path: Path) -> None:
    write_frame(tmp_path, one_frame(), name=FRAME_1)
    write_frame(tmp_path, one_frame(id=FRAME_2), name=FRAME_2)

    first, _ = parse_folder(tmp_path)
    second, _ = parse_folder(tmp_path)

    assert [frame.id for frame in first] == [frame.id for frame in second]


# ----------------------------------------------------- forma del export real


def test_the_real_anonymised_export_shape_parses(tmp_path: Path) -> None:
    """Los 3 fixtures reales (anonimizados a `<str:N>`) se parsean: solo la FORMA.

    Cada uno va en su propia carpeta porque el anonimizador en modo estructura sustituye
    TODOS los uuid por `<str:36>`: juntos serían tres artefactos con el mismo id y el
    parser —con razón— se quedaría con el primero.
    """
    samples = sorted(REAL_FIXTURES.glob("sample-*.json"))
    assert len(samples) == 3

    for sample in samples:
        directory = tmp_path / sample.stem / "frames-000" / "artifacts" / sample.stem
        directory.mkdir(parents=True)
        (directory / sample.name).write_text(sample.read_text(encoding="utf-8"), encoding="utf-8")

        parsed, report = parse_folder(tmp_path / sample.stem)

        assert len(parsed) == 1
        assert report.errors == []
        assert parsed[0].kind is not None
        assert parsed[0].visibility is not None
        assert parsed[0].versions != []
        # CA-2: ninguna versión del export real trae el contenido del artefacto.
        assert parsed[0].payload != {}


def test_the_real_fixture_with_three_versions_keeps_the_three(tmp_path: Path) -> None:
    """CA-3 contra el fixture real: `sample-02` es el artefacto de 3 versiones."""
    sample = REAL_FIXTURES / "sample-02.json"
    directory = tmp_path / "frames-000" / "artifacts" / sample.stem
    directory.mkdir(parents=True)
    (directory / sample.name).write_text(sample.read_text(encoding="utf-8"), encoding="utf-8")

    parsed, _report = parse_folder(tmp_path)

    assert len(parsed[0].versions) == 3


def test_an_unreadable_date_does_not_invalidate_the_frame(tmp_path: Path) -> None:
    """El fixture anonimizado trae `<str:25>` donde iba la fecha: el artefacto sigue valiendo."""
    write_frame(tmp_path, one_frame(updated_at="<str:25>"))

    parsed, report = parse_folder(tmp_path)

    assert parsed[0].updated_at is None
    assert (parsed[0].model_extra or {})["updated_at_raw"] == "<str:25>"
    assert report.errors == []

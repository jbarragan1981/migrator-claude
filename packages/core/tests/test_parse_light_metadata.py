"""Parser de `light_metadata` (spec 03, sección `light_metadata` CA-1..CA-3 y CA-C1..CA-C5).

Un test por regla. Los fixtures son sintéticos (contenido inventado); el fixture real
anonimizado de `v2026-batched/` solo se usa para comprobar que el parser no se rompe con
la FORMA del export real, nunca para verificar contenido (está anonimizado a `<str:N>`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from claude_export_md.adapters.parsers import light_metadata as parser
from claude_export_md.adapters.source_folder import FolderSource
from claude_export_md.domain.entities import Account, Report

REAL_FIXTURE = (
    Path(__file__).parent / "fixtures" / "v2026-batched" / "light_metadata" / "sample-01.json"
)

ACCOUNT_1 = "11111111-2222-4333-8444-555555555555"
ACCOUNT_2 = "99999999-8888-4777-8666-555555555555"


# ------------------------------------------------------------------ utilidades


def parse_folder(root: Path) -> tuple[list[Account], Report]:
    report = Report()
    return list(parser.parse(FolderSource(root), report)), report


def write_light_metadata(root: Path, payload: Any, part: int = 0) -> Path:  # noqa: ANN401
    """Escribe un `light_metadata-<part>/light_metadata.json` sintético dentro de `root`."""
    directory = root / f"light_metadata-{part:03d}"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "light_metadata.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def one_account(**extra: Any) -> dict[str, Any]:
    return {
        "email_address": "persona@example.com",
        "full_name": "Persona Sintética",
        "uuid": ACCOUNT_1,
        "verified_phone_number": None,
        **extra,
    }


# ----------------------------------------------------------- CA-1 mapeo directo


def test_ca1_maps_uuid_email_and_full_name(tmp_path: Path) -> None:
    """CA-1: `id=uuid`, `email=email_address`, `display_name=full_name`."""
    write_light_metadata(tmp_path, [one_account()])

    accounts, report = parse_folder(tmp_path)

    assert len(accounts) == 1
    assert accounts[0].id == ACCOUNT_1
    assert accounts[0].email == "persona@example.com"
    assert accounts[0].display_name == "Persona Sintética"
    assert report.errors == []
    assert report.counts == {"light_metadata": 1}


def test_settings_are_taken_when_the_export_brings_them(tmp_path: Path) -> None:
    """`settings` existe en la entidad; si el export lo trae, se mapea (no a `extra`)."""
    write_light_metadata(tmp_path, [one_account(settings={"locale": "es-CO"})])

    accounts, _ = parse_folder(tmp_path)

    assert accounts[0].settings == {"locale": "es-CO"}
    assert "settings" not in (accounts[0].model_extra or {})


def test_settings_of_an_unexpected_shape_are_kept_as_an_unknown_field(tmp_path: Path) -> None:
    """Si `settings` no es un objeto no se fuerza: queda en `extra.settings_raw` y se avisa."""
    write_light_metadata(tmp_path, [one_account(settings="dark")])

    accounts, report = parse_folder(tmp_path)

    assert accounts[0].settings == {}
    assert (accounts[0].model_extra or {})["settings_raw"] == "dark"
    assert report.warnings != []


def test_a_field_that_is_not_text_does_not_invalidate_the_account(tmp_path: Path) -> None:
    """`email_address` con forma rara no borra la cuenta: el campo queda `None`."""
    write_light_metadata(tmp_path, [one_account(email_address=42, full_name=None)])

    accounts, _ = parse_folder(tmp_path)

    assert accounts[0].email is None
    assert accounts[0].display_name is None
    assert accounts[0].id == ACCOUNT_1


# -------------------------------------------- CA-2 teléfono y credenciales


def test_ca2_null_phone_number_is_preserved_as_a_profile_field(tmp_path: Path) -> None:
    """CA-2: `verified_phone_number` null se conserva; no se excluye por parecer sensible."""
    write_light_metadata(tmp_path, [one_account()])

    accounts, _ = parse_folder(tmp_path)

    extra = accounts[0].model_extra or {}
    assert "verified_phone_number" in extra
    assert extra["verified_phone_number"] is None


def test_ca2_a_real_phone_number_is_preserved_too(tmp_path: Path) -> None:
    """CA-2: un teléfono verificado es un dato de perfil, no un secreto."""
    write_light_metadata(tmp_path, [one_account(verified_phone_number="+57 300 000 0000")])

    accounts, _ = parse_folder(tmp_path)

    assert (accounts[0].model_extra or {})["verified_phone_number"] == "+57 300 000 0000"


def test_ca2_a_field_that_looks_like_a_credential_never_reaches_the_entity(
    tmp_path: Path,
) -> None:
    """CA-2: la regla general sí se aplica a lo que parece token/credencial."""
    write_light_metadata(
        tmp_path,
        [one_account(api_token="sk-secreto", session_cookie="abc", Authorization="Bearer x")],
    )

    accounts, report = parse_folder(tmp_path)

    extra = accounts[0].model_extra or {}
    assert extra["api_token"] == parser.REDACTED
    assert extra["session_cookie"] == parser.REDACTED
    assert extra["Authorization"] == parser.REDACTED
    assert "sk-secreto" not in json.dumps(accounts[0].model_dump())
    # El nombre de la clave sí se nombra (no es el secreto) para que el usuario lo sepa.
    assert any("api_token" in warning for warning in report.warnings)


def test_a_field_that_only_sounds_like_a_credential_is_kept(tmp_path: Path) -> None:
    """`author` contiene "auth" y no es una credencial: no se toca."""
    write_light_metadata(tmp_path, [one_account(author="Persona Sintética")])

    accounts, _ = parse_folder(tmp_path)

    assert (accounts[0].model_extra or {})["author"] == "Persona Sintética"


# ------------------------------------------------- CA-3 más de un ítem


def test_ca3_an_array_with_more_than_one_item_yields_every_account(tmp_path: Path) -> None:
    """CA-3: no se asume longitud 1; el array se itera entero."""
    write_light_metadata(
        tmp_path,
        [one_account(), one_account(uuid=ACCOUNT_2, email_address="otra@example.com")],
    )

    accounts, report = parse_folder(tmp_path)

    assert [account.id for account in accounts] == [ACCOUNT_1, ACCOUNT_2]
    assert report.counts == {"light_metadata": 2}


def test_ca3_an_empty_array_is_not_an_error(tmp_path: Path) -> None:
    """Cero cuentas es una salida válida (no hay nada que convertir), no un fallo."""
    write_light_metadata(tmp_path, [])

    accounts, report = parse_folder(tmp_path)

    assert accounts == []
    assert report.errors == []


def test_a_lone_object_is_read_as_a_single_account(tmp_path: Path) -> None:
    """Tolerancia a esquema: si la raíz es el objeto suelto, se trata como un array de 1."""
    write_light_metadata(tmp_path, one_account())

    accounts, report = parse_folder(tmp_path)

    assert [account.id for account in accounts] == [ACCOUNT_1]
    assert report.errors == []
    assert any("objeto" in warning for warning in report.warnings)


# ------------------------------------------------------- CA-C2 ítem corrupto


def test_cac2_broken_json_is_reported_and_the_run_continues(tmp_path: Path) -> None:
    directory = tmp_path / "light_metadata-000"
    directory.mkdir(parents=True)
    (directory / "light_metadata.json").write_text('[{"uuid": "a"', encoding="utf-8")

    accounts, report = parse_folder(tmp_path)

    assert accounts == []
    assert len(report.errors) == 1
    assert report.errors[0].category == "light_metadata"


def test_cac2_an_item_that_is_not_an_object_is_reported(tmp_path: Path) -> None:
    write_light_metadata(tmp_path, ["no soy un objeto", one_account()])

    accounts, report = parse_folder(tmp_path)

    assert [account.id for account in accounts] == [ACCOUNT_1]
    assert [error.item_id for error in report.errors] == ["item[0]"]


def test_cac2_an_item_without_uuid_is_reported_and_skipped(tmp_path: Path) -> None:
    """Sin identificador no hay entidad (CLAUDE.md §1.3: todo opcional salvo el id)."""
    write_light_metadata(tmp_path, [{"email_address": "persona@example.com"}])

    accounts, report = parse_folder(tmp_path)

    assert accounts == []
    assert len(report.errors) == 1
    assert "uuid" in report.errors[0].reason


def test_cac2_a_root_that_is_neither_array_nor_object_is_reported(tmp_path: Path) -> None:
    write_light_metadata(tmp_path, "soy una cadena")

    accounts, report = parse_folder(tmp_path)

    assert accounts == []
    assert len(report.errors) == 1


def test_a_file_that_is_not_json_is_skipped_with_a_warning(tmp_path: Path) -> None:
    directory = tmp_path / "light_metadata-000"
    directory.mkdir(parents=True)
    (directory / "perfil.md").write_text("# no soy JSON", encoding="utf-8")

    accounts, report = parse_folder(tmp_path)

    assert accounts == []
    assert report.warnings != []


def test_oversized_file_is_reported_instead_of_loaded(tmp_path: Path, monkeypatch: Any) -> None:  # noqa: ANN401
    """El techo de `json.load` también aplica aquí, aunque el archivo real pese 152 bytes."""
    write_light_metadata(tmp_path, [one_account()])
    monkeypatch.setattr(parser, "MAX_JSON_BYTES", 1)

    accounts, report = parse_folder(tmp_path)

    assert accounts == []
    assert len(report.errors) == 1
    assert "bytes" in report.errors[0].reason


# --------------------------------------------------------- CA-C1 multi-parte


def test_cac1_parts_are_concatenated_without_duplicating(tmp_path: Path) -> None:
    """CA-C1: partes 0..n en orden y sin repetir `uuid`."""
    write_light_metadata(tmp_path, [one_account()], part=0)
    write_light_metadata(
        tmp_path,
        [one_account(), one_account(uuid=ACCOUNT_2)],
        part=1,
    )

    accounts, report = parse_folder(tmp_path)

    assert [account.id for account in accounts] == [ACCOUNT_1, ACCOUNT_2]
    assert any(ACCOUNT_1 in warning for warning in report.warnings)


# ------------------------------------------------ CA-C4 campos desconocidos


def test_cac4_unknown_fields_are_preserved(tmp_path: Path) -> None:
    write_light_metadata(tmp_path, [one_account(has_claude_pro=True, organization=None)])

    accounts, _ = parse_folder(tmp_path)

    extra = accounts[0].model_extra or {}
    assert extra["has_claude_pro"] is True
    assert extra["organization"] is None


def test_the_source_file_of_each_account_is_annotated(tmp_path: Path) -> None:
    """El frontmatter obligatorio (spec 04) pide `source_file` y el dominio no ve el disco."""
    write_light_metadata(tmp_path, [one_account()])

    accounts, _ = parse_folder(tmp_path)

    assert (accounts[0].model_extra or {})["source_file"] == (
        "light_metadata-000/light_metadata.json"
    )


# ------------------------------------------------------------ CA-C5 orden


def test_cac5_two_runs_produce_the_same_order(tmp_path: Path) -> None:
    write_light_metadata(
        tmp_path,
        [one_account(uuid=ACCOUNT_2), one_account()],
    )

    first, _ = parse_folder(tmp_path)
    second, _ = parse_folder(tmp_path)

    assert [account.id for account in first] == [account.id for account in second]
    assert [account.id for account in first] == [ACCOUNT_2, ACCOUNT_1]


# ----------------------------------------------------- forma del export real


def test_the_real_anonymised_export_shape_parses(tmp_path: Path) -> None:
    """El fixture real (anonimizado a `<str:N>`) se parsea sin errores: solo la FORMA."""
    directory = tmp_path / "light_metadata-000"
    directory.mkdir(parents=True)
    (directory / "light_metadata.json").write_text(
        REAL_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8"
    )

    accounts, report = parse_folder(tmp_path)

    assert len(accounts) == 1
    assert report.errors == []
    assert (accounts[0].model_extra or {})["verified_phone_number"] is None

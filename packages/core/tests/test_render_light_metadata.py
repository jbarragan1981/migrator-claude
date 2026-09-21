"""Render Markdown de `light_metadata` → `account/account.md` (spec 04, CA-1, CA-2, CA-9, CA-10).

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

from claude_export_md.domain.entities import Account
from claude_export_md.rendering.render import (
    ACCOUNT_PATH,
    account_output_path,
    account_path_warnings,
    account_title,
    assign_account_paths,
    build_environment,
    render_account,
    render_accounts,
)

ACCOUNT_1 = "11111111-2222-4333-8444-555555555555"
ACCOUNT_2 = "99999999-8888-4777-8666-555555555555"


def make_account(**values: Any) -> Account:
    return Account.model_validate(
        {
            "id": ACCOUNT_1,
            "email": "persona@example.com",
            "display_name": "Persona Sintética",
            "verified_phone_number": None,
            "source_file": "light_metadata-000/light_metadata.json",
            **values,
        }
    )


@pytest.fixture
def account() -> Account:
    return make_account()


def meta(markdown: str) -> dict[str, Any]:
    """Frontmatter ya parseado. `python-frontmatter` tipa los valores como `object`."""
    return cast(dict[str, Any], frontmatter.loads(markdown).metadata)


# --------------------------------------------------------- CA-2 frontmatter


def test_ca2_frontmatter_is_valid_and_has_the_required_fields(account: Account) -> None:
    """CA-2: parseable con `python-frontmatter` y con los campos obligatorios."""
    metadata = meta(render_account(account))

    assert set(metadata) >= {
        "id",
        "type",
        "title",
        "created_at",
        "updated_at",
        "source_file",
        "tags",
    }
    assert metadata["type"] == "account"
    assert metadata["id"] == ACCOUNT_1
    assert metadata["source_file"] == "light_metadata-000/light_metadata.json"
    assert metadata["tags"] == ["account"]


def test_the_export_brings_no_dates_for_the_account(account: Account) -> None:
    """`light_metadata` no trae fechas: se emiten en null antes que inventarlas."""
    metadata = meta(render_account(account))

    assert metadata["created_at"] is None
    assert metadata["updated_at"] is None


def test_unknown_fields_are_visible_under_extra(account: Account) -> None:
    metadata = meta(render_account(account))

    assert metadata["extra"]["verified_phone_number"] is None
    assert "source_file" not in metadata["extra"]


def test_an_awkward_display_name_does_not_break_the_yaml() -> None:
    """Un nombre con `:`, comillas y saltos de línea sigue siendo YAML válido."""
    markdown = render_account(make_account(display_name='a: "b"\nc'))

    assert meta(markdown)["title"] == 'a: "b"\nc'


# ------------------------------------------------------------------ título


def test_title_is_the_display_name(account: Account) -> None:
    assert account_title(account) == "Persona Sintética"


def test_title_falls_back_to_the_email_and_then_to_the_id() -> None:
    """Sin nombre se usa lo siguiente más legible; nunca un título inventado."""
    assert account_title(make_account(display_name=None)) == "persona@example.com"
    assert account_title(make_account(display_name="", email="")) == ACCOUNT_1


# ------------------------------------------------------- ruta de salida


def test_a_single_account_goes_to_the_fixed_path(account: Account) -> None:
    """CLAUDE.md §5: `account/account.md`, la única ruta fija del árbol."""
    assert ACCOUNT_PATH == "account/account.md"
    assert assign_account_paths([account]) == [(account, ACCOUNT_PATH)]
    assert account_path_warnings([account]) == []


def test_more_than_one_account_never_uses_the_fixed_path() -> None:
    """CA-3: con varias cuentas ninguna se queda `account.md` y ninguna pisa a otra."""
    accounts = [make_account(), make_account(id=ACCOUNT_2)]

    assigned = assign_account_paths(accounts)

    paths = [path for _account, path in assigned]
    assert ACCOUNT_PATH not in paths
    assert len(set(paths)) == 2
    assert all(path.startswith("account/account-") for path in paths)


def test_the_name_of_each_account_file_does_not_depend_on_the_order() -> None:
    """Mismo espíritu que las memorias: el desempate depende del `id`, no de la posición."""
    accounts = [make_account(), make_account(id=ACCOUNT_2)]

    def by_id(pairs: list[tuple[Account, str]]) -> dict[str, str]:
        return {account.id: path for account, path in pairs}

    assert by_id(assign_account_paths(accounts)) == by_id(
        assign_account_paths(list(reversed(accounts)))
    )


def test_more_than_one_account_leaves_a_warning() -> None:
    """Nunca en silencio (CLAUDE.md §1.3): el `Report` de la corrida lo cuenta."""
    warnings = account_path_warnings([make_account(), make_account(id=ACCOUNT_2)])

    assert len(warnings) == 1
    assert "account/account.md" in warnings[0]


def test_the_path_of_a_lone_account_ignores_its_id(account: Account) -> None:
    assert account_output_path(account) == ACCOUNT_PATH
    assert account_output_path(account, shared=True) != ACCOUNT_PATH


# ------------------------------------------------------------------ cuerpo


def test_the_body_shows_the_profile(account: Account) -> None:
    body = frontmatter.loads(render_account(account)).content

    assert "Persona Sintética" in body
    assert "persona@example.com" in body
    assert ACCOUNT_1 in body


def test_settings_are_listed_when_the_export_brings_them() -> None:
    markdown = render_account(make_account(settings={"locale": "es-CO", "theme": "dark"}))

    assert "| locale | es-CO |" in markdown
    assert "| theme | dark |" in markdown


def test_without_settings_there_is_no_empty_section(account: Account) -> None:
    assert "Configuración" not in render_account(account)


def test_a_missing_field_is_shown_as_empty_and_not_invented() -> None:
    markdown = render_account(make_account(email=None, display_name=None))

    assert "—" in frontmatter.loads(markdown).content


# ----------------------------------------------- CA-10 nada de la corrida


def test_ca10_output_has_no_generation_date_or_tool_version(account: Account) -> None:
    """CA-10: ni fecha de generación ni versión de la herramienta en el `.md`."""
    markdown = render_account(account)
    today = datetime.now(tz=UTC).date().isoformat()

    assert today not in markdown
    assert "claude_export_md" not in markdown
    assert "0.1.0" not in markdown


# ------------------------------------------------------ CA-1 determinismo


def test_ca1_two_renders_are_byte_identical(account: Account) -> None:
    first = render_accounts([account])
    second = render_accounts([account])

    assert first == second
    assert [markdown.encode("utf-8") for _path, markdown in first] == [
        markdown.encode("utf-8") for _path, markdown in second
    ]


def test_render_accounts_returns_the_path_of_each_file() -> None:
    rendered = render_accounts([make_account(), make_account(id=ACCOUNT_2)])

    assert len(rendered) == 2
    assert all(path.endswith(".md") for path, _markdown in rendered)


# --------------------------------------------------------- CA-9 plantillas


def test_ca9_user_template_overrides_the_default(tmp_path: Path, account: Account) -> None:
    (tmp_path / "account.md.j2").write_text("MÍA: {{ title }}\n", encoding="utf-8")

    assert render_account(account, build_environment(tmp_path)) == "MÍA: Persona Sintética\n"


# ------------------------------------------------------------------ snapshot


def test_snapshot_of_the_account(snapshot: SnapshotAssertion) -> None:
    accounts = [make_account(settings={"locale": "es-CO"}), make_account(id=ACCOUNT_2)]

    assert dict(render_accounts(accounts)) == snapshot

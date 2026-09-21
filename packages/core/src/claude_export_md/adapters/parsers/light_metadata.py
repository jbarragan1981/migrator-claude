"""Parser de `light_metadata` (spec 03, sección `light_metadata`).

Lo que confirmó la Fase 0 (`docs/export-format/light_metadata.md`): un único
`light_metadata-000/*.json` de ~152 bytes, **array** con un solo ítem en el export
observado, y ese ítem es el perfil de la cuenta (`uuid`, `email_address`, `full_name`,
`verified_phone_number`). Es la categoría más pequeña y la que mapea más directo:
`Account` (CA-1).

Decisiones de este módulo:

* **No se asume longitud 1 (CA-3)** — el array se itera entero. Si un export de
  organización trajera varias cuentas, salen todas; quien decide qué archivo le toca a
  cada una es `rendering/render.py` (`account/account.md` es una ruta fija de
  CLAUDE.md §5, así que con más de una cuenta ninguna se la queda).
* **Raíz que es un objeto suelto** — se trata como un array de un ítem y se avisa. Sin
  eso, un export con esa forma daría cero cuentas en silencio, que es justo lo que
  CLAUDE.md §1.3 prohíbe.
* **`verified_phone_number` se conserva (CA-2)** — es un dato de perfil, no un secreto,
  y va a `extra` como cualquier campo que la entidad no mapea (CA-C4). Lo que sí se
  excluye es el VALOR de cualquier campo cuyo nombre parezca una credencial
  (`*token*`, `*secret*`, `api_key`, `authorization`, `cookie`…): se sustituye por
  `REDACTED`, se conserva el nombre de la clave —que no es el secreto— y se avisa en
  `report.warnings`. `domain/redaction.py` no sirve aquí: resuelve otro problema (qué
  nombres de archivo puede publicar el inventario, ADR-0004), no valores de un perfil.
* **`json.load` con techo** — mismo criterio que `memories`: el archivo es diminuto y
  hay uno por cuenta, así que leerlo entero es correcto; la regla de streaming (CA-C3)
  apunta a `conversations.json` (~98 MB). Aun así se comprueba el tamaño antes, y si
  algún export trajera un `light_metadata` desproporcionado se registra en `Report` en
  vez de cargarlo en memoria.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator, Mapping, Sequence
from typing import Any

from claude_export_md.domain.entities import Account, Report
from claude_export_md.errors import CorruptFileError
from claude_export_md.ports.source import JSON, ExportSource, SourceFile

logger = logging.getLogger(__name__)

#: Nombre de la categoría tal como la nombran el manifiesto y `ExportSource`.
CATEGORY = "light_metadata"

#: Techo para leer el archivo entero (CA-C3). Por encima se registra y no se carga.
MAX_JSON_BYTES = 10 * 1024 * 1024

#: Claves del ítem que el parser mapea a un campo de `Account` (CA-1).
KEY_UUID = "uuid"
KEY_EMAIL = "email_address"
KEY_FULL_NAME = "full_name"
KEY_SETTINGS = "settings"
_ACCOUNT_KEYS = frozenset({KEY_UUID, KEY_EMAIL, KEY_FULL_NAME, KEY_SETTINGS})

#: Prefijo con el que se identifica un ítem del array en `Report.errors`.
ITEM_PREFIX = "item"
#: Campo de `extra` que anota de qué archivo del export salió la cuenta (spec 04).
SOURCE_FILE_KEY = "source_file"

#: Lo que se escribe en lugar del valor de un campo que parece una credencial (CA-2).
REDACTED = "<omitido: parece una credencial>"
#: Nombres (en minúsculas) que delatan un secreto. Son fragmentos: `api_token` entra por
#: `token`. Se buscan con `_looks_like_a_secret`, que exige que el fragmento sea una
#: PALABRA de la clave para que `author` no se confunda con `auth`.
SECRET_HINTS = frozenset(
    {
        "apikey",
        "auth",
        "authorization",
        "cookie",
        "credential",
        "credentials",
        "jwt",
        "key",
        "password",
        "passwd",
        "secret",
        "session",
        "signature",
        "token",
    }
)
#: Separadores con los que se parte el nombre de una clave en palabras.
_WORD_SEPARATORS = "-. /"


def parse(source: ExportSource, report: Report) -> Iterator[Account]:
    """Cuentas del export, en el orden del archivo y sin repetir `uuid` (CA-C1, CA-C5).

    No lanza: un archivo ilegible o un ítem con forma inesperada se acumula en
    `report.errors` y el resto sigue (CA-C2).
    """
    seen: set[str] = set()
    for file in _files(source, report):
        data = _load(source, file, report)
        if data is None:
            continue
        for index, raw in enumerate(_items(data, file, report)):
            account = _account(raw, index, file, report)
            if account is None:
                continue
            if account.id in seen:
                report.add_warning(
                    f"{file.path}: cuenta repetida {account.id}; se conserva la primera"
                )
                continue
            seen.add(account.id)
            report.count(CATEGORY)
            yield account


# ------------------------------------------------------------------- archivos


def _files(source: ExportSource, report: Report) -> list[SourceFile]:
    """Archivos JSON de la categoría, ordenados por parte y ruta (CA-C1)."""
    files = [file for file in source.files() if file.category == CATEGORY]
    for file in files:
        if file.kind != JSON:
            report.add_warning(f"{file.path}: no es JSON; se omite")
    return sorted((file for file in files if file.kind == JSON), key=lambda f: (f.part, f.path))


def _load(source: ExportSource, file: SourceFile, report: Report) -> Any | None:  # noqa: ANN401
    """Contenido del JSON, o `None` si no se pudo leer (ya registrado en `Report`)."""
    if file.bytes > MAX_JSON_BYTES:
        report.add_error(
            CATEGORY,
            f"el archivo ocupa {file.bytes} bytes, por encima del límite de "
            f"{MAX_JSON_BYTES} bytes para leerlo entero; se omite",
            source_file=file.path,
        )
        return None
    try:
        with source.open_file(file) as stream:
            return json.load(stream)
    except (CorruptFileError, OSError, UnicodeDecodeError, ValueError) as exc:
        logger.warning("light_metadata ilegible en %s: %s", file.path, exc)
        report.add_error(CATEGORY, f"JSON ilegible: {exc}", source_file=file.path)
        return None


def _items(data: Any, file: SourceFile, report: Report) -> Sequence[Any]:  # noqa: ANN401
    """Los ítems del archivo: el array del export o el objeto suelto como array de 1."""
    if isinstance(data, Sequence) and not isinstance(data, str | bytes):
        return data
    if isinstance(data, Mapping):
        report.add_warning(
            f"{file.path}: la raíz del JSON es un objeto y se esperaba un array; "
            "se trata como una única cuenta"
        )
        return [data]
    report.add_error(
        CATEGORY,
        f"la raíz del JSON es {type(data).__name__}, se esperaba un array de cuentas",
        source_file=file.path,
    )
    return []


# --------------------------------------------------------------------- cuenta


def _account(
    raw: Any,  # noqa: ANN401 - lo que venga en el array del export
    index: int,
    file: SourceFile,
    report: Report,
) -> Account | None:
    """Un ítem del array → `Account`, o `None` si no se pudo identificar (CA-C2)."""
    item_id = f"{ITEM_PREFIX}[{index}]"
    if not isinstance(raw, Mapping):
        report.add_error(
            CATEGORY,
            f"se esperaba un objeto y vino {type(raw).__name__}",
            item_id=item_id,
            source_file=file.path,
        )
        return None
    uuid = raw.get(KEY_UUID)
    if not isinstance(uuid, str) or not uuid.strip():
        report.add_error(
            CATEGORY,
            "cuenta sin `uuid`: no se puede identificar",
            item_id=item_id,
            source_file=file.path,
        )
        return None
    values = _safe_extra(raw, item_id, file, report)
    values.update(
        id=uuid,
        email=_text(raw.get(KEY_EMAIL)),
        display_name=_text(raw.get(KEY_FULL_NAME)),
        settings=_settings(raw.get(KEY_SETTINGS), item_id, file, report, values),
    )
    values.setdefault(SOURCE_FILE_KEY, file.path)
    return Account.model_validate(values)


def _text(value: Any) -> str | None:  # noqa: ANN401 - valor libre del export
    """Solo se acepta texto; cualquier otra forma deja el campo vacío, no la cuenta."""
    return value if isinstance(value, str) else None


def _settings(
    raw: Any,  # noqa: ANN401 - no se observó en el export real
    item_id: str,
    file: SourceFile,
    report: Report,
    extra: dict[str, Any],
) -> dict[str, Any]:
    """`settings` no apareció en la Fase 0; si llega y es un objeto, se mapea.

    Con cualquier otra forma no se fuerza el tipo: se avisa y el valor original sigue a
    la vista en `extra["settings_raw"]` —la misma convención que usa el dominio para una
    fecha ilegible—, porque no reconocer un campo no es motivo para descartarlo
    (CLAUDE.md §1.3).
    """
    if raw is None:
        return {}
    if isinstance(raw, Mapping):
        return {str(key): value for key, value in raw.items()}
    extra[f"{KEY_SETTINGS}_raw"] = raw
    report.add_warning(
        f"{file.path}: `{KEY_SETTINGS}` de {item_id} debería ser un objeto y vino "
        f"{type(raw).__name__}; se conserva en extra.{KEY_SETTINGS}_raw"
    )
    return {}


# --------------------------------------------------------------- credenciales


def _looks_like_a_secret(key: str) -> bool:
    """`api_token` sí, `author` no: el fragmento tiene que ser una palabra de la clave."""
    normalised = key.casefold()
    for separator in _WORD_SEPARATORS:
        normalised = normalised.replace(separator, "_")
    return any(word in SECRET_HINTS for word in normalised.split("_"))


def _safe_extra(
    raw: Mapping[str, Any], item_id: str, file: SourceFile, report: Report
) -> dict[str, Any]:
    """Campos que no mapea la entidad (CA-C4), con las credenciales ya sin valor (CA-2)."""
    extra: dict[str, Any] = {}
    redacted: list[str] = []
    for key, value in raw.items():
        if key in _ACCOUNT_KEYS:
            continue
        if _looks_like_a_secret(str(key)):
            # Se conserva el NOMBRE de la clave (no es el secreto) para que el usuario
            # sepa que el export traía ese campo y que la herramienta no lo escribió.
            extra[str(key)] = REDACTED
            redacted.append(str(key))
            continue
        extra[str(key)] = value
    if redacted:
        report.add_warning(
            f"{file.path}: {item_id} traía campos que parecen credenciales "
            f"({', '.join(sorted(redacted))}); su valor no se escribe en la salida"
        )
    return extra


__all__ = [
    "CATEGORY",
    "MAX_JSON_BYTES",
    "REDACTED",
    "SECRET_HINTS",
    "parse",
]

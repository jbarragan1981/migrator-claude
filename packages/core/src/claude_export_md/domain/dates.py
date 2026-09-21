"""Normalización de fechas del export a UTC (spec 02, regla de `tz_assumed`).

El export trae ISO-8601 en varias formas (`...Z`, `...+00:00`, sin zona). El dominio
guarda siempre `datetime` con `tzinfo=UTC`; cuando el origen no trae zona se asume UTC
y la entidad lo declara con `extra["tz_assumed"] = True`, para que el usuario sepa que
esa hora es una suposición nuestra y no un dato del export.

Módulo puro: sin I/O, solo stdlib.
"""

from __future__ import annotations

from datetime import UTC, datetime

#: Resultado de normalizar: `(fecha en UTC o None, se asumió la zona)`.
Timestamp = tuple[datetime | None, bool]

_UNPARSEABLE: Timestamp = (None, False)


def parse_timestamp(value: object) -> Timestamp:
    """`"2026-03-04T05:06:07"` → `(2026-03-04 05:06:07+00:00, True)`.

    Devuelve `(None, False)` para cualquier valor que no sea una fecha legible: quien
    llama decide si eso es un error del ítem o un campo ausente. Nunca lanza.
    """
    if isinstance(value, datetime):
        return _to_utc(value)
    if not isinstance(value, str) or not value.strip():
        return _UNPARSEABLE
    try:
        # `fromisoformat` acepta el sufijo `Z` desde 3.11 y los offsets `+HH:MM`.
        return _to_utc(datetime.fromisoformat(value.strip()))
    except ValueError:
        return _UNPARSEABLE


def _to_utc(value: datetime) -> Timestamp:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC), True
    return value.astimezone(UTC), False


__all__ = ["Timestamp", "parse_timestamp"]

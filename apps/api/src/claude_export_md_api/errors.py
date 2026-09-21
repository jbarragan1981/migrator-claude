"""Excepcion propia que el exception handler central traduce a RFC 7807 (spec 06).

Los routers/servicios lanzan `ProblemError`; `main.py` es el UNICO sitio que sabe
convertirla en una respuesta `application/problem+json` (CLAUDE.md 7, "no repitas
el formato a mano en cada endpoint").
"""

from __future__ import annotations


class ProblemError(Exception):
    """Un error HTTP con forma RFC 7807 (https://www.rfc-editor.org/rfc/rfc7807)."""

    def __init__(
        self,
        status: int,
        title: str,
        detail: str | None = None,
        *,
        type_: str = "about:blank",
    ) -> None:
        super().__init__(detail or title)
        self.status = status
        self.title = title
        self.detail = detail
        self.type = type_

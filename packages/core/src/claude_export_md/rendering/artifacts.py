"""Extracción de artefactos largos del cuerpo de una conversación (spec 04 CA-5).

Un bloque de código largo dentro de un mensaje se lee fatal pegado en medio del hilo y
además no se puede abrir con las herramientas del lenguaje. Este módulo lo saca a su
propio archivo y deja un enlace relativo en su lugar (skill `markdown-template`, regla 7).

**Umbral: 40 líneas.** El skill dice "no se pegan inline si superan 40 líneas" y la spec
04 CA-5 usa como ejemplo un artefacto de 120 líneas que debe acabar en
`artifacts/01-<slug>.<ext>`. No se contradicen: 40 es el umbral y 120 es un caso que lo
supera de sobra, así que con 40 se cumplen los dos. Se elige el número más exigente
porque el coste de sacar un archivo de más es un enlace, y el de dejarlo dentro es un
`.md` ilegible.

**Qué cuenta como artefacto.** La Fase 0 no observó bloques `artifact` ni
`<antArtifact>` en el export (spec 03, conversations CA-5): lo que hay son cercas de
código dentro del texto del mensaje. Por eso se extraen *cercas* (``` o ~~~), no
mensajes enteros: así el texto que rodea al código se conserva donde estaba.

**Nombre y extensión.** La extensión sale del lenguaje de la cerca (```python → `.py`);
si no hay lenguaje conocido, `.txt`. El nombre intenta usar un archivo mencionado justo
antes de la cerca (``Te dejo `scripts/ventas.py`:`` → `01-ventas.py`) y solo lo acepta si
la extensión de esa mención coincide con la del lenguaje, para no bautizar un artefacto
con cualquier cosa que venga entre comillas invertidas.

Módulo puro: no escribe nada y no mira el reloj.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from claude_export_md.rendering.filters import slugify

#: Líneas a partir de las cuales una cerca de código deja de pegarse en el cuerpo.
ARTIFACT_MIN_LINES = 40

#: Carpeta (relativa al `.md` de la conversación) donde van los artefactos.
ARTIFACTS_DIR = "artifacts"
#: Nombre de un artefacto cuya cerca no declara lenguaje.
DEFAULT_STEM = "artefacto"
#: Extensión de un lenguaje que no conocemos: el contenido sigue siendo texto.
DEFAULT_SUFFIX = ".txt"
#: Líneas hacia atrás en las que se busca el nombre de archivo del artefacto.
NAME_LOOKBACK = 5

#: Lenguaje de la cerca → extensión del archivo. Lo que no esté aquí acaba en `.txt`.
EXTENSIONS = {
    "bash": ".sh",
    "c": ".c",
    "cpp": ".cpp",
    "cs": ".cs",
    "csharp": ".cs",
    "css": ".css",
    "diff": ".diff",
    "go": ".go",
    "html": ".html",
    "ini": ".ini",
    "java": ".java",
    "javascript": ".js",
    "js": ".js",
    "json": ".json",
    "jsx": ".jsx",
    "kotlin": ".kt",
    "markdown": ".md",
    "md": ".md",
    "php": ".php",
    "python": ".py",
    "rb": ".rb",
    "ruby": ".rb",
    "rs": ".rs",
    "rust": ".rs",
    "sh": ".sh",
    "shell": ".sh",
    "sql": ".sql",
    "svg": ".svg",
    "swift": ".swift",
    "toml": ".toml",
    "ts": ".ts",
    "tsx": ".tsx",
    "typescript": ".ts",
    "xml": ".xml",
    "yaml": ".yaml",
    "yml": ".yaml",
}

_FENCE_OPEN = re.compile(r"^(?P<indent> {0,3})(?P<fence>`{3,}|~{3,})(?P<info>.*)$")
_INLINE_CODE = re.compile(r"`([^`\n]+)`")


def extension_for(language: str) -> str:
    """Extensión del archivo según el lenguaje de la cerca; `.txt` si no lo conocemos."""
    return EXTENSIONS.get(language.strip().lower(), DEFAULT_SUFFIX)


@dataclass(frozen=True, slots=True)
class Artifact:
    """Un bloque de código extraído a su propio archivo."""

    #: Nombre del archivo, ya numerado: `01-ventas.py`.
    name: str
    #: Ruta relativa desde el `.md` de la conversación: `<carpeta>/artifacts/01-ventas.py`.
    link: str
    content: str
    language: str
    lines: int


class ArtifactCollector:
    """Saca las cercas largas del texto de una conversación y las numera en orden.

    Se usa una por conversación: `extract` se llama una vez por bloque de texto y la
    numeración (`01-`, `02-`, …) sigue el orden de aparición en el hilo, que es
    determinista porque los mensajes y sus bloques conservan el orden del export.
    """

    def __init__(self, folder: str, min_lines: int = ARTIFACT_MIN_LINES) -> None:
        self._folder = folder
        self._min_lines = min_lines
        self.artifacts: list[Artifact] = []

    def extract(self, text: str) -> str:
        """Devuelve el texto con las cercas largas sustituidas por su enlace relativo."""
        lines = text.split("\n")
        out: list[str] = []
        index = 0
        while index < len(lines):
            opening = _FENCE_OPEN.match(lines[index])
            if opening is None:
                out.append(lines[index])
                index += 1
                continue
            end = _closing_line(lines, index, opening["fence"])
            if end is None:
                # Sin cierre no se sabe dónde acaba el artefacto: se deja tal cual.
                out.append(lines[index])
                index += 1
                continue
            body = lines[index + 1 : end]
            if len(body) > self._min_lines:
                out.append(opening["indent"] + self._store(body, opening["info"], out))
            else:
                out.extend(lines[index : end + 1])
            index = end + 1
        return "\n".join(out)

    def _store(self, body: list[str], info: str, before: list[str]) -> str:
        language = info.strip().split(" ")[0].strip().lower()
        suffix = extension_for(language)
        stem = _name_hint(before, suffix) or slugify(language or DEFAULT_STEM)
        name = f"{len(self.artifacts) + 1:02d}-{stem}{suffix}"
        artifact = Artifact(
            name=name,
            link=f"{self._folder}/{ARTIFACTS_DIR}/{name}",
            content="\n".join(body) + "\n",
            language=language,
            lines=len(body),
        )
        self.artifacts.append(artifact)
        return _link_line(artifact)


def _closing_line(lines: list[str], start: int, fence: str) -> int | None:
    """Índice de la línea que cierra la cerca abierta en `start`, o `None` si no cierra."""
    closing = re.compile(rf"^ {{0,3}}{re.escape(fence[0])}{{{len(fence)},}}[ \t]*$")
    for index in range(start + 1, len(lines)):
        if closing.match(lines[index]):
            return index
    return None


def _name_hint(before: list[str], suffix: str) -> str | None:
    """Nombre de archivo mencionado justo antes de la cerca, si encaja con el lenguaje."""
    for line in reversed(before[-NAME_LOOKBACK:]):
        for candidate in reversed(_INLINE_CODE.findall(line)):
            path = PurePosixPath(candidate.strip())
            if " " not in candidate.strip() and path.suffix.lower() == suffix:
                return slugify(path.stem)
    return None


def _link_line(artifact: Artifact) -> str:
    """Párrafo que sustituye al artefacto en el cuerpo, con el enlace relativo (CA-5)."""
    parts = [
        "> 📄 **Artefacto extraído**",
        f"[{artifact.name}]({artifact.link})",
        f"{artifact.lines} líneas",
    ]
    if artifact.language:
        parts.append(f"`{artifact.language}`")
    return " · ".join(parts)


__all__ = [
    "ARTIFACTS_DIR",
    "ARTIFACT_MIN_LINES",
    "EXTENSIONS",
    "Artifact",
    "ArtifactCollector",
    "extension_for",
]

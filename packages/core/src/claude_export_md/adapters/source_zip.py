"""Lectura de exports empaquetados en `.zip`, sin extraer nada a disco (CA-4).

Expone helpers reutilizables por `source_folder.py` (una carpeta puede contener zips
sin extraer) y `ZipSource`, que trata un único `.zip` como export completo.
"""

from __future__ import annotations

import logging
import zipfile
from collections.abc import Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import IO

from claude_export_md.domain.inventory import (
    BATCHED_MANIFEST,
    LEGACY_CATEGORIES,
    LEGACY_SINGLE_ZIP,
)
from claude_export_md.domain.manifest import Manifest, split_part_suffix
from claude_export_md.errors import CorruptFileError, UnknownFormatError
from claude_export_md.ports.source import JSON, MARKDOWN, OTHER, SourceFile

logger = logging.getLogger(__name__)


def classify_kind(name: str) -> str:
    lowered = name.lower()
    if lowered.endswith(".json") or lowered.endswith(".jsonl"):
        return JSON
    if lowered.endswith(".md") or lowered.endswith(".markdown"):
        return MARKDOWN
    return OTHER


def category_of_member(member: str, fallback: tuple[str, int]) -> tuple[str, int]:
    """Categoría/parte de un miembro de zip cuando el nombre del zip no las da."""
    head, _, tail = member.partition("/")
    if tail:
        guessed = split_part_suffix(head)
        if guessed is not None:
            return guessed
        return head, 0
    stem = member.rsplit(".", 1)[0]
    if stem in LEGACY_CATEGORIES:
        return stem, 0
    return fallback


def open_zip(path: Path) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise CorruptFileError(path.name, str(exc)) from exc


def zip_members(path: Path) -> list[zipfile.ZipInfo]:
    with open_zip(path) as zf:
        return [info for info in zf.infolist() if not info.is_dir()]


def is_legacy_zip(members: Sequence[zipfile.ZipInfo]) -> bool:
    """Legacy = varios de `conversations/projects/users.json` sueltos en la raíz del zip."""
    roots = {
        info.filename.rsplit(".", 1)[0]
        for info in members
        if "/" not in info.filename and info.filename.lower().endswith(".json")
    }
    return len(roots & LEGACY_CATEGORIES) >= 2


def zip_source_files(
    zip_path: Path,
    *,
    prefix: str = "",
    category: str | None = None,
    part: int = 0,
) -> tuple[list[SourceFile], bool]:
    """Archivos de un zip como `SourceFile`s. Devuelve también si el zip es legacy.

    Solo se leen las cabeceras del zip (`infolist`), nunca su contenido.
    """
    members = zip_members(zip_path)
    legacy = is_legacy_zip(members)
    files: list[SourceFile] = []
    for info in members:
        if legacy or category is None:
            member_category, member_part = category_of_member(
                info.filename, (category or zip_path.stem, part)
            )
        else:
            member_category, member_part = category, part
        files.append(
            SourceFile(
                category=member_category,
                part=member_part,
                path=f"{prefix}{info.filename}",
                bytes=info.file_size,
                kind=classify_kind(info.filename),
            )
        )
    return files, legacy


@contextmanager
def open_zip_member(zip_path: Path, member: str) -> Iterator[IO[bytes]]:
    """Abre un miembro del zip como stream binario (sin extraerlo)."""
    with open_zip(zip_path) as zf:
        try:
            handle = zf.open(member)
        except KeyError as exc:  # pragma: no cover - depende de un índice corrupto
            raise CorruptFileError(f"{zip_path.name}!/{member}", str(exc)) from exc
        with handle:
            yield handle


class ZipSource:
    """`ExportSource` sobre un único `.zip` (una categoría o el zip legacy completo)."""

    def __init__(self, path: Path) -> None:
        if not path.is_file() or path.suffix.lower() != ".zip":
            raise UnknownFormatError(f"{path.name} no es un archivo .zip")
        self._path = path
        guessed = split_part_suffix(path.stem)
        files, legacy = zip_source_files(
            path,
            category=None if guessed is None else guessed[0],
            part=0 if guessed is None else guessed[1],
        )
        self._legacy = legacy
        self._files = sorted(files, key=lambda f: (f.category, f.part, f.path))

    @property
    def root(self) -> str:
        return self._path.name

    @property
    def format_version(self) -> str:
        return LEGACY_SINGLE_ZIP if self._legacy else BATCHED_MANIFEST

    def files(self) -> Sequence[SourceFile]:
        return self._files

    def manifest(self) -> Manifest | None:
        return None

    def open_file(self, file: SourceFile) -> AbstractContextManager[IO[bytes]]:
        return open_zip_member(self._path, file.path)

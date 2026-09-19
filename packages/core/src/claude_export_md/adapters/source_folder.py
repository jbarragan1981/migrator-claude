"""`ExportSource` sobre una carpeta: el caso principal.

Acepta, en la misma raíz y mezclados:
- subcarpetas ya extraídas (`conversations-000/`, `memories-000/`, …),
- zips sin extraer (`conversations-000.zip`) — se leen en streaming vía `source_zip`,
- el layout legacy (`conversations.json`, `projects.json`, `users.json` sueltos),
- el `member-manifest-*.json`, que solo se usa para validar categorías y partes.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import IO

from claude_export_md.adapters.manifest import MANIFEST_GLOB, find_manifest, parse_manifest
from claude_export_md.adapters.source_zip import (
    classify_kind,
    open_zip_member,
    zip_source_files,
)
from claude_export_md.domain.inventory import (
    BATCHED_MANIFEST,
    LEGACY_CATEGORIES,
    LEGACY_SINGLE_ZIP,
)
from claude_export_md.domain.manifest import Manifest, split_part_suffix
from claude_export_md.errors import CorruptFileError, UnknownFormatError
from claude_export_md.ports.source import SourceFile

logger = logging.getLogger(__name__)


@contextmanager
def _open_real_file(path: Path) -> Iterator[IO[bytes]]:
    try:
        handle = path.open("rb")
    except OSError as exc:  # pragma: no cover - depende del sistema de archivos
        raise CorruptFileError(path.name, str(exc)) from exc
    with handle:
        yield handle


class FolderSource:
    """Lee un export ya presente en una carpeta del disco del usuario."""

    def __init__(self, root: Path) -> None:
        if not root.is_dir():
            raise UnknownFormatError(f"{root} no es una carpeta")
        self._root = root
        self._files: list[SourceFile] = []
        #: ruta de presentación → (archivo real, miembro de zip o None)
        self._locations: dict[str, tuple[Path, str | None]] = {}
        self._manifest_path = find_manifest(root)
        self._manifest: Manifest | None = None
        self._legacy = False
        self._discover()

    # -- descubrimiento ---------------------------------------------------

    def _add(self, file: SourceFile, real: Path, member: str | None = None) -> None:
        self._files.append(file)
        self._locations[file.path] = (real, member)

    def _discover(self) -> None:
        containers = 0
        legacy_markers = 0
        for entry in sorted(self._root.iterdir(), key=lambda p: p.name):
            if entry.is_dir():
                containers += 1
                self._discover_dir(entry)
            elif entry.suffix.lower() == ".zip":
                containers += 1
                self._discover_zip(entry)
            elif entry.suffix.lower() == ".json":
                if entry.match(MANIFEST_GLOB):
                    continue
                stem = entry.stem
                if stem in LEGACY_CATEGORIES:
                    legacy_markers += 1
                self._add(
                    SourceFile(
                        category=stem,
                        part=0,
                        path=entry.name,
                        bytes=entry.stat().st_size,
                        kind=classify_kind(entry.name),
                    ),
                    entry,
                )
            else:
                logger.debug("Se ignora %s: no es carpeta, zip ni json", entry.name)
        self._legacy = self._legacy or (containers == 0 and legacy_markers >= 2)
        self._files.sort(key=lambda f: (f.category, f.part, f.path))

    def _discover_dir(self, directory: Path) -> None:
        guessed = split_part_suffix(directory.name)
        category, part = guessed if guessed is not None else (directory.name, 0)
        for path in sorted(directory.rglob("*"), key=lambda p: p.as_posix()):
            if not path.is_file():
                continue
            relative = path.relative_to(self._root).as_posix()
            self._add(
                SourceFile(
                    category=category,
                    part=part,
                    path=relative,
                    bytes=path.stat().st_size,
                    kind=classify_kind(path.name),
                ),
                path,
            )

    def _discover_zip(self, zip_path: Path) -> None:
        guessed = split_part_suffix(zip_path.stem)
        try:
            files, legacy = zip_source_files(
                zip_path,
                prefix=f"{zip_path.name}!/",
                category=None if guessed is None else guessed[0],
                part=0 if guessed is None else guessed[1],
            )
        except CorruptFileError as exc:
            logger.warning("Zip ilegible %s: %s", zip_path.name, exc.reason)
            return
        for file in files:
            member = file.path.split("!/", 1)[1]
            self._add(file, zip_path, member)
        self._legacy = self._legacy or legacy

    # -- puerto -----------------------------------------------------------

    @property
    def root(self) -> str:
        return self._root.name

    @property
    def format_version(self) -> str:
        return LEGACY_SINGLE_ZIP if self._legacy else BATCHED_MANIFEST

    def files(self) -> Sequence[SourceFile]:
        return self._files

    def manifest(self) -> Manifest | None:
        """Parsea el manifiesto. Lanza `CorruptFileError` si existe pero está roto."""
        if self._manifest_path is None:
            return None
        if self._manifest is None:
            self._manifest = parse_manifest(self._manifest_path)
        return self._manifest

    def open_file(self, file: SourceFile) -> AbstractContextManager[IO[bytes]]:
        real, member = self._locations[file.path]
        if member is None:
            return _open_real_file(real)
        return open_zip_member(real, member)

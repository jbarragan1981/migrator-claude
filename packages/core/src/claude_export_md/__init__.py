"""API pública de claude_export_md.

Librería pura (sin HTTP, sin CLI, sin framework) para convertir una exportación
de datos de Claude.ai en una carpeta navegable de Markdown. Ver CLAUDE.md §1 en
la raíz del repo para las reglas no negociables de este paquete.

Uso típico:

    from claude_export_md import build_inventory, create_source, write_inventory

    inventory = build_inventory(create_source("./mi-export"))
    write_inventory(inventory, "inventory.json")
"""

from __future__ import annotations

from claude_export_md.adapters.sink_json import dumps_inventory, write_inventory
from claude_export_md.adapters.source_factory import create_source
from claude_export_md.adapters.source_folder import FolderSource
from claude_export_md.adapters.source_zip import ZipSource
from claude_export_md.domain.inventory import (
    CategoryInventory,
    FileInventory,
    Inventory,
)
from claude_export_md.domain.manifest import Manifest
from claude_export_md.errors import (
    ClaudeExportMdError,
    CorruptFileError,
    UnknownFormatError,
)
from claude_export_md.ports.source import ExportSource, SourceFile
from claude_export_md.usecases.inventory import build_inventory

__version__ = "0.1.0"

__all__ = [
    "CategoryInventory",
    "ClaudeExportMdError",
    "CorruptFileError",
    "ExportSource",
    "FileInventory",
    "FolderSource",
    "Inventory",
    "Manifest",
    "SourceFile",
    "UnknownFormatError",
    "ZipSource",
    "__version__",
    "build_inventory",
    "create_source",
    "dumps_inventory",
    "write_inventory",
]

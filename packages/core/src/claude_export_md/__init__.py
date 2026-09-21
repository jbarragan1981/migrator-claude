"""API pública de claude_export_md.

Librería pura (sin HTTP, sin CLI, sin framework) para convertir una exportación
de datos de Claude.ai en una carpeta navegable de Markdown. Ver CLAUDE.md §1 en
la raíz del repo para las reglas no negociables de este paquete.

Uso típico:

    from claude_export_md import (
        FilesystemSink, build_inventory, convert, create_source, write_inventory,
    )

    source = create_source("./mi-export")
    write_inventory(build_inventory(source), "inventory.json")
    result = convert(source, FilesystemSink("./salida"))   # → ConvertResult

`convert` escribe a través del puerto `MarkdownSink` (ADR-0006): quien llama elige el
destino (`FilesystemSink` hoy; un zip o una bóveda de Obsidian más adelante).
"""

from __future__ import annotations

from claude_export_md.adapters.parsers import conversations as conversations_parser
from claude_export_md.adapters.parsers import memories as memories_parser
from claude_export_md.adapters.sink_filesystem import FilesystemSink, ensure_writable
from claude_export_md.adapters.sink_json import (
    dumps_errors,
    dumps_inventory,
    dumps_summary,
    write_inventory,
)
from claude_export_md.adapters.source_factory import create_source
from claude_export_md.adapters.source_folder import FolderSource
from claude_export_md.adapters.source_zip import ZipSource
from claude_export_md.domain.entities import (
    Account,
    ContentBlock,
    Conversation,
    Frame,
    Memory,
    Message,
    ParseError,
    Project,
    ProjectDoc,
    Report,
)
from claude_export_md.domain.inventory import (
    CategoryInventory,
    FileInventory,
    Inventory,
)
from claude_export_md.domain.manifest import Manifest
from claude_export_md.errors import (
    ClaudeExportMdError,
    CorruptFileError,
    OutputNotEmptyError,
    UnknownFormatError,
)
from claude_export_md.ports.sink import MarkdownSink
from claude_export_md.ports.source import ExportSource, SourceFile
from claude_export_md.rendering.conversations import render_conversation, render_conversations
from claude_export_md.rendering.index import render_index, render_readme
from claude_export_md.rendering.render import build_environment, render_memories, render_memory
from claude_export_md.usecases.convert import ConvertResult, ProgressCallback, convert
from claude_export_md.usecases.inventory import build_inventory

__version__ = "0.1.0"

__all__ = [
    "Account",
    "CategoryInventory",
    "ClaudeExportMdError",
    "ContentBlock",
    "Conversation",
    "ConvertResult",
    "CorruptFileError",
    "ExportSource",
    "FileInventory",
    "FilesystemSink",
    "FolderSource",
    "Frame",
    "Inventory",
    "Manifest",
    "MarkdownSink",
    "Memory",
    "Message",
    "OutputNotEmptyError",
    "ParseError",
    "ProgressCallback",
    "Project",
    "ProjectDoc",
    "Report",
    "SourceFile",
    "UnknownFormatError",
    "ZipSource",
    "__version__",
    "build_environment",
    "build_inventory",
    "conversations_parser",
    "convert",
    "create_source",
    "dumps_errors",
    "dumps_inventory",
    "dumps_summary",
    "ensure_writable",
    "memories_parser",
    "render_conversation",
    "render_conversations",
    "render_index",
    "render_memories",
    "render_memory",
    "render_readme",
    "write_inventory",
]

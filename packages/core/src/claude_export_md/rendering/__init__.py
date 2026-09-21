"""Render de las entidades a Markdown (spec 04).

`filters.py` son las piezas comunes a todas las plantillas (slug, fechas, YAML del
frontmatter), `templates/` las plantillas Jinja2 por defecto y `render.py` el armado de
cada tipo de archivo. Nada de aquí escribe en disco: eso es de `adapters/`.
"""

from __future__ import annotations

from claude_export_md.rendering.artifacts import ARTIFACT_MIN_LINES, Artifact, ArtifactCollector
from claude_export_md.rendering.conversations import (
    CONVERSATIONS_DIR,
    ConversationPaths,
    RenderedConversation,
    RenderedFile,
    conversation_output_path,
    conversation_title,
    render_conversation,
    render_conversations,
)
from claude_export_md.rendering.filters import code_fence, hhmm, iso_utc, short_hash, slugify
from claude_export_md.rendering.render import (
    MEMORIES_DIR,
    TEMPLATES_DIR,
    assign_output_paths,
    build_environment,
    memory_output_path,
    memory_title,
    render_memories,
    render_memory,
)

__all__ = [
    "ARTIFACT_MIN_LINES",
    "CONVERSATIONS_DIR",
    "MEMORIES_DIR",
    "TEMPLATES_DIR",
    "Artifact",
    "ArtifactCollector",
    "ConversationPaths",
    "RenderedConversation",
    "RenderedFile",
    "assign_output_paths",
    "build_environment",
    "code_fence",
    "conversation_output_path",
    "conversation_title",
    "hhmm",
    "iso_utc",
    "memory_output_path",
    "memory_title",
    "render_conversation",
    "render_conversations",
    "render_memories",
    "render_memory",
    "short_hash",
    "slugify",
]

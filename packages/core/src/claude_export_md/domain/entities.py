"""Entidades del export, independientes del formato de origen y del de salida.

Modelo del spec 02 con los ajustes que obligó la Fase 0 (`docs/export-format/`) y que
documenta ADR-0005: `Memory.project_id` y rutas sintéticas para las memorias que el
export no trae con ruta propia, `ProjectDoc.content` opcional (el contenido no viaja en
el export), `Frame` con sus versiones, y `Report` como acumulador de errores.

Reglas que valen para todas (CLAUDE.md §1.3 y §7):

* `extra="allow"`: un campo desconocido se conserva y acaba bajo `extra:` en el
  frontmatter; nunca se descarta en silencio.
* `frozen=True`: una entidad ya parseada no se modifica (`Report` es la excepción
  razonada del ADR-0005: sus colecciones se acumulan, sus campos no se sustituyen).
* Todo opcional salvo el identificador (`id`, o `path` en `Memory`).
* Fechas en UTC; si el origen no trae zona se asume UTC y se marca `tz_assumed`.

Módulo puro: sin I/O y sin saber de archivos.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from functools import cache
from typing import Any, get_args

from pydantic import BaseModel, ConfigDict, model_validator

from claude_export_md.domain.dates import parse_timestamp

# --------------------------------------------------------------------- vocabulario

#: Tipos de bloque observados en `chat_messages[].content[]` (docs/export-format/conversations.md).
BLOCK_TEXT = "text"
BLOCK_THINKING = "thinking"
BLOCK_TOOL_USE = "tool_use"
BLOCK_TOOL_RESULT = "tool_result"
#: Un bloque sin `type`: no se descarta, se marca (su contenido sigue en `payload`).
BLOCK_UNKNOWN = "unknown"

#: Valores de `Message.sender` observados. Cualquier otro se conserva tal cual.
SENDER_HUMAN = "human"
SENDER_ASSISTANT = "assistant"

#: De dónde salió una `Memory` (ADR-0005), en `extra["origin"]`.
ORIGIN_MEMORY_FILES = "memory_files"
ORIGIN_CONVERSATIONS_MEMORY = "conversations_memory"
ORIGIN_PROJECT_MEMORIES = "project_memories"

#: Ruta sintética de `conversations_memory` (no viene con ruta propia en el export).
CONVERSATIONS_MEMORY_PATH = "/_conversations_memory.md"
#: Carpeta sintética de `project_memories{}`. El `_` marca que la ruta la inventa la
#: herramienta y no el export; NO garantiza el nombre del archivo, porque `slugify` lo
#: quita al escribir (`memories/project-memories/<uuid>.md`). De que dos memorias no se
#: pisen en disco se ocupa `rendering.render.assign_output_paths` (ADR-0005, corrección).
PROJECT_MEMORY_DIR = "/_project_memories"

#: Separador con el que se reconstruye `Message.text` desde los bloques de texto.
TEXT_JOIN = "\n\n"


def project_memory_path(project_id: str) -> str:
    """Ruta sintética y determinista de la memoria de un proyecto (ADR-0005)."""
    return f"{PROJECT_MEMORY_DIR}/{project_id}.md"


# -------------------------------------------------------------------- base común


@cache
def _timestamp_fields(model: type[BaseModel]) -> frozenset[str]:
    """Campos del modelo anotados como `datetime` (incluido `datetime | None`)."""
    return frozenset(
        name
        for name, field in model.model_fields.items()
        if field.annotation is datetime
        or any(arg is datetime for arg in get_args(field.annotation))
    )


class DomainModel(BaseModel):
    """Base de todas las entidades: tolerante a esquema, inmutable y en UTC."""

    model_config = ConfigDict(extra="allow", frozen=True)

    @model_validator(mode="before")
    @classmethod
    def _normalise_timestamps(cls, data: Any) -> Any:
        """Lleva todas las fechas a UTC y marca `tz_assumed` si hubo que suponerla.

        Una fecha ilegible no invalida el ítem: el campo queda en `None` y el valor
        original se conserva en `extra["<campo>_raw"]` para que el usuario lo vea.
        """
        if not isinstance(data, dict):
            return data
        fields = _timestamp_fields(cls)
        if not fields:
            return data
        values: dict[str, Any] = dict(data)
        assumed = False
        for name in fields:
            raw = values.get(name)
            if raw is None:
                continue
            parsed, was_naive = parse_timestamp(raw)
            values[name] = parsed
            assumed = assumed or was_naive
            if parsed is None:
                values.setdefault(f"{name}_raw", raw)
        if assumed:
            values.setdefault("tz_assumed", True)
        return values


# ------------------------------------------------------------------ conversación


class ContentBlock(DomainModel):
    """Un bloque de `content[]`: su tipo y el resto del bloque tal cual vino.

    `payload` guarda el bloque original completo menos `type`, porque `input`,
    `display_content` o `structured_content` son de esquema libre y dependen de la
    herramienta invocada (spec 03, conversations CA-3): asumir claves fijas ahí perdería
    datos.
    """

    type: str = BLOCK_UNKNOWN
    payload: dict[str, Any] = {}

    @model_validator(mode="before")
    @classmethod
    def _accept_raw_block(cls, data: Any) -> Any:
        """Acepta tanto `{type, payload}` como el bloque crudo del export."""
        if not isinstance(data, dict) or set(data) <= {"type", "payload"}:
            return data
        block_type = data.get("type")
        return {
            "type": block_type if isinstance(block_type, str) else BLOCK_UNKNOWN,
            "payload": {key: value for key, value in data.items() if key != "type"},
        }

    @classmethod
    def from_raw(cls, raw: Mapping[str, Any]) -> ContentBlock:
        """Construye el bloque desde un ítem crudo de `content[]`."""
        return cls.model_validate(dict(raw))

    @property
    def text(self) -> str:
        """Texto del bloque si es de tipo `text`; `""` en cualquier otro caso."""
        value = self.payload.get("text")
        if self.type == BLOCK_TEXT and isinstance(value, str):
            return value
        return ""


def text_from_blocks(blocks: Iterable[ContentBlock | Mapping[str, Any]]) -> str:
    """Reconstruye el texto de un mensaje concatenando sus bloques `text` (spec 02)."""
    parts = [
        block.text if isinstance(block, ContentBlock) else ContentBlock.from_raw(block).text
        for block in blocks
    ]
    return TEXT_JOIN.join(part for part in parts if part)


class Message(DomainModel):
    """Un turno de la conversación. `text` es el cuerpo ya plano; `blocks` el detalle."""

    id: str
    sender: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    text: str = ""
    blocks: list[ContentBlock] = []
    attachments: list[dict[str, Any]] = []

    @model_validator(mode="before")
    @classmethod
    def _derive_text(cls, data: Any) -> Any:
        """Si el export no trae `text`, se reconstruye desde los bloques (spec 02 CA-2)."""
        if not isinstance(data, dict) or data.get("text"):
            return data
        blocks = data.get("blocks")
        if not blocks:
            return data
        values: dict[str, Any] = dict(data)
        values["text"] = text_from_blocks(blocks)
        return values


class Conversation(DomainModel):
    """Una conversación con sus mensajes en el orden en que vinieron."""

    id: str
    title: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    #: `uuid` del proyecto al que pertenece, si tiene (`project_uuid` en el export).
    project_id: str | None = None
    summary: str | None = None
    messages: list[Message] = []


# ---------------------------------------------------------------------- memorias


class Memory(DomainModel):
    """Una memoria de la cuenta. El identificador es `path` (ADR-0005).

    Tres orígenes posibles, distinguidos por `extra["origin"]`: `memory_files[]` (con
    ruta real), `conversations_memory` y `project_memories{}` (con ruta sintética y
    `extra["synthetic_path"] = True`). Solo las de proyecto llevan `project_id`.
    """

    path: str
    content: str = ""
    updated_at: datetime | None = None
    #: `uuid` del proyecto dueño de la memoria; `None` para las de la cuenta.
    project_id: str | None = None


def memory_from_file(raw: Mapping[str, Any]) -> Memory:
    """Una entrada de `memory_files[]` → `Memory` con su ruta real (spec 03 CA-2)."""
    values = dict(raw)
    return Memory.model_validate(
        {
            **values,
            "path": values.get("path") or "",
            "content": values.get("content") or "",
            "origin": ORIGIN_MEMORY_FILES,
        }
    )


def conversations_memory(content: str, updated_at: object = None) -> Memory:
    """`conversations_memory` → `Memory` con la ruta sintética fija (spec 03 CA-3)."""
    return Memory.model_validate(
        {
            "path": CONVERSATIONS_MEMORY_PATH,
            "content": content,
            "updated_at": updated_at,
            "origin": ORIGIN_CONVERSATIONS_MEMORY,
            "synthetic_path": True,
        }
    )


def project_memory(project_id: str, content: str, updated_at: object = None) -> Memory:
    """Una entrada de `project_memories{}` → `Memory` ligada al proyecto (spec 03 CA-4)."""
    return Memory.model_validate(
        {
            "path": project_memory_path(project_id),
            "content": content,
            "updated_at": updated_at,
            "project_id": project_id,
            "origin": ORIGIN_PROJECT_MEMORIES,
            "synthetic_path": True,
        }
    )


# ---------------------------------------------------------------------- proyectos


class ProjectDoc(DomainModel):
    """Un documento de conocimiento del proyecto.

    `content = None` significa *el export solo trae la metadata del doc* (spec 03,
    projects CA-3); `""` significa documento vacío. No es lo mismo y no se confunden.
    """

    id: str
    filename: str | None = None
    content: str | None = None
    created_at: datetime | None = None


class Project(DomainModel):
    """Un proyecto con sus documentos y las conversaciones que lo referencian."""

    id: str
    name: str | None = None
    description: str | None = None
    #: `prompt_template` del export: el *system prompt* del proyecto.
    instructions: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    #: `creator.uuid`, no el objeto `creator` entero (spec 03, projects CA-5).
    creator_id: str | None = None
    docs: list[ProjectDoc] = []
    #: Conversaciones cuyo `project_uuid` apunta aquí; las resuelve `convert`.
    conversation_ids: list[str] = []


# ------------------------------------------------------------------------ cuenta


class Account(DomainModel):
    """Perfil de la cuenta (de `light_metadata`). Nunca tokens ni secretos."""

    id: str
    email: str | None = None
    display_name: str | None = None
    settings: dict[str, Any] = {}


# ------------------------------------------------------------------------ frames


class FrameVersion(DomainModel):
    """Una versión de un artefacto: solo metadata, el contenido no viaja en el export."""

    id: str
    title: str | None = None
    description: str | None = None
    created_at: datetime | None = None


class Frame(DomainModel):
    """Un artefacto de `frames-000/artifacts/`.

    El export no incluye el contenido real (spec 03, frames CA-2): `payload` conserva el
    JSON completo tal cual para no perder nada, y el render debe decir explícitamente
    que el contenido no está disponible.
    """

    id: str
    kind: str | None = None
    visibility: str | None = None
    owner_account: str | None = None
    updated_at: datetime | None = None
    active_version: str | None = None
    versions: list[FrameVersion] = []
    payload: dict[str, Any] = {}

    def active(self) -> FrameVersion | None:
        """Versión referenciada por `active_version`, o `None` si no coincide con ninguna.

        Que no coincida es una advertencia para el parser, no una excepción
        (spec 03, frames CA-3).
        """
        if self.active_version is None:
            return None
        return next((v for v in self.versions if v.id == self.active_version), None)


# -------------------------------------------------------------------- resultado


class ParseError(DomainModel):
    """Un ítem que no se pudo parsear. Se acumula, nunca se lanza (CLAUDE.md §4).

    Se serializa una por línea en `_report/errors.jsonl` (spec 04 CA-8).
    """

    category: str
    item_id: str | None = None
    reason: str
    source_file: str | None = None


class Report(DomainModel):
    """Qué pasó durante la corrida: errores por ítem, conteos y advertencias.

    Acumulador por diseño (ADR-0005): `frozen=True` impide sustituir los campos, y los
    parsers añaden a las colecciones con `add_error` / `add_warning` / `count`.
    """

    errors: list[ParseError] = []
    counts: dict[str, int] = {}
    warnings: list[str] = []

    def add_error(
        self,
        category: str,
        reason: str,
        item_id: str | None = None,
        source_file: str | None = None,
    ) -> ParseError:
        """Registra un ítem ilegible y devuelve el error creado."""
        error = ParseError(
            category=category, item_id=item_id, reason=reason, source_file=source_file
        )
        self.errors.append(error)
        return error

    def add_warning(self, message: str) -> None:
        """Registra algo que el usuario debería saber pero no impidió convertir."""
        self.warnings.append(message)

    def count(self, category: str, amount: int = 1) -> None:
        """Suma ítems convertidos de una categoría (alimenta `_report/summary.json`)."""
        self.counts[category] = self.counts.get(category, 0) + amount


__all__ = [
    "BLOCK_TEXT",
    "BLOCK_THINKING",
    "BLOCK_TOOL_RESULT",
    "BLOCK_TOOL_USE",
    "BLOCK_UNKNOWN",
    "CONVERSATIONS_MEMORY_PATH",
    "ORIGIN_CONVERSATIONS_MEMORY",
    "ORIGIN_MEMORY_FILES",
    "ORIGIN_PROJECT_MEMORIES",
    "PROJECT_MEMORY_DIR",
    "SENDER_ASSISTANT",
    "SENDER_HUMAN",
    "TEXT_JOIN",
    "Account",
    "ContentBlock",
    "Conversation",
    "DomainModel",
    "Frame",
    "FrameVersion",
    "Memory",
    "Message",
    "ParseError",
    "Project",
    "ProjectDoc",
    "Report",
    "conversations_memory",
    "memory_from_file",
    "project_memory",
    "project_memory_path",
    "text_from_blocks",
]

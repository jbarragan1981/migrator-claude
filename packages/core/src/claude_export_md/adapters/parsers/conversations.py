"""Parser de `conversations` (spec 03, sección `conversations`).

Lo que confirmó la Fase 0 (`docs/export-format/conversations.md`): un único
`conversations-000/conversations.json`, **array** de ~291 conversaciones y ~98 MB. Cada
ítem trae `uuid`, `name`, `summary`, fechas, `project_uuid` (nullable), `account.uuid` y
`chat_messages[]`; cada mensaje, un `content[]` con cuatro formas de bloque observadas
(`text`, `thinking`, `tool_use`, `tool_result`).

Decisiones de este módulo:

* **Streaming obligatorio (CA-C3)** — se recorre con `ijson.items(stream, "item")`. A
  diferencia de `memories` (un objeto de ~110 KB que se lee entero), aquí `json.load`
  significaría cargar ~98 MB de golpe, así que no hay techo de tamaño: no hace falta,
  porque en ningún momento vive en memoria más de una conversación.
* **Orden (CA-C5)** — `parse` emite en el orden del archivo, que ya es determinista, y
  no acumula nada. El orden canónico por `created_at` y luego `id` lo da
  `parse_sorted`, que sí materializa la lista: son ~291 entidades, no los 98 MB de JSON
  crudo. Se separan a propósito para que `convert` pueda escribir en streaming
  (cada conversación va a una ruta que depende solo de sí misma) y usar la lista
  ordenada únicamente donde el orden importa, que es el `_index.md`.
* **Mensaje sin `uuid`** — no se descarta: perder el texto de un turno por un
  identificador ausente sería peor que darle uno. Recibe el id sintético y determinista
  `<uuid de la conversación>#<posición>`, se marca con `extra["synthetic_id"]` y se avisa
  en `report.warnings`. El identificador del ÍTEM (la conversación) sí es obligatorio.
* **`chat_messages` ilegible** — la conversación se conserva igual (título, fechas y
  enlace a proyecto siguen siendo útiles) y el problema se registra en `report.errors`.
* Los campos que no mapean a la entidad (`account`, `parent_message_uuid`, …) viajan a
  `extra` (CA-C4); `chat_messages` y `project_uuid` NO, porque ya están representados en
  `messages` y `project_id` y duplicarlos sería copiar el export entero en memoria.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import ijson

from claude_export_md.domain.entities import (
    ContentBlock,
    Conversation,
    Message,
    Report,
)
from claude_export_md.errors import CorruptFileError
from claude_export_md.ports.source import JSON, ExportSource, SourceFile

logger = logging.getLogger(__name__)

#: Nombre de la categoría tal como la nombran el manifiesto y `ExportSource`.
CATEGORY = "conversations"

#: Prefijo de `ijson` para recorrer los ítems de un array raíz.
ITEM_PREFIX = "item"
#: Bytes que se leen para comprobar que la raíz es un array antes de recorrerla.
PEEK_BYTES = 64
_BOM = b"\xef\xbb\xbf"
_WHITESPACE = b" \t\r\n"

#: Claves del ítem que el parser mapea a un campo de `Conversation`.
KEY_UUID = "uuid"
KEY_NAME = "name"
KEY_SUMMARY = "summary"
KEY_PROJECT = "project_uuid"
KEY_MESSAGES = "chat_messages"
KEY_CREATED = "created_at"
KEY_UPDATED = "updated_at"
_CONVERSATION_KEYS = frozenset(
    {KEY_UUID, KEY_NAME, KEY_SUMMARY, KEY_PROJECT, KEY_MESSAGES, KEY_CREATED, KEY_UPDATED}
)

#: Claves del mensaje que el parser mapea a un campo de `Message`.
KEY_SENDER = "sender"
KEY_TEXT = "text"
KEY_CONTENT = "content"
KEY_ATTACHMENTS = "attachments"
_MESSAGE_KEYS = frozenset(
    {KEY_UUID, KEY_SENDER, KEY_TEXT, KEY_CONTENT, KEY_ATTACHMENTS, KEY_CREATED, KEY_UPDATED}
)

#: Separador del id sintético de un mensaje sin `uuid`.
SYNTHETIC_ID_SEPARATOR = "#"
#: Campo de `extra` que marca al archivo del export del que salió la conversación.
SOURCE_FILE_KEY = "source_file"

#: Fecha con la que se ordenan las conversaciones que el export trajo sin `created_at`.
_NO_DATE = datetime.min.replace(tzinfo=UTC)


def parse(source: ExportSource, report: Report) -> Iterator[Conversation]:
    """Conversaciones del export, en streaming y sin repetir `uuid` (CA-C1, CA-C3).

    No lanza: un ítem con forma inesperada o un JSON truncado se acumulan en
    `report.errors` y lo que sí se pudo leer se emite igual (CA-C2).
    """
    seen: set[str] = set()
    for file in _files(source, report):
        for conversation in _parse_file(source, file, report):
            if conversation.id in seen:
                report.add_warning(
                    f"{file.path}: conversación repetida {conversation.id}; se conserva la primera"
                )
                continue
            seen.add(conversation.id)
            report.count(CATEGORY)
            yield conversation


def parse_sorted(source: ExportSource, report: Report) -> list[Conversation]:
    """Las mismas conversaciones ya ordenadas por `created_at` y luego `id` (CA-C5).

    Materializa la colección, que es lo que hay que hacer para ordenar; lo que nunca se
    materializa es el JSON crudo. Las conversaciones sin fecha van al final (no se les
    inventa una), ordenadas entre sí por `id`.
    """
    return sorted(parse(source, report), key=sort_key)


def sort_key(conversation: Conversation) -> tuple[bool, datetime, str]:
    """Clave de orden canónico de una conversación (CA-C5)."""
    created = conversation.created_at
    return (created is None, created or _NO_DATE, conversation.id)


# ------------------------------------------------------------------- archivos


def _files(source: ExportSource, report: Report) -> list[SourceFile]:
    """Archivos JSON de la categoría, ordenados por parte y ruta (CA-C1)."""
    files = [file for file in source.files() if file.category == CATEGORY]
    for file in files:
        if file.kind != JSON:
            report.add_warning(f"{file.path}: no es JSON; se omite")
    return sorted((file for file in files if file.kind == JSON), key=lambda f: (f.part, f.path))


def _root_is_array(source: ExportSource, file: SourceFile, report: Report) -> bool:
    """Comprueba la forma de la raíz antes de recorrerla.

    Sin esto, `ijson.items(..., "item")` sobre un objeto devolvería cero conversaciones
    en silencio y el usuario no sabría por qué (CLAUDE.md §1.3).
    """
    try:
        with source.open_file(file) as stream:
            head = stream.read(PEEK_BYTES)
    except (CorruptFileError, OSError) as exc:
        report.add_error(CATEGORY, f"no se pudo abrir: {exc}", source_file=file.path)
        return False
    if head.lstrip(_BOM).lstrip(_WHITESPACE).startswith(b"["):
        return True
    report.add_error(
        CATEGORY,
        "la raíz del JSON no es un array de conversaciones: se esperaba un array",
        source_file=file.path,
    )
    return False


def _parse_file(source: ExportSource, file: SourceFile, report: Report) -> Iterator[Conversation]:
    """Recorre un archivo entero en streaming; un JSON roto corta ese archivo, no la corrida."""
    if not _root_is_array(source, file, report):
        return
    index = 0
    try:
        with source.open_file(file) as stream:
            # `use_float=True` evita los `Decimal` de ijson, que pydantic y el render
            # tendrían que volver a convertir.
            for raw in ijson.items(stream, ITEM_PREFIX, use_float=True):
                conversation = _conversation(raw, index, file, report)
                index += 1
                if conversation is not None:
                    yield conversation
    except (CorruptFileError, ijson.JSONError, OSError, UnicodeDecodeError, ValueError) as exc:
        logger.warning("Conversaciones ilegibles en %s: %s", file.path, exc)
        report.add_error(
            CATEGORY,
            f"JSON ilegible a partir del ítem {index}: {exc}",
            source_file=file.path,
        )


# -------------------------------------------------------------- conversación


def _conversation(
    raw: Any,  # noqa: ANN401 - lo que venga en el array del export
    index: int,
    file: SourceFile,
    report: Report,
) -> Conversation | None:
    """Un ítem del array → `Conversation`, o `None` si no se pudo identificar (CA-C2)."""
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
            "conversación sin `uuid`: no se puede identificar",
            item_id=item_id,
            source_file=file.path,
        )
        return None
    values: dict[str, Any] = {
        key: value for key, value in raw.items() if key not in _CONVERSATION_KEYS
    }
    values.update(
        id=uuid,
        # CA-4: `""` es un valor del export, no un campo ausente; solo `null` es ausencia.
        title=raw.get(KEY_NAME) if isinstance(raw.get(KEY_NAME), str) else None,
        summary=raw.get(KEY_SUMMARY) if isinstance(raw.get(KEY_SUMMARY), str) else None,
        created_at=raw.get(KEY_CREATED),
        updated_at=raw.get(KEY_UPDATED),
        project_id=_project_id(raw.get(KEY_PROJECT)),
        messages=_messages(raw.get(KEY_MESSAGES), uuid, file, report),
    )
    values.setdefault(SOURCE_FILE_KEY, file.path)
    return Conversation.model_validate(values)


def _project_id(raw: Any) -> str | None:  # noqa: ANN401 - `project_uuid` es nullable
    """CA-2: `project_uuid` no-null y no vacío enlaza con `Project`."""
    return raw.strip() if isinstance(raw, str) and raw.strip() else None


# -------------------------------------------------------------------- mensajes


def _messages(
    raw: Any,  # noqa: ANN401 - se comprueba la forma aquí
    conversation_id: str,
    file: SourceFile,
    report: Report,
) -> list[Message]:
    """`chat_messages[]` → `Message`; su ausencia o forma rara no tira la conversación."""
    if raw is None:
        return []
    if not isinstance(raw, Sequence) or isinstance(raw, str | bytes):
        report.add_error(
            CATEGORY,
            f"`{KEY_MESSAGES}` debería ser un array y vino {type(raw).__name__}; "
            "la conversación se conserva sin mensajes",
            item_id=conversation_id,
            source_file=file.path,
        )
        return []
    messages = []
    for position, entry in enumerate(raw):
        message = _message(entry, conversation_id, position, file, report)
        if message is not None:
            messages.append(message)
    return messages


def _message(
    raw: Any,  # noqa: ANN401 - se comprueba la forma aquí
    conversation_id: str,
    position: int,
    file: SourceFile,
    report: Report,
) -> Message | None:
    item_id = f"{conversation_id}{SYNTHETIC_ID_SEPARATOR}{position}"
    if not isinstance(raw, Mapping):
        report.add_error(
            CATEGORY,
            f"se esperaba un objeto y vino {type(raw).__name__}",
            item_id=item_id,
            source_file=file.path,
        )
        return None
    uuid = raw.get(KEY_UUID)
    synthetic = not (isinstance(uuid, str) and uuid.strip())
    if synthetic:
        report.add_warning(
            f"{file.path}: mensaje sin uuid en {conversation_id} (posición {position}); "
            f"se le asigna el id {item_id}"
        )
    values: dict[str, Any] = {key: value for key, value in raw.items() if key not in _MESSAGE_KEYS}
    values.update(
        id=item_id if synthetic else str(uuid),
        sender=raw.get(KEY_SENDER) if isinstance(raw.get(KEY_SENDER), str) else None,
        created_at=raw.get(KEY_CREATED),
        updated_at=raw.get(KEY_UPDATED),
        # Si el export no trae `text`, el propio dominio lo reconstruye desde los bloques.
        text=raw.get(KEY_TEXT) if isinstance(raw.get(KEY_TEXT), str) else "",
        blocks=_blocks(raw.get(KEY_CONTENT), item_id, file, report),
        attachments=_attachments(raw.get(KEY_ATTACHMENTS)),
    )
    if synthetic:
        values["synthetic_id"] = True
    return Message.model_validate(values)


def _attachments(raw: Any) -> list[dict[str, Any]]:  # noqa: ANN401 - hipótesis sin confirmar
    """`attachments[]` no se observó en la Fase 0; si aparece, se conserva."""
    if not isinstance(raw, Sequence) or isinstance(raw, str | bytes):
        return []
    return [dict(item) for item in raw if isinstance(item, Mapping)]


def _blocks(
    raw: Any,  # noqa: ANN401 - se comprueba la forma aquí
    message_id: str,
    file: SourceFile,
    report: Report,
) -> list[ContentBlock]:
    """CA-1: un `ContentBlock` por entrada de `content[]`, en el mismo orden.

    El tipado y la conservación del payload de esquema libre (CA-3) los resuelve el
    dominio en `ContentBlock.from_raw`; aquí solo se filtra lo que ni siquiera es un
    objeto, avisando para no descartarlo en silencio.
    """
    if not isinstance(raw, Sequence) or isinstance(raw, str | bytes):
        return []
    blocks = []
    for position, entry in enumerate(raw):
        if not isinstance(entry, Mapping):
            report.add_warning(
                f"{file.path}: bloque {position} de {message_id} no es un objeto "
                f"({type(entry).__name__}); se omite"
            )
            continue
        blocks.append(ContentBlock.from_raw(entry))
    return blocks


__all__ = ["CATEGORY", "parse", "parse_sorted", "sort_key"]

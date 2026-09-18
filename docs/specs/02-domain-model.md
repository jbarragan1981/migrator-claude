# 02 — Modelo de dominio

## Objetivo
Entidades pydantic v2 que representan el export de forma independiente del formato de origen y del formato de salida.

## Entidades (mínimo)
```
Export        id, format_version, exported_at?, account?, conversations[], projects[], memories[], frames[], report
Account       id, email?, display_name?, settings: dict (sin tokens/secretos)
Conversation  id, title, created_at, updated_at, project_id?, messages[], summary?, extra
Message       id, sender ("human"|"assistant"|str), created_at, text, blocks[ContentBlock], attachments[], extra
ContentBlock  type ("text"|"tool_use"|"tool_result"|"artifact"|"image"|str), payload: dict
Project       id, name, description?, instructions?, created_at, updated_at, docs[ProjectDoc], conversation_ids[], extra
ProjectDoc    id, filename, content, created_at, extra
Memory        path (p. ej. "/people/ana.md"), content, updated_at?, extra
Frame         id, kind?, payload: dict   ← provisional hasta Fase 0
Report        errors[ParseError], counts: dict, warnings[]
ParseError    category, item_id?, reason, source_file
```

## Reglas
- `model_config = ConfigDict(extra="allow", frozen=True)` en todas.
- Todo opcional salvo `id` (o `path` en Memory). Fechas `datetime` con tz UTC; si el origen no trae tz, se asume UTC y se marca `extra["tz_assumed"]=True`.
- `Message.text` se deriva de `blocks` si viene vacío (concatenar bloques `text`).
- Sin métodos de I/O en el dominio.

## Criterios de aceptación
- **CA-1** Un dict con claves desconocidas se valida y las claves quedan accesibles en `model_extra`.
- **CA-2** Un `Message` sin `text` pero con dos bloques `text` expone `text` = ambos unidos por `\n\n`.
- **CA-3** `Conversation` con `created_at` naive se normaliza a UTC y marca `tz_assumed`.
- **CA-4** Las entidades son hashables/inmutables (frozen) y `model_dump(mode="json")` es serializable.
- **CA-5** Cambiar cualquier campo de esta lista exige un ADR (hook `stop_check` lo recuerda).

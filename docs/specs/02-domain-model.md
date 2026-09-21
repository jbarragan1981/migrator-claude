# 02 — Modelo de dominio

## Objetivo
Entidades pydantic v2 que representan el export de forma independiente del formato de origen y del formato de salida.

## Entidades (mínimo)
Implementadas en `packages/core/src/claude_export_md/domain/entities.py`. Los campos marcados con ⬅ son ajustes de ADR-0005 sobre la lista original, obligados por lo que confirmó la Fase 0 (`docs/export-format/`).
```
Export        id, format_version, exported_at?, account?, conversations[], projects[], memories[], frames[], report
              ⬅ AÚN NO IMPLEMENTADA: se decide al escribir usecases/convert.py
Account       id, email?, display_name?, settings: dict (sin tokens/secretos)
Conversation  id, title, created_at, updated_at, project_id?, messages[], summary?, extra
Message       id, sender ("human"|"assistant"|str), created_at, updated_at? ⬅, text, blocks[ContentBlock], attachments[], extra
ContentBlock  type ("text"|"thinking" ⬅|"tool_use"|"tool_result"|"artifact"|"image"|str), payload: dict
Project       id, name, description?, instructions?, created_at, updated_at, creator_id? ⬅, docs[ProjectDoc], conversation_ids[], extra
ProjectDoc    id, filename, content: str|None ⬅ (None = no viaja en el export), created_at, extra
Memory        path, content, updated_at?, project_id? ⬅, extra
Frame         id, kind?, visibility? ⬅, owner_account? ⬅, updated_at? ⬅, active_version? ⬅, versions[FrameVersion] ⬅, payload: dict
FrameVersion  id, title?, description?, created_at   ⬅ nueva
Report        errors[ParseError], counts: dict, warnings[]   ⬅ acumulador: add_error/add_warning/count
ParseError    category, item_id?, reason, source_file   ⬅ solo entidad, no hay excepción homónima en errors.py
```
`Memory` cubre los tres orígenes del export real (`memory_files[]`, `conversations_memory`, `project_memories{}`); las dos últimas reciben una ruta sintética (`CONVERSATIONS_MEMORY_PATH`, `project_memory_path()`) y se marcan con `extra.origin` / `extra.synthetic_path`. Ver ADR-0005.

## Reglas
- `model_config = ConfigDict(extra="allow", frozen=True)` en todas.
- Todo opcional salvo `id` (o `path` en Memory). Fechas `datetime` con tz UTC; si el origen no trae tz, se asume UTC y se marca `extra["tz_assumed"]=True`.
- `Message.text` se deriva de `blocks` si viene vacío (concatenar bloques `text`).
- Sin métodos de I/O en el dominio.

## Criterios de aceptación
- **CA-1** Un dict con claves desconocidas se valida y las claves quedan accesibles en `model_extra`.
- **CA-2** Un `Message` sin `text` pero con dos bloques `text` expone `text` = ambos unidos por `\n\n`.
- **CA-3** `Conversation` con `created_at` naive se normaliza a UTC y marca `tz_assumed`.
- **CA-4** Las entidades son inmutables (frozen; hashables las que no tienen colecciones) y `model_dump(mode="json")` es serializable.
- **CA-5** Cambiar cualquier campo de esta lista exige un ADR (hook `stop_check` lo recuerda).
- **CA-6** Una fecha ilegible no invalida el ítem: el campo queda en `None` y el valor original se conserva en `extra["<campo>_raw"]`.

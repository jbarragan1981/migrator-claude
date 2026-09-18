# 03 — Parsers por categoría

> Este spec se completa con lo que descubra la Fase 0 (`docs/export-format/`). Las secciones marcadas ⚠️ son hipótesis a verificar, no requisitos.

## Objetivo
Un parser por categoría que convierta los archivos de origen en entidades de dominio, en streaming, tolerando esquema.

## Interfaz común
```python
def parse(source: ExportSource, category: str, report: Report) -> Iterator[Entity]
```
Registrado en `usecases/convert.py` por nombre de categoría y versión de formato.

## Criterios comunes a todos
- **CA-C1** Multi-parte: dadas `part 0..n`, se concatenan en orden y no se duplican ítems por `id`.
- **CA-C2** Ítem corrupto → `report.errors += ParseError(...)`; el iterador continúa.
- **CA-C3** Sin `json.load` de archivos > 10 MB (test con archivo sintético de 50 MB y límite de memoria).
- **CA-C4** Campos desconocidos preservados en `extra`.
- **CA-C5** Orden de salida determinista (por `created_at`, luego `id`).

## conversations ⚠️
- Origen probable: `conversations.json` (array) dentro de `conversations-NNN`.
- Cada ítem: `uuid, name, created_at, updated_at, chat_messages[]`; cada mensaje: `uuid, sender, text, content[], created_at, attachments[], files[]`.
- **CA-1** Mensaje con `content[]` de tipos mixtos produce `blocks` en el mismo orden.
- **CA-2** Conversación con `project_uuid` enlaza a `Project`.
- **CA-3** Artefactos embebidos en el texto (`<antArtifact …>`) se extraen como `ContentBlock(type="artifact")` con `title`, `language`, `identifier`.

## memories ⚠️
- Origen probable: `memories.json` con lista de archivos `{path, content, updated_at}` o carpeta de `.md`.
- **CA-1** Cada memoria conserva su `path` original; el frontmatter YAML que ya traiga no se duplica.
- **CA-2** Se exportan también al árbol de salida respetando subcarpetas (`people/`, `areas/`, `topics/`).

## projects ⚠️
- Origen probable: `projects.json` con `uuid, name, description, prompt_template (instrucciones), docs[{uuid, filename, content}]`.
- **CA-1** Cada `ProjectDoc` genera un archivo propio; `instructions` va a `project.md`.
- **CA-2** Las conversaciones del proyecto se enlazan por `project_uuid` desde `conversations`.

## light_metadata ⚠️
- Origen probable: `users.json` / cuenta y configuración.
- **CA-1** Se excluyen campos que parezcan credenciales (`token`, `secret`, `key`, `password`) y se registran en `report.warnings`.

## frames ❓
- Desconocido. **CA-1**: hasta terminar Fase 0, el parser genérico guarda cada ítem como `Frame(payload=item)` y un `.md` con el JSON en bloque de código.

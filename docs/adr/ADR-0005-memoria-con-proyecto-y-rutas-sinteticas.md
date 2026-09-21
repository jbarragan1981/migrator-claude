# ADR-0005: `Memory` lleva `project_id` y ruta sintética para las memorias sin ruta
Fecha: 2026-09-19   Estado: Aceptada
## Contexto
El spec 02 modela `Memory` como `path, content, updated_at?, extra`, heredado de la hipótesis de CLAUDE.md §6 de que `memories` era una carpeta de archivos `.md` (`/profile.md`, `/people/*.md`). La Fase 0 (`docs/export-format/memories.md`) la descartó: en `batched-manifest` (2026) hay **un único JSON por cuenta** con `{account_uuid, conversations_memory: str, memory_files: [{content, path, updated_at}], project_memories: {<project_uuid>: str}}`. O sea **tres orígenes** de memoria, y solo uno (`memory_files[]`) trae `path`:
- `memory_files[]` — tiene `path` y `updated_at` propios.
- `conversations_memory` — una sola cadena a nivel de cuenta, sin `path` y sin fecha.
- `project_memories{}` — una cadena por proyecto, sin `path` y sin fecha, **ligada a un `Project` por uuid** (spec 03, `memories` CA-4).

`Memory` tal como está no puede representar ese enlace a proyecto ni distinguir una ruta real de una inventada. Modificar la lista de entidades del spec 02 exige un ADR (spec 02 CA-5). Este ADR cubre además los demás ajustes del modelo de dominio que la Fase 0 obliga a hacer (`ProjectDoc`, `Frame`, `ParseError`, `Report`), para no abrir cinco ADRs por la misma tanda de evidencia.

## Decisión
1. **`Memory.project_id: str | None = None`** — nuevo campo. No `None` solo para las entradas de `project_memories{}`; es la misma clave de enlace que ya usa `Conversation.project_id`, así que el render (`projects/<slug>/`) los agrupa igual sin lógica especial.
2. **Las memorias sin ruta propia reciben una ruta sintética, definida en el dominio, no en el parser**, para que parser y render usen la misma constante:
   - `CONVERSATIONS_MEMORY_PATH = "/_conversations_memory.md"`
   - `project_memory_path(project_id) -> "/_project_memories/<uuid>.md"`
   El prefijo `_` mantiene la ruta sintética distinguible de un `path` real del export (`/profile.md`, `/people/x.md`) **dentro del dominio**: Anthropic no emite rutas con esa forma en la muestra.

   > **Corrección (revisión de M1).** Este punto decía que el prefijo `_` evitaba la sobrescritura silenciosa en disco. No es cierto: `slugify` quita el `_` al construir el nombre del archivo, así que la salida real es `memories/conversations-memory.md` y un `/conversations_memory.md` del export slugificaría igual. Quien impide de verdad la pisada es `rendering.render.assign_output_paths`, que al detectar dos rutas de salida iguales le da a **ambas** el hash corto de su `Memory.path` original. El prefijo `_` sigue siendo útil como marca de "esto lo inventamos nosotros", nada más.
3. **El origen se marca en `extra`, no en campos nuevos**: `origin` (`"memory_files" | "conversations_memory" | "project_memories"`) y `synthetic_path: True` cuando la ruta la puso la herramienta. `extra="allow"` ya los lleva al frontmatter bajo `extra:` (CLAUDE.md §5) sin tocar el esquema. Los helpers `memory_from_file` / `conversations_memory` / `project_memory` del dominio construyen las tres variantes con esos marcadores puestos.
4. **Un solo módulo `domain/entities.py`** para todas las entidades (más `domain/dates.py` para la normalización de fechas), en línea con CLAUDE.md §3 (`domain/ ← entidades pydantic: …`). Un módulo por entidad sería una decena de archivos de veinte líneas con importaciones cruzadas.
5. Ajustes menores de la misma tanda, todos justificados por Fase 0:
   - `ProjectDoc.content: str | None` — `None` significa *no está en el export* (`projects` CA-3: `docs[]` solo trae metadata), distinto de `""` (doc vacío). El parser emite un `warning`, no inventa contenido.
   - `Frame` gana `visibility`, `owner_account`, `updated_at`, `active_version`, `versions[FrameVersion]` además de `id`/`kind`/`payload`; `payload` sigue guardando el JSON completo tal cual (`frames` CA-2, el contenido real del artefacto no viaja en el export).
   - `Project.creator_id` (de `creator.uuid`, `projects` CA-5) y `Message.updated_at` (presente en todos los mensajes reales).
   - `ParseError` es **solo** un modelo de dominio serializable a `_report/errors.jsonl`; no se añade una excepción homónima a `errors.py` pese a la redacción de CLAUDE.md §4, porque dos `ParseError` distintos en el mismo paquete es una trampa segura. Nada lanza `ParseError`: se acumula.
   - `Report` es frozen como el resto, pero es un **acumulador**: `add_error` / `add_warning` / `count` mutan sus listas internas. `frozen=True` en pydantic impide sustituir el campo, no mutar la lista que contiene; la interfaz de los parsers del spec 03 (`parse(source, category, report)`) necesita exactamente eso.
   - No se crea `Export` todavía: `usecases/convert.py` aún no existe y no está decidido si el ensamblado es una entidad o un iterador perezoso por categoría. Crearla ahora sería adivinar; se decidirá al escribir `convert`.

## Alternativas consideradas
- **Una entidad `ProjectMemory` aparte** — duplica `path`/`content`/`updated_at`/render por un único campo de diferencia, y obliga a un segundo renderizador de Markdown.
- **Dejar el enlace a proyecto solo en `extra["project_uuid"]`** — funciona por tolerancia, pero el enlace conversación↔proyecto es parte del contrato de salida (CLAUDE.md §5); un campo que el render necesita sí o sí no puede vivir en el saco de lo desconocido.
- **Ruta sintética con el nombre del proyecto** (`/_project_memories/<slug-del-proyecto>.md`) — más legible, pero el parser de `memories` solo ve el uuid: dependería del orden de parseo entre categorías y dejaría de ser determinista si falta el proyecto. El slug legible es problema del render, que sí tiene ambos lados.
- **`Memory.source: Literal[...]` en vez de `extra["origin"]`** — un campo más en el esquema para algo que `extra` ya transporta hasta el frontmatter; se descartó por la regla de no sobre-diseñar (spec 02: todo opcional salvo el identificador).

## Consecuencias
+ Las tres formas de memoria se parsean, se ordenan y se renderizan con un solo tipo y una sola plantilla.
+ `path` sigue siendo el identificador de `Memory` y sigue siendo único, también para las sintéticas.
+ El frontmatter dice de dónde salió cada memoria (`extra.origin`), que es justo lo que el usuario necesita para entender un archivo que no existía en Claude.ai.
— El spec 02 se actualizó en el mismo cambio que este ADR (`docs/specs/02-domain-model.md`); este ADR queda como referencia de la decisión, no como pendiente.
— Si un export real trae un `memory_files[].path` que empiece por `_`, habrá dos memorias con nombres parecidos; es visible y sin pérdida de datos, pero conviene revisarlo cuando se lea un export sin anonimizar (`memories.md`, "Dudas": el valor real de `path` aún no se ha visto).

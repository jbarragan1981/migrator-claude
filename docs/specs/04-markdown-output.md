# 04 — Salida Markdown

## Objetivo
Un árbol de archivos `.md` navegable en Obsidian, VS Code y GitHub, autocontenido, determinista y con enlaces relativos.

## Árbol (contrato)
Ver `docs/output-layout.md` (copia de la sección 5 de CLAUDE.md). Resumen:
```
output/{README.md, _index.md, _report/, account/, memories/, projects/<slug>/, conversations/YYYY/MM/, frames/}
```

Quién escribe ese árbol: `usecases/convert.py` renderiza y manda cada archivo al puerto `MarkdownSink` (`ports/sink.py`, ADR-0006) con su **ruta relativa POSIX**. `FilesystemSink` es la única implementación hoy (UTF-8 y `\n` siempre); los nombres del árbol (`_index.md`, `README.md`, `_report/{summary.json,errors.jsonl,inventory.json}`) son constantes de `rendering/index.py`, no del sink.

## Frontmatter (todas las entidades)
`id, type, title, created_at, updated_at, source_file, project_id?, tags[], extra?` — ISO-8601 UTC.

## Criterios de aceptación
- **CA-1** Dado un fixture de 3 conversaciones, cuando convierto dos veces, entonces `diff -r` entre ambas salidas está vacío.
- **CA-2** Cada `.md` tiene frontmatter YAML válido (parseable con `python-frontmatter`) con los campos obligatorios.
- **CA-3** Conversación con mensajes `human`/`assistant` renderiza encabezados `## 👤 Usuario` / `## 🤖 Claude` con timestamp `HH:MM`.
- **CA-4** Un bloque `tool_use` se renderiza dentro de `<details>` y no rompe el Markdown circundante.
- **CA-5** Un artefacto de 120 líneas se escribe en `artifacts/01-<slug>.<ext>` y el cuerpo contiene un enlace relativo a él.
- **CA-6** Título con caracteres no ASCII ("Análisis Ñandú / Q3") produce slug `analisis-nandu-q3`.
- **CA-7** `_index.md` lista todas las conversaciones ordenadas por fecha descendente con enlace relativo, proyecto y nº de mensajes.
- **CA-8** `_report/summary.json` contiene conteos por categoría y nº de errores; `errors.jsonl` una línea por `ParseError`.
- **CA-9** Con `--templates ./mis-plantillas`, una plantilla sobreescrita reemplaza a la default y las demás siguen funcionando.
- **CA-10** El cuerpo del `.md` nunca contiene la fecha de generación ni la versión de la herramienta.

## Plantillas (para `--templates ./mis-plantillas`)
Las plantillas por defecto están en `packages/core/src/claude_export_md/rendering/templates/`. Una plantilla propia con el mismo nombre de archivo reemplaza a la de la librería; las demás siguen viniendo de la librería (CA-9). El entorno (`rendering.render.build_environment`) usa `StrictUndefined`: una variable que no exista falla en vez de escribir un hueco.

Filtros disponibles en todas las plantillas (registrados en `rendering.render.FILTERS`; esta tabla y ese diccionario son el mismo contrato):
| filtro | para qué |
|---|---|
| `yaml_value` | un valor detrás de `clave: ` en el frontmatter (cita/escapa lo que haga falta, un texto multilínea sale como bloque `\|-`) |
| `yaml_inline` | una lista corta en estilo de flujo: `[memory, memory-files]` |
| `yaml_block` | un mapa indentado, para colgarlo de `extra:` |
| `slugify` | ASCII minúsculas, máx. 60 caracteres (CA-6) |
| `iso_utc` | `datetime` → `2026-09-18T16:59:47Z` |
| `hhmm` | `datetime` → `14:32` en UTC, para el encabezado de cada turno (CA-3) |
| `code_fence` | envuelve un texto en una cerca ``` más larga que cualquiera que traiga dentro (CA-4) |
| `md_cell` | un valor dentro de una celda de tabla: escapa `\|`, `[`, `]` y `\`, colapsa los saltos de línea y muestra `—` si no hay valor (CA-7) |

### `memory.md.j2`
Variables: `memory` (la entidad completa), `id` (= `Memory.path`), `type` (`"memory"`), `title`, `created_at` (siempre `None`: el export no trae fecha de creación de una memoria), `updated_at`, `source_file`, `project_id` (solo en las de `project_memories`), `tags`, `extra`, `content`.

Dos decisiones que el export no trae resueltas (ver el docstring de `rendering/render.py`):
- **Título** — una memoria no tiene `title`. Se usa el último segmento de `Memory.path` sin la extensión (`/people/Ana María.md` → `Ana María`); las dos memorias de ruta sintética (ADR-0005) llevan un título fijo que dice qué son (`Memoria de conversaciones`, `Memoria del proyecto <uuid>`).
- **Nombre del archivo** — `Memory.path` viene del export y no tiene por qué ser un nombre válido en disco, así que la salida conserva la jerarquía con cada segmento slugificado: `/people/Ana María.md` → `memories/people/ana-maria.md`, `/_project_memories/<uuid>.md` → `memories/project-memories/<uuid>.md`. Si dos rutas distintas slugifican igual, AMBAS reciben el hash corto de su ruta original, para que el nombre de cada archivo dependa solo de su propia ruta y no del orden de la colección (CA-1). No aplica el patrón `YYYY-MM-DD_<slug>_<uuid8>.md` de las conversaciones: una memoria no tiene ni uuid ni fecha de creación, y su ruta ya es única.

### `conversation.md.j2` [IMPLEMENTADO]
Variables: `conversation` (la entidad completa), `id`, `type` (`"conversation"`), `title`, `created_at`, `updated_at`, `source_file`, `project_id` (solo si `project_uuid` no era null), `summary`, `message_count`, `tags`, `extra`, `turns`.

`turns` es una lista de `{heading, message, parts}`, una por mensaje. Cada `part` es `{kind, text}` si el bloque era de texto (se inserta tal cual) o `{kind, summary, body}` en cualquier otro caso (va dentro de `<details>`).

Decisiones que el export no trae resueltas (ver el docstring de `rendering/conversations.py`):
- **Nombre del archivo** — `conversations/YYYY/MM/YYYY-MM-DD_<slug>_<uuid8>.md`. La fecha es `created_at` y, si falta, `updated_at`; si no hay ninguna la conversación va a `conversations/sin-fecha/<slug>_<uuid8>.md` (no se inventa una fecha). El `uuid8` son los 8 primeros caracteres alfanuméricos del `uuid`; con un identificador más corto se usa un hash corto y estable.
- **Colisiones de ruta** — dos conversaciones del mismo día, con el mismo título y con los mismos 8 caracteres de `uuid8` piden el mismo archivo. `rendering.conversations.ConversationPaths` desempata: la primera que reclama la ruta se la queda y las siguientes reciben el hash corto de su `id` (`…_a1a1a1a1-<hash>.md`), **más** una advertencia en `Report.warnings` que acaba en `_report/summary.json`. Nunca se sobrescribe en silencio (CLAUDE.md §1.3). A diferencia de las memorias —donde `assign_output_paths` ve la colección entera y le da el hash a AMBAS— aquí el desempate es incremental porque las conversaciones se escriben en streaming; sigue siendo determinista porque el orden de lectura del export lo es, y el `_index.md` enlaza siempre la ruta ya desempatada.
- **Título** — `name` puede ser `""` (spec 03, conversations CA-4). El frontmatter muestra entonces `Conversación sin título` y el slug del archivo cae en `sin-titulo` (el fallback de `slugify`), no en la frase entera.
- **Encabezados** — `## 👤 Usuario — 14:32` / `## 🤖 Claude — 14:32` (CA-3); sin la hora si el mensaje no trae fecha, y `## 💬 <sender>` para cualquier remitente que no sea `human`/`assistant`.
- **Bloques no textuales** — resumen visible por tipo: `🧠 Razonamiento`, `🔧 Uso de herramienta: <tool>`, `📋 Resultado de <tool>` (con `(error)` si `is_error`) y `❓ Bloque <tipo>` para lo que no conocemos. Dentro va primero lo legible (razonamiento, entrada de la herramienta, salida) y después sus metadatos como JSON con las claves ordenadas. De los metadatos se quitan las claves de PRIMER nivel que valen `null` (en el export real son la mayoría: integraciones y MCP sin usar); el bloque íntegro sigue en `ContentBlock.payload`, el `.md` es una vista. No se poda el interior de `input`/`display_content`, que son de esquema libre (spec 03, conversations CA-3).

**Umbral de extracción de artefactos: 40 líneas.** El skill `markdown-template` (regla 7) dice "no se pegan inline si superan 40 líneas" y CA-5 pide que un artefacto de 120 líneas acabe en `artifacts/01-<slug>.<ext>`. No se contradicen: 40 es el umbral y 120 lo supera, así que con 40 se cumplen los dos. Lo que se extrae son las **cercas de código** dentro del texto del mensaje, no mensajes enteros: la Fase 0 no observó bloques `artifact` ni `<antArtifact>` en el export (spec 03, conversations CA-5). La extensión sale del lenguaje de la cerca (```` ```python ```` → `.py`; desconocido → `.txt`) y el nombre, de un archivo mencionado justo antes de la cerca si su extensión coincide con la del lenguaje (``Te dejo `scripts/ventas.py`:`` → `01-ventas.py`), si no del propio lenguaje (`01-python.py`). Los artefactos van en `conversations/YYYY/MM/<nombre del .md sin extensión>/artifacts/NN-<nombre>.<ext>` y el cuerpo deja en su lugar un enlace relativo.

### `index.md.j2` y `readme.md.j2` [IMPLEMENTADO]

Las dos plantillas de la raíz de la salida, que arma `rendering/index.py` y escribe
`usecases/convert.py`. Como las demás, son sustituibles con `--templates` (CA-9).

`index.md.j2` (el `_index.md`, CA-7). Variables: `conversations`, `memories`
(filas ya ordenadas: `{day, title, link, project, messages}`), `conversation_count`,
`memory_count`. Decisiones:

- **Qué lista** — CA-7 solo exige la tabla de conversaciones (fecha descendente, enlace
  relativo, proyecto y nº de mensajes). Se añade una segunda tabla con las memorias: son
  la mitad de lo que M1 escribe y quedarían sin puerta de entrada. Va en su propia
  sección, de modo que una plantilla propia pueda quitarla sin tocar la otra.
- **Orden** — fecha descendente, `id` ascendente para desempatar; lo que no tiene fecha
  va al final con `—` en la columna (no se le inventa una).
- **Proyecto** — hasta el parser de `projects` (M2) no hay nombre que mostrar: se
  imprime el `project_uuid` crudo, que es lo que trae el export.

`readme.md.j2` (el `README.md`, CLAUDE.md §5). Variables: `source`, `format_version`,
`counts`, `export_created_at`, `missing_categories`. La única fecha que aparece es la
del **manifiesto** (`created_at`, cuándo generó Anthropic el export); si el export no
trae manifiesto o está roto, la fila simplemente no se imprime. Nunca se usa el reloj de
la corrida (CA-10, CLAUDE.md §1.4).

### `_report/` [IMPLEMENTADO]

`summary.json` (CA-8) lleva `categories` (conteo por categoría), `error_count`,
`errors_file`, `warning_count` y `warnings` (enteras, no solo contadas: son lo que hay
que leer cuando algo salió raro pero la corrida terminó bien), más el contexto del
export convertido (`source`, `format_version`, `export_created_at`,
`missing_categories`, `converted_categories`). `errors.jsonl` lleva una línea JSON por
`ParseError` y **se escribe siempre**, aunque quede vacío, para que el árbol de salida
tenga la misma forma haya habido problemas o no. `inventory.json` es el mismo inventario
del spec 01, guardado junto a la salida como constancia de qué traía el export.

**Lo que M1 no escribe todavía**: `projects/`, `frames/` y `account/`. No se crean
carpetas vacías; el `README.md` generado lo dice explícitamente.

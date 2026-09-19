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
Variables: `conversation` (la entidad completa), `id`, `type` (`"conversation"`), `title`, `created_at`, `updated_at`, `source_file`, `project_id` (solo si `project_uuid` no era null), `project_title` y `project_link` (el proyecto ya resuelto por `usecases/links.py` y el enlace relativo a su `project.md`; ambos `None` si el `project_uuid` no corresponde a ningún proyecto del export), `summary`, `message_count`, `tags`, `extra`, `turns`.

`turns` es una lista de `{heading, message, parts}`, una por mensaje. Cada `part` es `{kind, text}` si el bloque era de texto (se inserta tal cual) o `{kind, summary, body}` en cualquier otro caso (va dentro de `<details>`).

Decisiones que el export no trae resueltas (ver el docstring de `rendering/conversations.py`):
- **Nombre del archivo** — `conversations/YYYY/MM/YYYY-MM-DD_<slug>_<uuid8>.md`. La fecha es `created_at` y, si falta, `updated_at`; si no hay ninguna la conversación va a `conversations/sin-fecha/<slug>_<uuid8>.md` (no se inventa una fecha). El `uuid8` son los 8 primeros caracteres alfanuméricos del `uuid`; con un identificador más corto se usa un hash corto y estable.
- **Colisiones de ruta** — dos conversaciones del mismo día, con el mismo título y con los mismos 8 caracteres de `uuid8` piden el mismo archivo. `rendering.conversations.ConversationPaths` desempata: la primera que reclama la ruta se la queda y las siguientes reciben el hash corto de su `id` (`…_a1a1a1a1-<hash>.md`), **más** una advertencia en `Report.warnings` que acaba en `_report/summary.json`. Nunca se sobrescribe en silencio (CLAUDE.md §1.3). A diferencia de las memorias —donde `assign_output_paths` ve la colección entera y le da el hash a AMBAS— aquí el desempate es incremental porque las conversaciones se escriben en streaming; sigue siendo determinista porque el orden de lectura del export lo es, y el `_index.md` enlaza siempre la ruta ya desempatada.
- **Título** — `name` puede ser `""` (spec 03, conversations CA-4). El frontmatter muestra entonces `Conversación sin título` y el slug del archivo cae en `sin-titulo` (el fallback de `slugify`), no en la frase entera.
- **Encabezados** — `## 👤 Usuario — 14:32` / `## 🤖 Claude — 14:32` (CA-3); sin la hora si el mensaje no trae fecha, y `## 💬 <sender>` para cualquier remitente que no sea `human`/`assistant`.
- **Bloques no textuales** — resumen visible por tipo: `🧠 Razonamiento`, `🔧 Uso de herramienta: <tool>`, `📋 Resultado de <tool>` (con `(error)` si `is_error`) y `❓ Bloque <tipo>` para lo que no conocemos. Dentro va primero lo legible (razonamiento, entrada de la herramienta, salida) y después sus metadatos como JSON con las claves ordenadas. De los metadatos se quitan las claves de PRIMER nivel que valen `null` (en el export real son la mayoría: integraciones y MCP sin usar); el bloque íntegro sigue en `ContentBlock.payload`, el `.md` es una vista. No se poda el interior de `input`/`display_content`, que son de esquema libre (spec 03, conversations CA-3).

**Umbral de extracción de artefactos: 40 líneas.** El skill `markdown-template` (regla 7) dice "no se pegan inline si superan 40 líneas" y CA-5 pide que un artefacto de 120 líneas acabe en `artifacts/01-<slug>.<ext>`. No se contradicen: 40 es el umbral y 120 lo supera, así que con 40 se cumplen los dos. Lo que se extrae son las **cercas de código** dentro del texto del mensaje, no mensajes enteros: la Fase 0 no observó bloques `artifact` ni `<antArtifact>` en el export (spec 03, conversations CA-5). La extensión sale del lenguaje de la cerca (```` ```python ```` → `.py`; desconocido → `.txt`) y el nombre, de un archivo mencionado justo antes de la cerca si su extensión coincide con la del lenguaje (``Te dejo `scripts/ventas.py`:`` → `01-ventas.py`), si no del propio lenguaje (`01-python.py`). Los artefactos van en `conversations/YYYY/MM/<nombre del .md sin extensión>/artifacts/NN-<nombre>.<ext>` y el cuerpo deja en su lugar un enlace relativo.

### `account.md.j2` [IMPLEMENTADO]

El perfil de la cuenta (`light_metadata` → entidad `Account`). Variables: `account` (la
entidad completa), `id` (el `uuid`), `type` (`"account"`), `title`, `created_at` y
`updated_at` (**siempre `None`**: `light_metadata` no trae ninguna fecha de la cuenta),
`source_file`, `tags` (siempre `[account]`), `extra`, `email`, `display_name` y
`settings` (pares `(clave, valor)` ya ordenados). El cuerpo es una tabla con los tres
campos del perfil y, solo si el export trae `settings`, una sección `## Configuración`;
sin `settings` no se imprime una sección vacía.

Decisiones que el export no trae resueltas (ver el docstring de `rendering/render.py`):
- **Ruta** — `account/account.md` es la única ruta **fija** del árbol (CLAUDE.md §5): no
  depende de ningún texto del export, al revés que memorias y conversaciones.
- **Varias cuentas** — el export observado trae una sola, pero el parser no asume
  longitud 1 (spec 03, `light_metadata` CA-3). Si llegaran varias, NINGUNA se queda
  `account/account.md`: todas pasan a `account/account-<hash8 del id>.md` y queda una
  advertencia en `Report.warnings` → `_report/summary.json`. Así el nombre fijo nunca
  significa en silencio "la primera de varias" y, como en las memorias, el nombre de
  cada archivo depende solo de su propio `id` y no del orden de la colección.
- **Título** — una cuenta no tiene `title`: se usa `full_name`, si no el correo, y si
  tampoco, el `uuid`. Nunca un título inventado.
- **Credenciales** — el frontmatter nunca puede mostrar un secreto: el parser ya
  sustituye el VALOR de cualquier campo cuyo nombre parezca una credencial (spec 03,
  `light_metadata` CA-2). `verified_phone_number` sí se muestra: es un dato de perfil.

### `project.md.j2` y `project_doc.md.j2` [IMPLEMENTADO]

Un proyecto (`projects` → entidad `Project`) y cada uno de sus documentos (`ProjectDoc`).
Salida: `projects/<slug del nombre>/project.md` y
`projects/<slug>/docs/<slug del filename>.md` (CLAUDE.md §5).

`project.md.j2`. Variables: `project` (la entidad completa), `id`, `type` (`"project"`),
`title`, `created_at`, `updated_at`, `source_file`, `creator_id`, `tags` (`[project]`),
`extra`, `description`, `instructions`, `docs` (filas `{doc, title, filename,
created_at, link, available, status}`), `doc_count`, `conversations` (los uuids),
`conversation_rows` (las mismas conversaciones ya resueltas a archivo: `{id, title,
link, day}`, ordenadas por fecha descendente y con `link` relativo al `project.md`) y
`notes` (las frases fijas de las secciones sin nada que mostrar).

`project_doc.md.j2`. Variables: `doc`, `project`, `id`, `type` (`"project_doc"`),
`title`, `created_at`, `updated_at` (**siempre `None`**: el export no trae fecha de
actualización de un documento), `source_file` (el del proyecto: salieron del mismo
archivo), `project_id`, `project_title`, `project_link`, `filename`, `tags`
(`[project-doc, project]`), `extra`, `content` y `notice`.

Decisiones que el export no trae resueltas (ver el docstring de `rendering/render.py`):
- **Un archivo por documento** — cada doc es una entidad propia y no una sección del
  `project.md`, porque el día que se sepa dónde vive su contenido (spec 03, projects
  CA-3) el archivo ya existe y solo hay que llenarlo.
- **Contenido no disponible** — `ProjectDoc.content is None` significa *el export no lo
  trae* (ADR-0005). El `.md` del documento lo dice con todas las letras
  (`DOC_CONTENT_UNAVAILABLE`) y la tabla del proyecto lo marca en su columna
  `Contenido`; nunca se escribe un archivo vacío ni se inventa texto. Si un export futuro
  sí trae el contenido, se inserta tal cual, como cualquier Markdown del usuario.
- **Colisiones** — si dos proyectos slugifican igual (`Q3: Ventas` y `Q3 / Ventas`),
  AMBOS llevan el hash corto de su `id` (como en las memorias: el nombre depende solo de
  la propia entidad, no del orden de la colección). Lo mismo entre los documentos de un
  mismo proyecto.
- **Título** — el `name` del proyecto (`Proyecto sin título` si venía vacío) y, en un
  documento, su `filename` COMPLETO: la extensión es parte del nombre que el usuario ve
  en Claude.ai y no siempre es `.md`. La extensión solo se quita para calcular el nombre
  del archivo de salida.
- **Secciones vacías** — `description` e `instructions` en `""` son un valor del export
  (spec 03, projects CA-2): la sección se imprime diciendo que está vacía y solo se omite
  cuando el campo es `None`. Sin documentos y sin conversaciones enlazadas se dice
  explícitamente, en vez de dejar una sección muda.
- **Conversaciones** — el archivo del proyecto no las trae (spec 03, projects CA-4): las
  cruza `usecases/links.py` desde `conversations[].project_uuid` mientras `convert`
  escribe. Con el cruce hecho, la sección es una tabla de `conversation_rows` (título,
  enlace relativo y fecha); si solo hay `Project.conversation_ids` (una plantilla que
  renderiza el proyecto por su cuenta) se enumeran los uuids; y si no hay ninguna, se
  dice explícitamente en vez de dejar la sección muda.

### `frame.md.j2` [IMPLEMENTADO]

Un artefacto (`frames` → entidad `Frame`). Salida: `frames/<slug>.md`, **plano**
(CLAUDE.md §5 dejaba la categoría "por investigar"; la Fase 0 ya la resolvió y un
artefacto es UN archivo, sin hijos que colgar como los documentos de un proyecto).

Variables: `frame` (la entidad completa), `id`, `type` (`"frame"`), `title`, `created_at`
(**derivado**: la fecha de la versión más antigua de `versions[]`), `updated_at`,
`source_file`, `kind`, `visibility`, `owner_account`, `active_version` (tal cual vino),
`active` (la versión activa ya resuelta, o `None`), `versions` (filas `{version, id,
title, description, created_at, active}`), `version_count`, `tags` (`[frame, <kind>]`),
`extra`, `payload_json` (el JSON original completo ya formateado, `""` si no hay),
`notice` y `notes` (`no_versions`, `no_active_version`, `payload_available`,
`active_unmatched`).

Decisiones que el export no trae resueltas (ver el docstring de `rendering/render.py`):
- **Contenido no disponible** — ningún campo observado trae el código, el documento o la
  imagen del artefacto (spec 03, frames CA-2). El `.md` lo dice con todas las letras
  (`FRAME_CONTENT_UNAVAILABLE`, el mismo criterio que `DOC_CONTENT_UNAVAILABLE` en los
  documentos de proyecto) y además publica el JSON original íntegro (`Frame.payload`) en
  un `<details>`, para que no se pierda nada mientras se averigua dónde vive. El aviso de
  que ese JSON está abajo solo se imprime si de verdad hay JSON que enseñar.
- **Título** — el artefacto no tiene título propio, lo tienen sus versiones: se usa el de
  la versión activa; si `active_version` no coincide con ninguna, el de la primera
  versión que traiga uno; si ninguna, el `kind` (lo que el export dice que es) y, en
  último caso, `Artefacto sin título`. Nunca un título inventado.
- **Fecha de creación** — tampoco hay `created_at` a nivel de artefacto: se DERIVA de la
  versión más antigua. Es un dato del export, no el reloj de la corrida (CA-10); si
  ninguna versión tiene fecha, el campo va en `null`. El orden canónico de la colección,
  en cambio, lo da `updated_at` (spec 03, frames CA-C5).
- **Colisiones** — dos artefactos cuyo título slugifique igual llevan AMBOS el hash corto
  de su `id`, como en memorias y proyectos.
- **Versión activa incoherente** — si `active_version` no corresponde a ninguna versión
  (spec 03, frames CA-3), el archivo lo cuenta (`ACTIVE_VERSION_UNMATCHED_NOTE`) en vez
  de callarse la incoherencia; el parser ya dejó su advertencia en el `Report`.

### `index.md.j2` y `readme.md.j2` [IMPLEMENTADO]

Las dos plantillas de la raíz de la salida, que arma `rendering/index.py` y escribe
`usecases/convert.py`. Como las demás, son sustituibles con `--templates` (CA-9).

`index.md.j2` (el `_index.md`, CA-7). Una sección por categoría convertida, cada una con
sus filas ya ordenadas: `conversations` (`{day, title, link, project, project_link,
messages}`), `projects` (`{day, title, link, conversations, docs}`), `memories`
(`{day, title, link, project, project_link}`), `frames` (`{day, title, link, kind,
content}`) y `accounts` (`{title, link}`), más un contador por sección
(`conversation_count`, `project_count`, `memory_count`, `frame_count`,
`account_count`). Decisiones:

- **Qué lista** — CA-7 solo exige la tabla de conversaciones (fecha descendente, enlace
  relativo, proyecto y nº de mensajes). Hay una sección por categoría convertida porque
  un índice que nombrara solo una parte dejaría el resto del árbol sin puerta de
  entrada; cada una es independiente, de modo que una plantilla propia pueda quitar la
  que no le interese sin tocar las demás. Una sección sin filas no se imprime (no hay
  tablas vacías), y si no se convirtió nada el índice lo dice y remite a
  `_report/errors.jsonl`.
- **Orden** — fecha descendente, `id` ascendente para desempatar; lo que no tiene fecha
  va al final con `—` en la columna (no se le inventa una). La clave es la misma de
  `rendering/links.py`, compartida con la lista de conversaciones del `project.md`.
- **Proyecto** — si `Conversation.project_id` (o `Memory.project_id`) resuelve a un
  proyecto del export, la columna muestra su NOMBRE con enlace relativo a
  `projects/<slug>/project.md`; el cruce lo hace `usecases/links.py`. Si no resuelve
  —proyecto ausente, export sin `projects`— se imprime el `project_uuid` crudo, que es
  lo que trae el export, sin enlace: nunca se inventa uno roto.
- **Artefactos** — la columna `Contenido` dice si el export trae o no el contenido del
  artefacto; hoy siempre dice que no (spec 03, frames CA-2), con la misma frase que usa
  la tabla de documentos del proyecto.

`readme.md.j2` (el `README.md`, CLAUDE.md §5). Variables: `source`, `format_version`,
`counts`, `export_created_at`, `missing_categories`. La única fecha que aparece es la
del **manifiesto** (`created_at`, cuándo generó Anthropic el export); si el export no
trae manifiesto o está roto, la fila simplemente no se imprime. Nunca se usa el reloj de
la corrida (CA-10, CLAUDE.md §1.4). La sección "Cómo está organizado" se construye a
partir de `counts`: solo enumera las carpetas que ESTE export produjo, porque las que no
se escribieron no existen. La sección "Lo que el export no trae" solo aparece cuando hay
proyectos o artefactos, que son los que llegan sin contenido.

### `_report/` [IMPLEMENTADO]

`summary.json` (CA-8) lleva `categories` (conteo por categoría), `error_count`,
`errors_file`, `warning_count` y `warnings` (enteras, no solo contadas: son lo que hay
que leer cuando algo salió raro pero la corrida terminó bien), más el contexto del
export convertido (`source`, `format_version`, `export_created_at`,
`missing_categories`, `converted_categories`). `errors.jsonl` lleva una línea JSON por
`ParseError` y **se escribe siempre**, aunque quede vacío, para que el árbol de salida
tenga la misma forma haya habido problemas o no. `inventory.json` es el mismo inventario
del spec 01, guardado junto a la salida como constancia de qué traía el export.

### El árbol completo [IMPLEMENTADO en M2]

`usecases/convert.py` escribe ya las cinco categorías, en este orden: `memories` →
`account` → (se parsean los proyectos) → `conversations` → `projects` → `frames` →
`_index.md`, `README.md` y `_report/`. Los proyectos se parsean ANTES que las
conversaciones —para que cada conversación pueda nombrar el suyo mientras se escribe en
streaming— y se ESCRIBEN después, porque su `project.md` enumera las conversaciones que
lo referencian y esa lista solo está completa al terminar el streaming.

Una categoría que el export no traiga no genera una carpeta vacía: simplemente no
aparece, y el `README.md` generado solo enumera lo que de verdad se escribió.

**El enlace conversación ↔ proyecto** (spec 03, projects CA-4) lo resuelve
`usecases/links.py` (`ProjectLinker`), el único sitio que ve las dos colecciones:

- hacia adelante, cada conversación recibe el `ProjectLink` de su proyecto y lo muestra
  en su `.md` (`Proyecto: [Nombre](../../../projects/<slug>/project.md)`) y en la
  columna `Proyecto` del `_index.md`;
- hacia atrás, cada `project.md` enumera sus conversaciones con título, enlace relativo
  y fecha, y `Project.conversation_ids` queda poblado (el parser lo deja vacío a
  propósito);
- si un `project_uuid` no resuelve, la conversación se convierte igual con su uuid
  crudo y sin enlace, y la corrida deja UNA advertencia agregada en
  `_report/summary.json` (una por corrida, no una por conversación: un export sin la
  categoría `projects` produciría cientos de líneas idénticas).

Las rutas relativas entre archivos las calcula `rendering/links.py` con `posixpath`, no
con `os.path`: el mismo export tiene que producir el mismo texto en Windows y en Linux
(CA-1).

# CLAUDE.md — claude-export-md

Herramienta que convierte una exportación de datos de Claude.ai (los zips `conversations-000`, `memories-000`, `projects-000`, `frames-000`, `light_metadata-000` + el `member-manifest-*.json`) en una carpeta navegable de archivos Markdown, para conservar la información de una cuenta antigua y poder moverla a otra herramienta (Obsidian, Notion, otro Claude, un repo).

Monorepo: **`core` (librería Python pura) → `cli` (Typer) → `api` (FastAPI) → `web` (Angular)**. El valor está en `core`; todo lo demás son puertas de entrada.

---

## 1. Principios no negociables

1. **`core` no conoce HTTP, ni Angular, ni la consola.** Es una librería Python instalable con `pip`/`uv`, sin dependencias de framework. Si algo de `core` importa `fastapi`, `typer` o `rich`, es un bug.
2. **Primero el inventario, después el parser.** El formato del export de Anthropic cambia y no está documentado oficialmente. NUNCA escribas un parser "de memoria": antes ejecuta el comando `inventory` (sección 6) sobre la carpeta real, mira las claves reales, y a partir de eso escribe fixtures y luego el parser.
3. **Tolerante a esquema.** Todo campo es opcional salvo el identificador. Un campo desconocido se conserva en `raw`/frontmatter, nunca se descarta en silencio. Una conversación que no se pueda parsear se registra en `_report/errors.jsonl` y NO detiene la corrida.
4. **Idempotente y determinista.** Correr dos veces sobre el mismo export produce exactamente los mismos archivos (mismos nombres, mismo orden, mismas fechas en UTC ISO-8601). Sin `datetime.now()` en el contenido generado.
5. **Nada sale de la máquina del usuario.** No hay telemetría, no hay llamadas a Internet. El `export_url` del manifiesto NO se usa (es de un solo uso y expira); el input siempre es lo que ya está en disco.
6. **Datos privados.** Los fixtures de test se anonimizan (`scripts/anonymize_fixture.py`). Nunca se commitea un export real. `exports/`, `output/` y `*.zip` están en `.gitignore`.

---

## 2. Stack

| Capa | Tecnología | Por qué |
|---|---|---|
| Python | 3.12+, **uv** (workspace), **ruff**, **mypy --strict**, **pytest** | uv gestiona el workspace de los 3 paquetes Python con un solo lockfile |
| Modelos | **pydantic v2** | Validación + `model_dump()` para frontmatter; `extra="allow"` para tolerar esquema |
| JSON grande | **ijson** (streaming) | `conversations.json` puede pesar cientos de MB; nunca `json.load()` completo |
| Markdown | **Jinja2** templates + `python-frontmatter` | Plantillas editables por el usuario, frontmatter YAML estándar |
| CLI | **Typer** + **rich** | Barra de progreso, salida legible, `--help` gratis |
| API | **FastAPI** + **uvicorn** | Async, OpenAPI automático → cliente Angular generado |
| Jobs | En memoria (`asyncio`) en v1; interfaz `JobStore` para cambiar a SQLite/Redis después | La conversión dura minutos; no bloquear el request |
| Front | **Angular 21** standalone components + **signals**, **Angular Material**, **Tailwind 3**, **Transloco** (es/en) | Mismo stack que ya usa el equipo; sin NgModules |
| Cliente HTTP | `openapi-typescript-codegen` desde `/openapi.json` | Un solo contrato, tipos sincronizados |
| Empaquetado | `pyproject` publicable (`uvx claude-export-md`), **Docker Compose** (api + web), binario opcional con **PyInstaller** | Tres formas de que "le sirva a otros" (sección 9) |
| Tareas | **justfile** en raíz | Un comando por tarea, funciona igual en Windows (con `just`), macOS y Linux |
| Node | **pnpm** solo para `apps/web` | El resto del repo no necesita Node |
| CI | GitHub Actions: `lint → typecheck → test → build` | Falla si baja la cobertura de `core` por debajo del 85 % |

No introducir: Nx/Turborepo (sobredimensionado para 4 paquetes), ORM, base de datos en v1, NgRx (signals bastan), Celery.

---

## 3. Estructura del monorepo

```
claude-export-md/
├── CLAUDE.md                      ← este archivo
├── README.md                      ← para usuarios finales (quick start < 5 min)
├── justfile
├── pyproject.toml                 ← uv workspace: members = packages/core, apps/cli, apps/api
├── uv.lock
├── docker-compose.yml
├── .github/workflows/ci.yml
├── docs/
│   ├── adr/                       ← decisiones (ADR-0001-hexagonal.md, ADR-0002-streaming.md, …)
│   ├── export-format/             ← lo que descubrimos del formato: un .md por categoría + JSON de ejemplo anonimizado
│   └── output-layout.md           ← contrato de la carpeta de salida (sección 5)
├── packages/
│   └── core/                      ← claude_export_md (librería)
│       ├── src/claude_export_md/
│       │   ├── domain/            ← entidades pydantic: Export, Conversation, Message, ContentBlock, Project, ProjectDoc, Memory, Frame, Account
│       │   ├── ports/             ← Protocols: ExportSource, MarkdownSink, ProgressReporter
│       │   ├── adapters/
│       │   │   ├── source_folder.py     ← lee carpetas ya extraídas (caso principal)
│       │   │   ├── source_zip.py        ← lee los .zip directamente
│       │   │   ├── manifest.py          ← parsea member-manifest-*.json (solo para validar categorías/partes)
│       │   │   ├── parsers/             ← un módulo por categoría: conversations.py, memories.py, projects.py, frames.py, light_metadata.py
│       │   │   └── sink_filesystem.py   ← escribe el árbol Markdown
│       │   ├── rendering/         ← Jinja2 templates + filtros (slugify, fecha, code fences)
│       │   ├── usecases/          ← inventory.py, convert.py, validate.py
│       │   └── __init__.py        ← API pública: `convert(source, dest, options) -> Report`
│       ├── tests/
│       │   ├── fixtures/          ← exports mínimos ANONIMIZADOS por versión de formato (v2025-legacy/, v2026-batched/)
│       │   └── test_*.py
│       └── pyproject.toml
├── apps/
│   ├── cli/                       ← `claude-export-md inventory|convert|validate|serve`
│   ├── api/                       ← FastAPI: routers/, schemas/, services/, jobs/
│   └── web/                       ← Angular: src/app/{core,shared,features/{upload,inventory,jobs,browser}}
└── scripts/
    └── anonymize_fixture.py
```

Regla de dependencia (solo hacia adentro): `web → api → core`, `cli → core`. `core` no importa de nadie.

---

## 4. Arquitectura de `core` (hexagonal)

```
 ExportSource (port)                                   MarkdownSink (port)
 ┌──────────────────┐                                  ┌──────────────────┐
 │ FolderSource     │   inventory → parse → normalize  │ FilesystemSink   │
 │ ZipSource        │ ───────────────────────────────▶ │ (futuro: ZipSink,│
 └──────────────────┘        → render → write          │  ObsidianVault)  │
                                                       └──────────────────┘
```

Pipeline de `convert`:

1. **inventory** — recorre el input, detecta versión de formato (`legacy-single-zip` vs `batched-manifest`), lista archivos por categoría, tamaño, y muestreo de claves JSON (primer nivel + `chat_messages[0]`). Devuelve `Inventory`, serializable a JSON. Es el mismo comando que el usuario ve.
2. **parse** — por categoría, con *streaming* (`ijson.items(f, "item")`). Cada parser devuelve un iterador de entidades de dominio. Nunca carga todo el archivo en memoria.
3. **normalize** — fechas a UTC, texto de mensajes reconstruido desde `content[]` (bloques `text`, `tool_use`, `tool_result`, artefactos), slugs únicos y estables (`YYYY-MM-DD_slug-del-titulo_uuid8`), enlaces conversación ↔ proyecto.
4. **render** — Jinja2, una plantilla por tipo. El usuario puede sobreescribir plantillas con `--templates ./mis-plantillas`.
5. **write** — `MarkdownSink.write(path, content)`; genera además `_index.md` por carpeta y `_report/summary.json`.

Errores: excepciones propias en `core/errors.py` (`UnknownFormatError`, `CorruptFileError`, `ParseError(item_id, reason)`). `convert` nunca lanza por un ítem; acumula en `Report.errors`.

---

## 5. Contrato de la carpeta de salida

```
output/
├── README.md                          ← qué es esto, cuándo se generó el export (fecha del manifiesto, no de la corrida)
├── _index.md                          ← tabla maestra: conversaciones, proyectos, memorias con enlaces relativos
├── _report/{summary.json, errors.jsonl, inventory.json}
├── account/
│   └── account.md                     ← de light_metadata (perfil, configuración, sin tokens ni secretos)
├── memories/
│   ├── profile.md                     ← se respeta la ruta original de cada memoria (/profile.md, /people/*.md, /areas/*.md…)
│   ├── people/… areas/… topics/…
│   └── _index.md
├── projects/
│   └── <slug-proyecto>/
│       ├── project.md                 ← nombre, descripción, instrucciones (system prompt) del proyecto
│       ├── docs/<slug-doc>.md         ← conocimiento del proyecto
│       └── conversations/ → enlaces relativos a las conversaciones del proyecto
├── conversations/
│   └── YYYY/MM/
│       └── YYYY-MM-DD_slug_uuid8.md
└── frames/                            ← categoría aún por investigar en Fase 0; tratar como "adjuntos/artefactos" hasta confirmar
```

Frontmatter obligatorio en cada `.md`: `id`, `type` (`conversation|project|project_doc|memory|frame|account`), `title`, `created_at`, `updated_at`, `source_file`, `project_id` (si aplica), `tags`. Campos desconocidos del JSON original van bajo `extra:`.

Conversación (cuerpo): encabezado `## 👤 Usuario` / `## 🤖 Claude` con timestamp, texto en Markdown tal cual, bloques `tool_use`/`tool_result` colapsados en `<details>`, artefactos extraídos a `conversations/YYYY/MM/<slug>/artifacts/<nombre>.<ext>` y enlazados.

---

## 6. Fase 0 (obligatoria antes de cualquier parser)

Ejecutar sobre la carpeta real del usuario:

```bash
uv run claude-export-md inventory ./exports/mi-cuenta --out docs/export-format/inventory.json
```

Con el resultado, por CADA categoría (`conversations`, `memories`, `projects`, `frames`, `light_metadata`):

1. Documentar en `docs/export-format/<categoria>.md`: nombre(s) de archivo dentro de la carpeta, tipo (array/objeto/carpeta de .md), claves de primer nivel, claves de los ítems hijos, ejemplo anonimizado de 1 ítem.
2. Crear fixture mínimo (2–3 ítems) en `packages/core/tests/fixtures/v2026-batched/<categoria>/`.
3. Escribir el test **antes** que el parser (`test_parse_<categoria>.py`).
4. Recién entonces escribir `adapters/parsers/<categoria>.py`.

Lo que se sabe hoy (verificar, no asumir): las exportaciones grandes llegan como manifiesto + zips por lote (`part` puede ser > 0 para categorías grandes → el parser debe concatenar partes); el formato legacy era un solo zip con `conversations.json`, `projects.json`, `users.json`; las memorias son un conjunto de archivos Markdown con rutas (`/profile.md`, `/people/*.md`…) y `updated_at` por archivo; en conversaciones cada mensaje tiene `sender` (`human`/`assistant`), `text` y un `content[]` con bloques tipados. `frames` es desconocido: investigar primero.

---

## 7. Convenciones

**Python**
- `ruff format` + `ruff check --fix`; `mypy --strict` en `core`; `from __future__ import annotations`.
- Modelos pydantic: `model_config = ConfigDict(extra="allow", frozen=True)`.
- Funciones puras en `usecases/`; I/O solo en `adapters/`.
- Logging con `logging` estándar (`claude_export_md.*`), nunca `print` en `core`.
- Tests: `pytest` + `pytest-cov`; un test por regla de negocio; fixtures anonimizados; test de **snapshot** del Markdown generado (`syrupy`) para detectar cambios de render.

**Angular**
- Standalone components, `inject()`, signals + `computed()`, `ChangeDetectionStrategy.OnPush`, sin `any`.
- Estructura por *feature*; `core/` solo servicios singleton y el cliente API generado.
- Formularios: Angular Material *outline*; tablas: Angular Material (PrimeNG solo si hace falta virtual scroll para miles de conversaciones).
- Textos SIEMPRE por Transloco (`assets/i18n/es.json`, `en.json`); español es el idioma por defecto.
- Sin lógica de parseo en el front. El front solo: sube/indica la ruta, muestra inventario, lanza job, muestra progreso (SSE), navega el resultado.

**API**
- `POST /exports` (multipart zip o `{ "path": "..." }` en modo local) → `201 {export_id}`
- `GET /exports/{id}/inventory`
- `POST /exports/{id}/convert` → `202 {job_id}`
- `GET /jobs/{id}` y `GET /jobs/{id}/events` (SSE de progreso)
- `GET /exports/{id}/output/tree` y `GET /exports/{id}/output/file?path=`
- `GET /exports/{id}/download` (zip del output)
- Errores como RFC 7807 (`application/problem+json`). Versionar bajo `/api/v1`.

**Git**
- Conventional Commits (`feat(core): …`, `fix(api): …`). Un ADR por decisión de arquitectura en `docs/adr/`.

---

## 8. Comandos

```bash
just setup          # uv sync + pnpm install
just inventory DIR  # uv run claude-export-md inventory DIR
just convert DIR OUT
just test           # pytest (core, cli, api) + ng test
just lint           # ruff + mypy + eslint
just api            # uvicorn apps.api.main:app --reload
just web            # pnpm -C apps/web start
just up             # docker compose up --build  (api :8000, web :4200)
just gen-client     # regenera apps/web/src/app/core/api desde http://localhost:8000/openapi.json
```

---

## 9. Distribución ("que le sirva a otros de manera sencilla")

Tres niveles, del más simple al más completo; los tres usan el mismo `core`:

1. **Solo CLI, sin instalar nada permanente**: `uvx claude-export-md convert ./mi-export ./salida`. Para gente técnica. Publicar en PyPI.
2. **Interfaz web local con Docker**: `git clone … && docker compose up` → abrir `http://localhost:4200`, arrastrar los zips o el manifiesto, descargar el zip con los Markdown. Nada sale de su máquina.
3. **Ejecutable único (Windows/macOS)**: PyInstaller sobre `cli serve` que levanta la API + el build estático de Angular y abre el navegador. Para gente no técnica. Es la meta de la v2.

El input aceptado en los tres casos: (a) carpeta con las subcarpetas ya extraídas, (b) carpeta con los `.zip` sin extraer, (c) el `member-manifest-*.json` junto a los zips — en este caso el manifiesto solo sirve para validar que están las 5 categorías y todas las `part`; los `export_url` se ignoran.

---

## 10. Orden de construcción (roadmap)

- **M0** Esqueleto del monorepo, `justfile`, CI en verde, `core` vacío con `inventory` funcionando sobre la carpeta real.
- **M1** Parsers + Markdown para `memories` (el más pequeño y el más valioso) y `conversations`. CLI `convert` usable. Snapshot tests.
- **M2** `projects` (con enlace a sus conversaciones), `light_metadata`, `frames`. `_index.md` global.
- **M3** FastAPI con jobs y SSE; Docker Compose.
- **M4** Angular: upload → inventario → progreso → navegador del resultado → descarga.
- **M5** Publicar en PyPI, plantillas personalizables, ejecutable único.

---

## 11. Lo que NO hay que hacer

- No usar `json.load()` sobre `conversations.json`.
- No hardcodear nombres de archivo del export: se descubren en `inventory`.
- No poner lógica de negocio en routers de FastAPI ni en componentes Angular.
- No borrar campos que no reconocemos; van a `extra:`.
- No hacer peticiones a `claude.ai` ni a los `export_url`.
- No commitear datos reales, ni siquiera "un ejemplito".
- No crear un nuevo paquete si el código encaja en uno existente.

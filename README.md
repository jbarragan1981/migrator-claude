# claude-export-md

Convierte una exportación de datos de Claude.ai (los zips `conversations-000`,
`memories-000`, `projects-000`, `frames-000`, `light_metadata-000` + el
`member-manifest-*.json`) en una carpeta de Markdown navegable — conversaciones,
memorias, proyectos y artefactos — para conservarla o pasarla a otra herramienta
(Obsidian, Notion, otro Claude, un repo propio).

**Privacidad**: todo se procesa en tu máquina. Nada sale a Internet, no hay
telemetría, y el `export_url` del manifiesto (de un solo uso) nunca se usa —
el punto de partida siempre es lo que ya tenés en disco o subís vos mismo.

Este repo está en desarrollo activo (ver [`docs/specs/STATUS.md`](docs/specs/STATUS.md)
para el estado real). Hoy: el motor de conversión (`core`) y la CLI cubren las
5 categorías del export; la API (`apps/api`) expone subida, conversión en
background con progreso y descarga; el front web (`apps/web`, Angular) cubre
todo el flujo (subir el export → ver el inventario → convertir con progreso →
navegar y descargar el resultado). **Si no sos programador/a, la Opción 2
(Docker Compose) es la que te conviene**: un solo comando levanta el backend
y el front juntos, sin instalar Python, Node ni nada más que Docker.

---

## Paso 0 — Exportar tus datos desde Claude.ai

Antes de usar esta herramienta necesitás el backup que genera la propia
Claude.ai (esta app no se conecta a tu cuenta, solo procesa lo que ya
descargaste):

1. Entrá a [claude.ai](https://claude.ai) con la cuenta que querés exportar.
2. Abrí tu perfil (esquina inferior izquierda) → **Settings / Configuración**
   → sección **Account / Cuenta** → **Export data / Exportar datos**.
3. Confirmá la solicitud. Anthropic arma el export de forma asíncrona (puede
   tardar minutos u horas) y te avisa **por correo electrónico** cuando está
   listo.
4. Desde ese correo descargás uno o varios `.zip` (`conversations-000.zip`,
   `memories-000.zip`, `projects-000.zip`, `frames-000.zip`,
   `light_metadata-000.zip` — los nombres varían según cuánto contenido
   tengas) y un `member-manifest-*.json`. **El enlace de descarga expira en
   pocos días**: bajá los archivos a una carpeta local apenas estén
   disponibles, no dependas del enlace más adelante.
5. Guardalos juntos en una carpeta de tu máquina (por ejemplo
   `./exports/mi-cuenta/`). No hace falta descomprimir los `.zip` — tanto la
   CLI como la API los aceptan tal como llegan, junto con el manifiesto.

Con esa carpeta ya podés seguir con cualquiera de las tres opciones de abajo.
Recordá el principio de privacidad del proyecto: nada de lo que subas o
proceses sale de tu máquina (ver [`CLAUDE.md`](CLAUDE.md) §1.5).

---

## Opción 1 — Línea de comandos (la más simple)

Requisitos: [uv](https://docs.astral.sh/uv/) y Python 3.12+.

```bash
git clone <este-repo>
cd migrator-claude
uv sync

# Ver qué trae tu export sin convertir nada
uv run claude-export-md inventory /ruta/a/tu/export

# Convertir de verdad
uv run claude-export-md convert /ruta/a/tu/export ./salida
```

`inventory` acepta una carpeta con las 5 subcarpetas ya extraídas, un `.zip`, o
el `member-manifest-*.json` junto a los zips. `convert` produce el árbol en
`./salida`: `README.md`, `_index.md`, `memories/`, `conversations/YYYY/MM/`,
`projects/<slug>/`, `frames/`, `account/`, `_report/{summary.json,errors.jsonl}`.

Ver `uv run claude-export-md --help` y [`docs/specs/05-cli.md`](docs/specs/05-cli.md)
para el resto de las opciones (`--overwrite`, `--templates`, `--quiet`).

## Opción 2 — Todo con Docker Compose (backend + front, recomendado)

La forma más simple si no querés instalar nada de Python/Node ni tocar la
terminal más que para copiar y pegar dos comandos. Requisitos: solo
[Docker](https://www.docker.com/) (con Compose, incluido en Docker Desktop).

```bash
git clone <este-repo>
cd migrator-claude
docker compose up -d --build
```

La primera vez tarda unos minutos (arma las dos imágenes). Cuando termine,
abrí **`http://localhost:4200`** en el navegador: ahí está la interfaz web
completa (subir el export del Paso 0 → ver el inventario → convertir con
progreso → navegar y descargar el resultado), sin que tengas que llamar a la
API a mano. El front habla con el backend a través del propio contenedor
(`http://localhost:8000` también queda expuesta si querés mirar la
documentación interactiva en `http://localhost:8000/docs`).

Para bajar todo: `docker compose down`. Para actualizar después de bajar
cambios nuevos del repo: `docker compose up -d --build` de nuevo (reconstruye
solo lo que cambió).

### Solo la API, sin front (por ejemplo para automatizar con `curl`)

```bash
docker compose up -d api
```

Por defecto el modo `{"path": "..."}` está desactivado (`CEM_ALLOW_LOCAL_PATHS=false`):
la única forma de entrada es subir tus zips por multipart, igual que haría un
front real.

Flujo típico con `curl`:

```bash
# 1. Subir el export (zips y/o el manifiesto)
curl -F "file=@conversations-000.zip" -F "file=@memories-000.zip" \
     -F "file=@member-manifest-2026-01-01.json" \
     http://localhost:8000/api/v1/exports
# → {"export_id": "..."}

# 2. Ver qué contiene
curl http://localhost:8000/api/v1/exports/<export_id>/inventory

# 3. Convertir (corre en background, devuelve un job)
curl -X POST http://localhost:8000/api/v1/exports/<export_id>/convert
# → {"job_id": "..."}

# 4. Seguir el progreso (streaming de eventos por categoría)
curl -N http://localhost:8000/api/v1/jobs/<job_id>/events

# 5. Cuando termine: navegar el árbol, leer un archivo o descargar el zip
curl http://localhost:8000/api/v1/exports/<export_id>/output/tree
curl "http://localhost:8000/api/v1/exports/<export_id>/output/file?path=_index.md"
curl -o resultado.zip http://localhost:8000/api/v1/exports/<export_id>/download

# 6. Limpiar
curl -X DELETE http://localhost:8000/api/v1/exports/<export_id>
```

Variables de entorno (con default) configurables en `docker-compose.yml`:
`CEM_ALLOW_LOCAL_PATHS=false`, `CEM_MAX_UPLOAD_MB=2048`, `CEM_JOB_TIMEOUT_S=300`.

Contrato completo de la API: [`docs/specs/06-api.md`](docs/specs/06-api.md).

## Opción 3 — Interfaz web en modo desarrollo (para tocar código)

Pensada para quien va a modificar el proyecto (recarga en caliente del front,
logs directos de la API). Si solo querés *usar* la app, la Opción 2 (Docker)
te ahorra instalar Python/Node/`just`.

Requisitos: [uv](https://docs.astral.sh/uv/) + Python 3.12+, Node 20+ con
`pnpm` (`corepack enable`), y [`just`](https://github.com/casey/just) (el
runner de comandos del `justfile` — si `just setup`/`just web` te dice
`command not found`, es porque falta instalar esto: `winget install
casey.just` en Windows, `brew install just` en macOS, o `cargo install just`
si ya tenés Rust).

```bash
git clone <este-repo>
cd migrator-claude
just setup     # uv sync + pnpm -C apps/web install (una sola vez)
```

**Terminal 1 — backend** (API en `http://localhost:8000`):

```bash
just api
```

**Terminal 2 — front** (Angular en `http://localhost:4200`, con proxy a la
API para evitar problemas de CORS):

```bash
just web
```

Con los dos corriendo, abrí `http://localhost:4200` en el navegador. El
flujo de la app (spec 07) es:

1. **Inicio** — arrastrá o elegí los `.zip` y el `member-manifest-*.json`
   del Paso 0 y tocá "Subir y continuar" (`POST /exports`).
2. **Inventario** — se muestra qué trae el export por categoría (archivos,
   tamaño, ítems aproximados, avisos); tocá "Continuar".
3. **Conversión** — arranca sola (`POST /exports/{id}/convert`) y muestra el
   progreso en vivo por categoría (SSE); al terminar, "Ver resultado".
4. **Resultado** — árbol navegable del Markdown generado, con buscador,
   previsualización de archivos de texto y un botón "Descargar zip"
   (`GET /exports/{id}/download`) con el resultado completo.

No hace falta memorizar ninguna URL de la API: el front la consume entera.

---

## Desarrollo

Requisitos: [uv](https://docs.astral.sh/uv/), [just](https://github.com/casey/just),
Node 20+ con `pnpm` (vía `corepack enable`).

```bash
just setup     # uv sync + pnpm install
just test      # pytest (core, cli, api) + tests del front
just lint      # ruff + mypy --strict (core) + eslint
just api       # uvicorn con --reload, para desarrollo local sin Docker
just up        # docker compose up --build
```

Reglas del proyecto, arquitectura y decisiones: [`CLAUDE.md`](CLAUDE.md).
Specs por área: [`docs/specs/`](docs/specs/). Estado real de cada milestone:
[`docs/specs/STATUS.md`](docs/specs/STATUS.md).

## Qué falta / limitaciones conocidas

- El contenido real de los documentos de un proyecto y de los artefactos
  (`frames`) no viene en el export de Claude.ai — el `.md` generado lo dice
  explícitamente en vez de inventarlo.
- El front web (`apps/web`) cubre el flujo completo, tanto en Docker
  (Opción 2, imagen nginx que sirve el build de producción) como en modo
  desarrollo (Opción 3). Falta todavía la pantalla de Ajustes real (cambio de
  idioma) y la publicación en PyPI / ejecutable único (M5).
- Detalle completo de lo hecho y lo pendiente en `docs/specs/STATUS.md`.

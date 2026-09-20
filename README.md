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
background con progreso y descarga; el front web (`apps/web`) todavía no existe
(planeado para más adelante).

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

## Opción 2 — API con Docker Compose

Requisitos: [Docker](https://www.docker.com/) con Compose.

```bash
git clone <este-repo>
cd migrator-claude
docker compose build api
docker compose up -d api
```

Esto levanta la API en `http://localhost:8000` (documentación interactiva en
`http://localhost:8000/docs`, contrato OpenAPI en `http://localhost:8000/openapi.json`).
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

Para bajar todo: `docker compose down`.

## Opción 3 — Interfaz web

Todavía no existe (front Angular planeado, ver
[`docs/specs/07-web.md`](docs/specs/07-web.md) y `STATUS.md`). Cuando esté
lista, `docker compose up` va a levantar API + web juntos.

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
- Front web (M4) y publicación en PyPI / ejecutable único (M5) todavía no
  existen.
- Detalle completo de lo hecho y lo pendiente en `docs/specs/STATUS.md`.

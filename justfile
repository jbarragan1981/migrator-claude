set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

default:
    @just --list

setup:
    uv sync
    pnpm -C apps/web install

inventory DIR:
    uv run claude-export-md inventory "{{DIR}}" --out docs/export-format/inventory.json

inventory-raw DIR:
    uv run python scripts/inventory_raw.py "{{DIR}}" --out docs/export-format/inventory.json

convert DIR OUT:
    uv run claude-export-md convert "{{DIR}}" "{{OUT}}"

test:
    uv run pytest packages/core apps/cli apps/api -q --cov=claude_export_md --cov-fail-under=85
    pnpm -C apps/web exec ng test --watch=false

lint:
    uv run ruff check .
    uv run ruff format --check .
    uv run mypy --strict packages/core
    pnpm -C apps/web lint

api:
    uv run uvicorn claude_export_md_api.main:app --reload --port 8000

web:
    pnpm -C apps/web start

up:
    docker compose up --build

gen-client:
    # Dos ajustes sobre el comando "de libro" (necesita la API corriendo, `just api`):
    # 1. El paquete se llama `openapi-typescript-codegen` pero el binario que instala
    #    (ver su package.json -> "bin") se llama `openapi`, no el nombre del paquete.
    # 2. openapi-typescript-codegen@0.31 resuelve $refs con una version de
    #    json-schema-ref-parser que ya no acepta una URL http(s) como --input
    #    directo (falla con "Unable to resolve $ref pointer" antes de leer nada,
    #    confirmado con curl/fetch funcionando bien contra la misma URL): se baja
    #    el openapi.json a un archivo temporal primero y se le apunta a ESE archivo.
    node -e "fetch('http://localhost:8000/openapi.json').then(r=>r.text()).then(t=>require('fs').writeFileSync('apps/web/.openapi-gen-client.json', t))"
    pnpm -C apps/web exec openapi --input .openapi-gen-client.json --output src/app/core/api --client angular
    node -e "require('fs').rmSync('apps/web/.openapi-gen-client.json')"

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
    pnpm -C apps/web test --watch=false

lint:
    uv run ruff check . && uv run ruff format --check . && uv run mypy --strict packages/core
    pnpm -C apps/web lint

api:
    uv run uvicorn claude_export_md_api.main:app --reload --port 8000

web:
    pnpm -C apps/web start

up:
    docker compose up --build

gen-client:
    pnpm -C apps/web exec openapi-typescript-codegen --input http://localhost:8000/openapi.json --output src/app/core/api --client angular

# Build context: raíz del repo (necesita packages/core, dependencia de workspace de uv).
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY packages/core packages/core
COPY apps/api apps/api

RUN uv sync --frozen --no-dev --package claude-export-md-api

FROM python:3.12-slim-bookworm
WORKDIR /app
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:${PATH}"

# CEM_ALLOW_LOCAL_PATHS queda en false (default de la app): en Docker Compose
# el modo local no tiene sentido, el usuario siempre sube su export (spec 06 CA-9).

# Observacion 5 de la revision de M3: correr como root en el contenedor es un
# privilegio innecesario (la app no necesita escribir fuera de su propio directorio
# de trabajo, CEM_WORK_DIR); un usuario sin privilegios reduce el impacto de
# cualquier RCE futura.
RUN useradd -m app && chown -R app /app
USER app

EXPOSE 8000
CMD ["uvicorn", "claude_export_md_api.main:app", "--host", "0.0.0.0", "--port", "8000"]

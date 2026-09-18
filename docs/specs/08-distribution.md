# 08 — Distribución

## Objetivo
Que otra persona use la herramienta sin conocer el repo.

## Canales
| Canal | Público | Comando |
|---|---|---|
| PyPI / uvx | técnico | `uvx claude-export-md convert ./export ./salida` |
| Docker Compose | semi-técnico | `docker compose up` → http://localhost:4200 |
| Ejecutable único (PyInstaller) | no técnico | doble clic → abre el navegador con la UI |

## Criterios de aceptación
- **CA-1** CI verde en `ubuntu-latest` y `windows-latest`: ruff, mypy, pytest (core ≥ 85 % cobertura), pnpm lint/test/build.
- **CA-2** `docker compose up --build` desde repo limpio levanta API y web en < 3 min; la imagen de la API corre como usuario no root.
- **CA-3** Publicación en PyPI por tag `v*` con trusted publishing (sin tokens en secretos).
- **CA-4** `CHANGELOG.md` actualizado en cada tag; versión única en `packages/core/pyproject.toml`.
- **CA-5** README con quick start de < 5 minutos por canal y sección "Privacidad" explícita.
- **CA-6** El ejecutable se genera en CI para Windows y macOS y se adjunta al release de GitHub.

# 06 — API (FastAPI)

## Objetivo
Exponer inventario, conversión asíncrona y navegación del resultado para el front, sin duplicar lógica de core.

## Endpoints (`/api/v1`)
| Método | Ruta | Respuesta |
|---|---|---|
| POST | `/exports` (multipart zips/manifiesto **o** `{"path"}` en modo local) | `201 {export_id}` |
| GET | `/exports/{id}/inventory` | `Inventory` |
| POST | `/exports/{id}/convert` `{only?, templates?}` | `202 {job_id}` |
| GET | `/jobs/{id}` | `{status, progress, counts, errors}` |
| GET | `/jobs/{id}/events` | SSE: `progress`, `done`, `error` |
| GET | `/exports/{id}/output/tree` | árbol de archivos |
| GET | `/exports/{id}/output/file?path=` | contenido `.md` |
| GET | `/exports/{id}/download` | zip streaming |
| DELETE | `/exports/{id}` | `204` (borra el directorio de trabajo) |

## Criterios de aceptación
- **CA-1** Subir un zip de fixture → 201; `inventory` devuelve las categorías del fixture.
- **CA-2** `convert` responde en < 200 ms con 202 y el job avanza en segundo plano.
- **CA-3** SSE emite al menos un evento `progress` por categoría y un `done` final con los conteos.
- **CA-4** `path=../../etc/passwd` en `/output/file` → 400 problem+json.
- **CA-5** Subida mayor a `CEM_MAX_UPLOAD_MB` → 413 problem+json.
- **CA-6** Job que supera `CEM_JOB_TIMEOUT_S` → estado `failed` con motivo `timeout`.
- **CA-7** `openapi.json` es válido y `just gen-client` genera el cliente sin errores.
- **CA-8** Ningún endpoint realiza llamadas de red salientes (test con socket bloqueado).
- **CA-9** Modo local `{"path"}` solo se acepta si `CEM_ALLOW_LOCAL_PATHS=true` (por defecto en `docker compose` está apagado).

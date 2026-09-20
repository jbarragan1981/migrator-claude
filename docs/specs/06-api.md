# 06 — API (FastAPI)

## Objetivo
Exponer inventario, conversión asíncrona y navegación del resultado para el front, sin duplicar lógica de core.

## Endpoints (`/api/v1`)
| Método | Ruta | Respuesta |
|---|---|---|
| POST | `/exports` (multipart zips/manifiesto **o** `{"path"}` en modo local) | `201 {export_id}` |
| GET | `/exports/{id}/inventory` | `Inventory` |
| POST | `/exports/{id}/convert` `{only?, templates?}` | `202 {job_id}` (o `409` si ya hay una conversión pendiente/en curso para ese export) |
| GET | `/jobs/{id}` | `{status, progress, counts, errors, warnings, reason}` |
| GET | `/jobs/{id}/events` | SSE: `progress`, `done`, `error` |
| GET | `/exports/{id}/output/tree` | árbol de archivos (`404` si el export todavía no se convirtió) |
| GET | `/exports/{id}/output/file?path=` | contenido `.md` (`404` si no se convirtió; `400` si `path` es inválido) |
| GET | `/exports/{id}/download` | zip completo (armado a un temporal, ver abajo; `404` si no se convirtió) |
| DELETE | `/exports/{id}` | `204` (borra el directorio de trabajo, ver matiz local/subida abajo; `409` si hay una conversión en curso) |

## Criterios de aceptación
- **CA-1** Subir un zip de fixture → 201; `inventory` devuelve las categorías del fixture.
- **CA-2** `convert` responde en < 200 ms con 202 y el job avanza en segundo plano.
- **CA-3** SSE emite al menos un evento `progress` por categoría y un `done` final con los conteos.
- **CA-4** `path=../../etc/passwd` en `/output/file` → 400 problem+json. Lo mismo para cualquier ruta absoluta, cualquier componente `.`/`..`, y para un byte de control (incluido NUL, `\x00`) en el string crudo — nunca un 500.
- **CA-5** Subida mayor a `CEM_MAX_UPLOAD_MB` → 413 problem+json.
- **CA-6** Job que supera `CEM_JOB_TIMEOUT_S` → estado `failed` con motivo `timeout`.
- **CA-7** `openapi.json` es válido y `just gen-client` genera el cliente sin errores.
- **CA-8** Ningún endpoint realiza llamadas de red salientes (test con socket bloqueado).
- **CA-9** Modo local `{"path"}` solo se acepta si `CEM_ALLOW_LOCAL_PATHS=true` (por defecto en `docker compose` está apagado); si está apagado, `POST /exports` con `{"path"}` responde `403` problem+json.

## Detalles de contrato (completados en la revisión de M3)

- **`only` de `POST /convert` es hoy un no-op.** Se acepta el campo en el body (`ConvertRequest`) para no romper el contrato del spec, pero `usecases.convert.convert()` de `core` todavía no filtra categorías (mismo pendiente que `--only` del CLI, `docs/specs/05-cli.md`). El servidor deja un `logger.warning` cuando se manda un valor no vacío; el job convierte igual las 5 categorías. Se documentará como implementado recién cuando `core` soporte el filtro de verdad.
- **`GET /jobs/{id}` — campos reales de `JobStatusResponse`**: `status` (`pending|running|done|failed`), `progress` (lista de `{category, done}`, uno por evento emitido), `counts` (`dict[str, int]` por categoría, solo presente cuando `status == "done"`), `errors`/`warnings` (enteros, solo cuando `status == "done"`), `reason` (string, solo cuando `status == "failed"`; el valor `"timeout"` es el único que un cliente puede comparar por igualdad para CA-6, cualquier otro texto es el mensaje de una excepción real y puede cambiar). **Deliberadamente NO incluye `destination`** (la ruta absoluta del servidor donde se escribió `_output/`): es un detalle interno, no de incumbencia del cliente HTTP. El evento SSE `done` de `GET /jobs/{id}/events` expone el mismo subconjunto (`counts`, `errors`, `warnings`) — nunca `destination` tampoco, para no ser inconsistente con `GET /jobs/{id}`.
- **`POST /exports/{id}/convert` con una conversión ya en curso → `409` problem+json** con el `job_id` del job `pending`/`running` existente en el `detail`. Un export solo puede tener UNA conversión viva a la vez (evita que dos jobs escriban concurrentemente el mismo `_output/`); un nuevo `POST /convert` vuelve a aceptarse normalmente una vez que ese job llega a `done`/`failed`.
- **`404` de "export sin convertir todavía"** en los tres `GET /exports/{id}/output/*` y en `/download`: mismo código que un `export_id` inexistente, pero con un `detail` distinguible ("no tiene un árbol de salida todavía: corré `POST /convert`..."). Se eligió 404 (no 409) porque, desde el punto de vista del cliente, `_output/` es un recurso más bajo `exports/{id}` (como `/inventory`) y "todavía no existe" es justo lo que 404 comunica.
- **`403` de CA-9**: `POST /exports` con `{"path": ...}` cuando `CEM_ALLOW_LOCAL_PATHS` no es `"true"` → `403` problem+json (`"Modo local desactivado"`). Es el default en Docker Compose (spec 06 CA-9); el modo subida multipart nunca está gateado.
- **`413` de subida**: si el cliente manda `Content-Length` y supera `CEM_MAX_UPLOAD_MB`, se rechaza antes de leer el body; si no lo manda (o miente), igual se corta en streaming apenas la suma de bytes escritos supera el límite, sin juntar nunca el archivo completo en memoria. Limitación conocida y documentada en `STATUS.md`: esta versión de Starlette no aplica `max_part_size` a partes con `filename`, así que un cliente que miente sobre el tamaño ya le entrega el archivo completo al `SpooledTemporaryFile` de Starlette antes de que la app pueda intervenir; la mitigación real para ese caso es un límite de body en el reverse proxy (fuera del alcance de esta app).
- **`DELETE /exports/{id}` — matiz local vs. subida**: en modo subida (`{export_id}` registrado por multipart) se borra el directorio de trabajo COMPLETO (`shutil.rmtree`, es enteramente nuestro). En modo local (`{"path": ...}`) la carpeta es del USUARIO: `DELETE` borra SOLO `_output/` (lo único que `POST /convert` creó ahí), nunca el export original. `export_id` inexistente → `404` (no idempotente, por consistencia con el resto del contrato). **`DELETE` con una conversión `pending`/`running` para ese export → `409` problem+json** con el `job_id` en el `detail`, en vez de borrar mientras el job todavía escribe (evita que el borrado corra contra una escritura en curso).
- **Subida multipart: nombres de campo.** `POST /exports` lee TODAS las partes del `multipart/form-data` sin importar su nombre de campo (`multi_items()`, no `values()`) — subir varias partes con el mismo `name="file"` (el caso del ejemplo de `curl` del README) sube todos los archivos, no solo el último.
- **`GET /exports/{id}/download` YA NO es streaming incremental** (cuarta ronda de fixes de M3, ver `STATUS.md`). El diseño anterior armaba el zip chunk a chunk sobre un hilo productor + `queue.Queue` acotada; tres rondas de revisión encontraron bugs de fondo en ese mecanismo (el último: un abort duro del cliente podía dejar el hilo productor bloqueado para siempre en `queue.put()`, agotando el pool de `asyncio.to_thread` compartido con las conversiones) y throughput real de solo ~42 KB/s. El diseño actual arma el zip **completo** en un archivo temporal dentro de un único `asyncio.to_thread` (`services/output.py::build_zip_archive`) y lo sirve con `TempZipResponse` (subclase de `FileResponse` en `services/output.py`) — el temporal se borra en un `finally` propio de `TempZipResponse.__call__`, no con `background=` de `FileResponse`: quinta ronda de revisión, `FileResponse.__call__` NO corre `background` cuando un header `Range` es inválido (400) o no satisfacible (416), así que un `BackgroundTask` dejaba el temporal huérfano en esos dos casos. El `finally` cubre el camino normal y esos dos casos de `Range`. Se pierde el streaming incremental (memoria/tiempo constante mientras se arma el zip); a cambio desaparece toda la máquina de hilo+cola+cancelación.

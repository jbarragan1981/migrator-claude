# frames

Version de formato: batched-manifest (2026)
Archivos: 17 archivos con patron `frames-000/artifacts/<uuid>/*.json` (un archivo por artefacto, agrupado en una carpeta por uuid)
Tamano observado: 10.941 bytes totales (~10,7 KB) para los 17 archivos en el export real del usuario
Items: 17 (file_count=17; approx_item_count=null porque cada item es un archivo entero)
Partes: 1 (parts=[0])

Fuente: docs/export-format/inventory.json (categoria frames) + fixtures anonimizados packages/core/tests/fixtures/v2026-batched/frames/sample-01.json, sample-02.json, sample-03.json.

## CORRECCION respecto a CLAUDE.md

CLAUDE.md (seccion 6) marcaba frames como "desconocido, investigar primero". Ya no es desconocido en su ESTRUCTURA: son artefactos (probablemente codigo/documentos generados durante conversaciones, dado el nombre de carpeta `artifacts`). Lo que sigue sin confirmarse es DONDE vive el contenido real de cada version del artefacto (ver "Dudas").

## Estructura

- raiz: objeto (un artefacto por archivo, ubicado en `frames-000/artifacts/<uuid-del-artefacto>/*.json`).
- claves de primer nivel (top_keys, presentes en los 3 ejemplos de la muestra):
  - id: string (obligatorio, 36 chars - uuid del artefacto, coincide con el nombre de la carpeta que lo contiene)
  - kind: string (obligatorio, 8 chars en los 3 ejemplos - mismo largo, sugiere un valor fijo o un set pequeno de valores; no se pudo determinar el valor real)
  - visibility: string (obligatorio, 7 chars en los 3 ejemplos - igual, sugiere valor fijo, ej. "private"=7 chars encajaria pero no esta confirmado)
  - owner_account: string (obligatorio, 36 chars - uuid de la cuenta duena)
  - updated_at: string ISO-8601 (obligatorio, 25 chars)
  - active_version: string (obligatorio, 15 chars - identificador de version, distinto formato de uuid; correlaciona con versions[].id)
  - versions[]: array (obligatorio, 1 a 3 items observados en la muestra)

- item dentro de versions[]:
  - id: string (obligatorio, 15 chars - mismo formato que active_version)
  - title: string (obligatorio, 28-37 chars en la muestra)
  - description: string (obligatorio, 126-181 chars en la muestra)
  - created_at: string ISO-8601 (obligatorio, 25 chars)
  - NO hay campo de contenido (content/body/code/text) dentro de version - solo metadata (titulo, descripcion, fecha).

## Variantes observadas

- versions[] tiene 1 item en sample-01 y sample-03, y 3 items en sample-02 (con title/description del mismo largo repetidos en las 3 versiones de sample-02 - podria ser el mismo artefacto editado varias veces, o 3 versiones con metadata similar).
- No se observo variacion en las claves de primer nivel entre los 3 ejemplos: siempre las mismas 7 claves (id, kind, visibility, versions, owner_account, updated_at, active_version), todas presentes.

## Ejemplo anonimizado (artefacto con 3 versiones, sample-02)

```json
{
  "active_version": "<str:15>",
  "id": "<str:36>",
  "kind": "<str:8>",
  "owner_account": "<str:36>",
  "updated_at": "<str:25>",
  "versions": [
    {
      "created_at": "<str:25>",
      "description": "<str:181>",
      "id": "<str:15>",
      "title": "<str:28>"
    },
    {
      "created_at": "<str:25>",
      "description": "<str:181>",
      "id": "<str:15>",
      "title": "<str:28>"
    },
    {
      "created_at": "<str:25>",
      "description": "<str:181>",
      "id": "<str:15>",
      "title": "<str:28>"
    }
  ],
  "visibility": "<str:7>"
}
```

## Dudas / no determinable

- No determinable con la informacion disponible donde vive el CONTENIDO real del artefacto (el codigo, el documento, la imagen que el usuario vio en Claude.ai). Los 3 archivos de la muestra solo traen metadata (titulo, descripcion, fechas, ids de version) y ningun campo de tipo content/body/code/text/url. Hipotesis a verificar por el core-developer: (a) el contenido esta en otro archivo referenciado por versions[].id o por el uuid de la carpeta que no aparecio en la muestra de 3 (frames-000/artifacts/<uuid>/ podria tener mas de un .json por carpeta - no se confirmo cuantos archivos hay POR carpeta, el inventario solo reporta 17 archivos en total para el patron completo), (b) el contenido vive embebido en conversations.json (dentro de algun bloque tool_use/tool_result de tipo artefacto), (c) el contenido no se incluye en este export y solo se referencia por id.
- No determinable el valor real de kind ni visibility (siempre el mismo largo de string en la muestra de 3, consistente con valores fijos como "document"/"code" y "private"/"public", pero no verificado).
- No determinable si active_version siempre coincide con uno de los id de versions[] (no se pudo comparar valores reales, solo longitudes, y ambos campos miden 15 chars en todos los ejemplos, lo cual es compatible pero no concluyente).
- Pendiente: el fixture actual (3 archivos) no incluye un caso "minimo" (versions con 0 items, si es que existe) ni un caso con visibility/kind de un largo distinto - anotado para quien amplie los fixtures en M1/M2, no inventado aqui.

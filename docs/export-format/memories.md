# memories

Version de formato: batched-manifest (2026)
Archivos: 1 archivo con patron `memories-000/memories/<uuid>.json` (uuid de cuenta, no de item)
Tamano observado: 110.955 bytes (~108,4 KB) en el export real del usuario
Items: no aplica un conteo de "items" en el sentido de array; es UN objeto por cuenta. Dentro: memory_files[] tiene 3 entradas y project_memories tiene 16 claves en el fixture.
Partes: 1 (parts=[0])

Fuente: docs/export-format/inventory.json (categoria memories) + fixture anonimizado packages/core/tests/fixtures/v2026-batched/memories/memories.json.

## CORRECCION IMPORTANTE respecto a CLAUDE.md / spec 03

CLAUDE.md (Seccion 2, Seccion 5, Seccion 6) y spec 03 (03-parsers.md) asumen que `memories` es una CARPETA de archivos .md sueltos (`/profile.md`, `/people/*.md`, `/areas/*.md`...). Esto NO es lo que muestra el export real de este usuario: es un UNICO archivo JSON por cuenta, `memories-000/memories/<account_uuid>.json`, con root_type=object. No hay archivos .md reales dentro de memories-000 en este export.

## Estructura

- raiz: objeto (NO array, NO carpeta de .md).
- claves de primer nivel (top_keys en el inventario, las 4 estan presentes en el unico item observado):
  - account_uuid: string (obligatorio, identificador de la cuenta duena de las memorias)
  - conversations_memory: string larga (obligatorio en la muestra; ~5666 caracteres anonimizados) - parece ser un resumen/memoria agregada de todas las conversaciones, en texto libre (no JSON anidado)
  - memory_files[]: array de objetos (obligatorio; 3 items en la muestra), cada uno:
    - content: string (el contenido de la "memoria", texto libre, tamanos observados 1522/924/819 chars)
    - path: string (36-41 chars anonimizados; el NOMBRE sugiere una ruta tipo "/profile.md" o "/people/x.md" pero el valor real esta anonimizado a `<str:N>` y no se puede confirmar el formato exacto)
    - updated_at: string ISO-8601 (32 chars anonimizados)
  - project_memories: objeto/diccionario (obligatorio) cuyas CLAVES son uuids de proyecto (formato `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`, visibles como tal porque el anonimizador reemplaza uuids reales por uuids falsos deterministas, no por `<str:N>`) y cuyos VALORES son strings largos (2358 a 7102 caracteres en la muestra) - memoria especifica por proyecto, en texto libre.

## Variantes observadas

- El numero de claves en project_memories (16 en la muestra) es igual o menor al numero de proyectos reales de la cuenta (32 proyectos segun inventory.json) - sugiere que solo los proyectos con actividad relevante generan una entrada en project_memories; no se puede confirmar la regla exacta con la informacion disponible.
- memory_files[].path tiene longitudes distintas entre si (39, 39, 35 caracteres) - consistente con rutas de distinto nivel de profundidad (ej. "/profile.md" mas corto que "/people/alguien.md") pero no confirmado porque el contenido esta anonimizado.

## Ejemplo anonimizado (unico item de la cuenta)

```json
{
  "account_uuid": "<str:36>",
  "conversations_memory": "<str:5666>",
  "memory_files": [
    {
      "content": "<str:1522>",
      "path": "<str:39>",
      "updated_at": "<str:32>"
    },
    {
      "content": "<str:924>",
      "path": "<str:39>",
      "updated_at": "<str:32>"
    },
    {
      "content": "<str:819>",
      "path": "<str:35>",
      "updated_at": "<str:32>"
    }
  ],
  "project_memories": {
    "171cfb43-a1e8-c21f-c51f-77c2135e1b6a": "<str:4533>",
    "1f82b2f4-b6e4-c03c-e7cb-55e6a68d47ba": "<str:6085>",
    "361ab264-751c-6c5f-fef1-dd6077dad712": "<str:3647>"
  }
}
```

(project_memories esta recortado a 3 claves de las 16 reales del fixture por brevedad; los uuids mostrados son FALSOS, generados deterministicamente por el anonimizador, nunca uuids reales de la cuenta.)

## Dudas / no determinable

- No determinable con la informacion disponible si memory_files[].path codifica efectivamente rutas tipo "/profile.md" o "/people/nombre.md" (el valor esta anonimizado a `<str:N>`, solo se conoce la longitud). El parser de M1 deberia leer el valor real de path en un export sin anonimizar antes de decidir el nombre del archivo Markdown de salida.
- No determinable si conversations_memory y los valores de project_memories son texto plano Markdown, texto plano sin formato, o algun otro formato estructurado serializado como string.
- No determinable la regla que decide que proyectos aparecen en project_memories (16 de 32 proyectos en esta cuenta).
- No hay memory_files vacio en la muestra (siempre 3 items) - no se pudo observar el caso de una cuenta sin memorias.

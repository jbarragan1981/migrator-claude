# projects

Version de formato: batched-manifest (2026)
Archivos: 32 archivos con patron `projects-000/projects/<uuid>.json` (un archivo por proyecto, no un array unico)
Tamano observado: 22.960 bytes totales (~22,4 KB) para los 32 archivos en el export real del usuario
Items: 32 proyectos (file_count=32; approx_item_count=null porque cada item es un archivo entero, no hay array que contar)
Partes: 1 (parts=[0])

Fuente: docs/export-format/inventory.json (categoria projects) + fixtures anonimizados packages/core/tests/fixtures/v2026-batched/projects/sample-01.json, sample-02.json, sample-03.json.

## CORRECCION respecto al spec 01 original

El spec 01 (via CLAUDE.md) asumia un unico projects.json con un array. El export real trae un archivo JSON POR PROYECTO (root_type=object), no un array. El parser debe iterar los 32 archivos, no items dentro de un array.

## Estructura

- raiz: objeto (un proyecto por archivo).
- claves de primer nivel (top_keys, presentes en los 3 ejemplos de la muestra):
  - uuid: string (obligatorio, identificador)
  - name: string (obligatorio; longitudes observadas 33, 3, 7 chars - puede ser muy corto)
  - description: string (obligatorio como clave pero puede ser "" - observado vacio en sample-03)
  - is_private: boolean (obligatorio; true en los 3 ejemplos)
  - is_starter_project: boolean (obligatorio; false en los 3 ejemplos)
  - prompt_template: string (obligatorio como clave, pero vacio "" en los 3 ejemplos - podria ser el "system prompt" del proyecto que CLAUDE.md llama instructions, pero en esta cuenta esta siempre vacio)
  - created_at / updated_at: string ISO-8601 (obligatorios)
  - creator: objeto {uuid: string, full_name: string} (obligatorio, mismo full_name/uuid de 7/36 chars en los 3 ejemplos, consistente con ser siempre el dueno de la cuenta)
  - docs[]: array (obligatorio como clave, puede estar vacio [] - 2 de los 3 ejemplos lo traen vacio; el tercero trae 1 item)

- item dentro de docs[] (solo visto en sample-01):
  - uuid: string (obligatorio)
  - filename: string (obligatorio, 50 chars en el unico ejemplo)
  - created_at: string ISO-8601 (obligatorio)
  - NO hay campo de contenido (content/text/body) en docs[] - la metadata del doc no incluye su texto.

## Variantes observadas

- docs[] vacio en 2 de 3 proyectos de la muestra, con 1 item en el tercero. No se pudo observar un proyecto con mas de 1 doc.
- description y prompt_template pueden ser cadena vacia ("") - son claves siempre presentes pero el valor puede estar "vacio" en el sentido de negocio.
- creator parece ser siempre el mismo (mismo largo de full_name=7 y uuid=36 en los 3 ejemplos) - consistente con que todos los proyectos de esta cuenta fueron creados por el dueno de la cuenta, sin colaboradores visibles en la muestra.

## Ejemplo anonimizado (proyecto con 1 doc, sample-01)

```json
{
  "created_at": "<str:32>",
  "creator": {
    "full_name": "<str:7>",
    "uuid": "<str:36>"
  },
  "description": "<str:105>",
  "docs": [
    {
      "created_at": "<str:32>",
      "filename": "<str:50>",
      "uuid": "<str:36>"
    }
  ],
  "is_private": true,
  "is_starter_project": false,
  "name": "<str:33>",
  "prompt_template": "<str:0>",
  "updated_at": "<str:32>",
  "uuid": "<str:36>"
}
```

## Dudas / no determinable

- No determinable con la informacion disponible donde vive el CONTENIDO de cada doc de docs[] (filename+uuid son solo metadata). Hipotesis a verificar por el core-developer contra el export real sin anonimizar: (a) un archivo separado referenciado por docs[].uuid dentro de projects-000 que no aparecio en la muestra de 3 proyectos porque solo 1 de ellos tiene docs, (b) contenido inline en un campo que no salio en la muestra de top_keys, (c) el contenido esta en otra categoria del export (p.ej. dentro de conversations o memories) y projects solo referencia metadata.
- No determinable si prompt_template alguna vez tiene contenido no vacio en esta cuenta (los 3 ejemplos lo traen "") - CLAUDE.md lo llama "instructions"/"system prompt" del proyecto; el nombre real de la clave es prompt_template.
- No se observo el campo project_uuid de conversations.json enlazando a NINGUNO de estos 3 proyectos (los 3 ejemplos del fixture de conversations tienen project_uuid=null) - la relacion Conversation.project_uuid -> Project.uuid no se pudo verificar end-to-end con los fixtures disponibles, aunque ambos lados usan el mismo formato de uuid.
- No determinable si existen campos de colaboradores/miembros del proyecto ademas de creator (no aparecieron en la muestra de 3).

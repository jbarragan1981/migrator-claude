# conversations

Version de formato: batched-manifest (2026)
Archivos: `conversations-000/conversations.json` (1 archivo, `part 0`)
Tamano observado: 103.037.885 bytes (~98,3 MB) en el export real del usuario
Items: ~291 conversaciones (aproximado, item_count_exact=false; ijson no cuenta exacto sin recorrer todo el archivo)
Partes: 1 (parts=[0])

Fuente: docs/export-format/inventory.json (categoria conversations) + fixture anonimizado packages/core/tests/fixtures/v2026-batched/conversations/conversations.json (3 conversaciones completas).

## Estructura

- raiz: array de conversaciones (NO objeto envolvente, NO paginado dentro del archivo).
- item (conversacion):
  - uuid: string (obligatorio, identificador)
  - name: string (obligatorio, puede ser "" si el usuario no le puso titulo)
  - summary: string (observado siempre presente pero vacio "" en los 3 items del fixture, no se puede confirmar si alguna vez trae contenido real)
  - created_at / updated_at: string ISO-8601 (obligatorios)
  - project_uuid: string o null (opcional, null en los 3 items del fixture; enlaza a Project cuando no es null)
  - account.uuid: objeto anidado con un unico campo uuid (obligatorio)
  - chat_messages[]: array de mensajes (obligatorio, puede tener 2 o mas items)

- item (mensaje dentro de chat_messages[]):
  - uuid: string (obligatorio)
  - sender: string, valores observados "human" (5 chars) y "assistant" (9 chars) (obligatorio)
  - parent_message_uuid: string (obligatorio en los 3 items; sugiere estructura de arbol/hilo, no solo lista lineal)
  - text: string (obligatorio, concatenacion/resumen plano del mensaje; puede ser larga, hasta 36923 caracteres observado)
  - created_at / updated_at: string ISO-8601 (obligatorios)
  - content[]: array de bloques tipados (obligatorio), ver "Variantes observadas"

## Variantes observadas en content[].type

Se observaron 4 formas distintas de bloque dentro de content[] (usando la longitud de las cadenas anonimizadas para inferir el valor real, consistente con sender humano/asistente y con el vocabulario ya usado en CLAUDE.md/specs):

1. Bloque de texto (type de 4 caracteres, consistente con "text") - aparece en mensajes human y tambien dentro de mensajes assistant:
   - text: string
   - citations: array (vacio en los 3 ejemplos)
   - flags: null
   - start_timestamp / stop_timestamp: string

2. Bloque de razonamiento (type de 8 caracteres, consistente con "thinking") - solo visto en mensajes assistant:
   - thinking: string (texto largo, hasta 4025 chars observado)
   - summaries[]: array de {summary: string} (0 a 3 items observados)
   - signature: null (siempre null en la muestra)
   - alternative_display_type, cut_off, hidden, thinking_hidden, truncated: booleanos/null
   - start_timestamp / stop_timestamp: string

3. Bloque de invocacion de herramienta (type tambien de 8 caracteres, mismo largo que "thinking" pero campos distintos, consistente con "tool_use"):
   - id: string
   - name: string (nombre de la tool, una de 4 chars y otra de 9 chars en la muestra; no determinable cual exactamente sin el valor real)
   - input: objeto de forma VARIABLE, visto {description, path} y tambien {command, description} (confirma que input es esquema libre, dependiente de la tool)
   - icon_name: string
   - display_content: objeto {text, type} o {json_block, type} (forma variable)
   - message: string
   - integration_name, integration_icon_url, mcp_server_url, tool_identifier, context, approval_key, approval_key_legacy, approval_options, is_mcp_app, hidden_in_chat: presentes pero null en los 3 ejemplos (campos opcionales que sugieren integraciones/MCP no usadas en esta muestra)
   - start_timestamp / stop_timestamp: string

4. Bloque de resultado de herramienta (type de 11 caracteres, consistente con "tool_result"):
   - tool_use_id: string (correlaciona con el id del bloque tool_use)
   - content[]: array anidado de {text, type, uuid} (el resultado puede tener su propio sub-array de bloques)
   - is_error: boolean
   - structured_content: null en los 3 ejemplos (opcional, sugiere que a veces trae contenido estructurado ademas de texto)
   - display_content: null o {json_block, type} (forma variable, igual que en tool_use)
   - meta.output_format_category: string corta (2 o 4 chars), categorizacion del formato de salida
   - icon_name, integration_name, integration_icon_url, mcp_server_url, message, hidden_in_chat, name: presentes, mezcla de string/null

No se observaron bloques "image" ni "artifact" explicitos en la muestra de 3 conversaciones. El spec 02 los prevee (ContentBlock.type: "image"|"artifact") pero NO estan confirmados con este export.

## Ejemplo anonimizado (1 conversacion, recortada a 1 intercambio human -> assistant)

```json
{
  "account": {
    "uuid": "<str:36>"
  },
  "chat_messages": [
    {
      "content": [
        {
          "citations": [],
          "flags": null,
          "start_timestamp": "<str:27>",
          "stop_timestamp": "<str:27>",
          "text": "<str:381>",
          "type": "<str:4>"
        }
      ],
      "created_at": "<str:27>",
      "parent_message_uuid": "<str:36>",
      "sender": "<str:5>",
      "text": "<str:381>",
      "updated_at": "<str:27>",
      "uuid": "<str:36>"
    },
    {
      "content": [
        {
          "alternative_display_type": null,
          "cut_off": false,
          "flags": null,
          "hidden": false,
          "signature": null,
          "start_timestamp": "<str:27>",
          "stop_timestamp": "<str:27>",
          "summaries": [
            { "summary": "<str:63>" },
            { "summary": "<str:66>" }
          ],
          "thinking": "<str:147>",
          "thinking_hidden": false,
          "truncated": false,
          "type": "<str:8>"
        },
        {
          "approval_key": null,
          "approval_key_legacy": null,
          "approval_options": null,
          "context": null,
          "display_content": { "text": "<str:52>", "type": "<str:4>" },
          "flags": null,
          "hidden_in_chat": null,
          "icon_name": "<str:4>",
          "id": "<str:30>",
          "input": { "description": "<str:52>", "path": "<str:41>" },
          "integration_icon_url": null,
          "integration_name": null,
          "is_mcp_app": null,
          "mcp_server_url": null,
          "message": "<str:52>",
          "name": "<str:4>",
          "start_timestamp": "<str:27>",
          "stop_timestamp": "<str:27>",
          "tool_identifier": null,
          "type": "<str:8>"
        },
        {
          "content": [
            { "text": "<str:13388>", "type": "<str:4>", "uuid": "<str:36>" }
          ],
          "display_content": null,
          "flags": null,
          "hidden_in_chat": null,
          "icon_name": "<str:4>",
          "integration_icon_url": null,
          "integration_name": null,
          "is_error": false,
          "mcp_server_url": null,
          "message": null,
          "meta": { "output_format_category": "<str:2>" },
          "name": "<str:4>",
          "start_timestamp": null,
          "stop_timestamp": null,
          "structured_content": null,
          "tool_use_id": "<str:30>",
          "type": "<str:11>"
        }
      ],
      "created_at": "<str:27>",
      "parent_message_uuid": "<str:36>",
      "sender": "<str:9>",
      "text": "<str:1762>",
      "updated_at": "<str:27>",
      "uuid": "<str:36>"
    }
  ],
  "created_at": "<str:27>",
  "name": "<str:47>",
  "project_uuid": null,
  "summary": "<str:0>",
  "updated_at": "<str:27>",
  "uuid": "<str:36>"
}
```

(Todas las cadenas estan reemplazadas por `<str:N>`, modo "estructura" del anonimizador; el item completo, con las 3 conversaciones, esta en el fixture.)

## Dudas / no determinable

- No se puede confirmar el valor literal de type ("text", "thinking", "tool_use", "tool_result") porque el fixture esta anonimizado a longitud de cadena; se infiere por longitud y por el vocabulario ya usado en CLAUDE.md/spec 02, pero NO esta verificado caracter a caracter.
- No se observaron bloques "image" ni artefactos embebidos en texto (`<antArtifact ...>`) en la muestra de 3 conversaciones; el spec 02/03 los prevee como hipotesis, no confirmados.
- summary aparece siempre vacio ("") en la muestra; no determinable si alguna vez trae contenido real.
- No hay evidencia en la muestra de campos attachments[] o files[] que el spec 03 menciona como hipotesis para Message; no aparecen en top_keys de ningun mensaje observado. No determinable con la informacion disponible si existen en otras conversaciones del export real.
- part es siempre 0 en este export (291 conversaciones caben en un solo archivo de ~98 MB); no se pudo observar como el formato dividiria en partes multiples (part > 0) porque este export no lo requirio.

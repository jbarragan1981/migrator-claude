# 03 - Parsers por categoria

Este spec se completo con lo que descubrio la Fase 0 (docs/export-format/). Las secciones marcadas [OK] estan confirmadas contra el export real; las marcadas [?] siguen siendo hipotesis a verificar por el core-developer contra un export sin anonimizar.

## Objetivo
Un parser por categoria que convierta los archivos de origen en entidades de dominio, en streaming, tolerando esquema.

## Interfaz comun
def parse(source: ExportSource, category: str, report: Report) -> Iterator[Entity]

Registrado en usecases/convert.py por nombre de categoria y version de formato.

## Criterios comunes a todos
- CA-C1 Multi-parte: dadas part 0..n, se concatenan en orden y no se duplican items por id. OK en el export real observado, las 5 categorias solo tienen part=0, no se pudo verificar el caso multi-parte con datos reales, sigue siendo un criterio a probar con fixtures sinteticos.
- CA-C2 Item corrupto produce report.errors += ParseError(...); el iterador continua.
- CA-C3 Sin json.load de archivos mayores a 10 MB. Confirmado necesario: conversations.json del export real pesa unos 98 MB.
- CA-C4 Campos desconocidos preservados en extra.
- CA-C5 Orden de salida deterministico (por created_at, luego id).

## conversations [OK]
- Origen confirmado: conversations-000/conversations.json, archivo UNICO (no hay parte mayor a 0 en este export), root_type=array, unos 291 items, unos 98 MB.
- Cada item: uuid, name, summary, created_at, updated_at, project_uuid (nullable), account.uuid, chat_messages[].
- Cada mensaje: uuid, sender ("human" o "assistant"), parent_message_uuid, text, created_at, updated_at, content[]. NO se confirmaron attachments[] ni files[] en la muestra (spec 02 los preveia como hipotesis).
- content[] trae al menos 4 formas de bloque distintas (ver docs/export-format/conversations.md): texto plano, "thinking" (razonamiento, con summaries[] y thinking_hidden), invocacion de herramienta tipo tool_use (con input de forma libre segun la tool, y muchos campos de integracion/MCP casi siempre null), y resultado de herramienta tipo tool_result (con content[] anidado, structured_content, display_content de forma variable).
- CA-1 Mensaje con content[] de tipos mixtos produce blocks en el mismo orden, preservando los 4 tipos observados (texto, thinking, tool_use, tool_result) como ContentBlock distintos.
- CA-2 Conversacion con project_uuid no-null enlaza a Project por uuid. No verificado end-to-end porque los 3 items del fixture tienen project_uuid=null.
- CA-3 display_content e input dentro de un bloque tool_use o tool_result son objetos de esquema libre (se observaron combinaciones de text/type, json_block/type, description/path, command/description). El parser no debe asumir claves fijas ahi, debe preservarlas completas en extra o payload.
- CA-4 name y summary pueden ser cadena vacia. No se debe tratar cadena vacia como campo ausente ni descartarlo.
- CA-5 Artefactos embebidos en el texto no se observaron en la muestra de 3 conversaciones. El parser puede implementar esa extraccion como fallback opcional pero no puede asumir que es el mecanismo principal de artefactos, dado que existe una categoria dedicada frames que parece cumplir ese rol.

## memories [OK] - corrige hipotesis de CLAUDE.md y spec 01
- Origen confirmado: un unico archivo JSON por cuenta (memories-000/memories/<account_uuid>.json), root_type=object. NO es una carpeta de archivos .md como asumia CLAUDE.md secciones 2, 5 y 6 - esa hipotesis queda descartada para el formato batched-manifest 2026.
- Forma: account_uuid, conversations_memory (string), memory_files (array de content/path/updated_at), project_memories (objeto con clave uuid de proyecto y valor string).
- CA-1 El parser lee un solo archivo por cuenta, no recorre una carpeta buscando .md.
- CA-2 Cada entrada de memory_files[] genera una Memory con path tomado del campo path real (el parser debe leer el valor real en un export sin anonimizar para confirmar si codifica rutas de estilo jerarquico - no confirmado con el fixture anonimizado) y content tomado del campo content.
- CA-3 conversations_memory (string a nivel de cuenta, sin path propio) se exporta como una Memory adicional con un path sintetico fijo definido por el parser, documentando en extra que no vino con path original.
- CA-4 Cada clave de project_memories (uuid de proyecto) genera una Memory ligada a ese Project por uuid, con un path sintetico ya que tampoco trae path propio.
- CA-5 No determinable si existen cuentas sin memory_files o sin project_memories (la unica muestra disponible siempre trae ambos no vacios). El parser debe tolerar arrays u objetos vacios de todas formas.

## projects [OK] - corrige hipotesis de spec 01
- Origen confirmado: un archivo JSON por proyecto (projects-000/projects/<uuid>.json), root_type=object, NO un unico projects.json con array.
- Cada archivo: uuid, name, description, is_private, is_starter_project, prompt_template, created_at, updated_at, creator (uuid y full_name), docs (array de uuid, filename, created_at).
- CA-1 El parser itera N archivos (uno por proyecto), no items dentro de un array.
- CA-2 prompt_template mapea a Project.instructions (puede ser cadena vacia, no tratar como ausente).
- CA-3 docs[] solo trae metadata (uuid, filename, created_at); el contenido del doc no esta en este archivo. El parser debe resolver el contenido desde donde realmente viva; hasta confirmarlo, debe generar el ProjectDoc marcando el contenido como no disponible en este export en vez de inventarlo o dejarlo vacio sin avisar, y registrar un warning en report.warnings por cada doc sin contenido resuelto.
- CA-4 Las conversaciones del proyecto se enlazan por project_uuid desde conversations. No verificado end-to-end con los fixtures disponibles (ningun item de la muestra de conversations tiene project_uuid no-null).
- CA-5 creator es un objeto con uuid y full_name, no un id plano. El parser debe extraer creator.uuid como referencia, no asumir que creator es directamente un string.

## light_metadata [OK]
- Origen confirmado: light_metadata-000/*.json, root_type=array con exactamente 1 item (perfil de cuenta) en este export.
- Item: email_address, full_name, uuid, verified_phone_number (nullable).
- CA-1 Mapea a Account: id=uuid, email=email_address, display_name=full_name.
- CA-2 verified_phone_number puede ser null; no se excluye por parecer sensible (no es un secreto/token, es un dato de perfil), pero se sigue aplicando la regla general de excluir campos que parezcan credenciales si aparecieran en extra.
- CA-3 No confirmado si el array puede traer mas de 1 item (cuentas de equipo u organizacion). El parser no debe asumir longitud 1 de forma rigida, debe iterar el array igual.

## frames [OK] - ya no es "desconocido"
- Origen confirmado: frames-000/artifacts/<uuid>/*.json, un archivo por artefacto, root_type=object, 17 archivos en este export.
- Cada archivo: id, kind, visibility, owner_account, updated_at, active_version, versions (array de id, title, description, created_at).
- CA-1 El parser lee cada archivo de frames-000/artifacts/ como un Frame con id, kind, visibility, owner_account, updated_at, active_version y versions[] preservados.
- CA-2 Ninguno de los campos observados trae el contenido real del artefacto (codigo o documento). Hasta confirmar donde vive, el payload del Frame debe preservar el JSON completo tal cual y el render Markdown debe indicar explicitamente que el contenido no esta disponible en este export, en vez de mostrar un bloque vacio silencioso.
- CA-3 versions[] puede tener uno o mas items (1 a 3 observados). active_version referencia, por longitud de string aunque no confirmado por valor, uno de los id de versions[]. El parser debe resolver cual version esta activa comparando active_version con versions[].id, tolerando que no coincida con ninguna (warning, no excepcion).

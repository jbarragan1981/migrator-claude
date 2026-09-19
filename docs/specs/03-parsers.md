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

## conversations [OK] [IMPLEMENTADO]
Implementado en adapters/parsers/conversations.py con la firma parse(source, report) -> Iterator[Conversation] (misma convencion que memories: sin el argumento category). Render en rendering/conversations.py + rendering/artifacts.py + templates/conversation.md.j2; escritura a traves del puerto MarkdownSink desde usecases/convert.py (ADR-0006), con FilesystemSink como unica implementacion hoy. Cobertura por tests en packages/core/tests/test_parse_conversations.py y test_render_conversations.py (100% de linea en los tres modulos nuevos):
- CA-1 test_ca1_mixed_block_types_keep_their_order, test_ca1_an_unknown_block_type_is_kept_as_is (el tipado y el orden los resuelve ContentBlock.from_raw del dominio, el parser no reimplementa nada)
- CA-2 test_ca2_project_uuid_links_the_conversation, test_ca2_null_project_uuid_leaves_no_link, test_ca2_blank_project_uuid_is_not_a_link. Ya NO queda sin verificar end-to-end: el fixture sintetico fixtures/synthetic/conversations-batched/ trae una conversacion con project_uuid no-null (el fixture anonimizado real sigue teniendo los 3 items con project_uuid=null). Falta el otro extremo del enlace, que es del parser de projects (M2).
- CA-3 test_ca3_tool_use_input_is_preserved_whole, test_ca3_tool_result_keeps_its_nested_content_and_meta, test_thinking_keeps_its_summaries. El parser no toca esos objetos: van enteros a ContentBlock.payload.
- CA-4 test_ca4_empty_name_and_summary_are_not_treated_as_absent, test_a_null_summary_stays_none. Solo null es ausencia; "" se conserva y se emite en el frontmatter.
- CA-5 Implementado como fallback opcional, tal y como permite este CA: se extraen las CERCAS DE CODIGO largas (>40 lineas) del texto del mensaje a artifacts/NN-<nombre>.<ext> con enlace relativo (spec 04 CA-5, umbral razonado alli). No se asume que ese sea el mecanismo principal de artefactos: frames sigue siendo la categoria dedicada y se resuelve en M2.
- CA-C1 test_cac1_parts_are_concatenated_without_duplicating (dedupe por Conversation.id)
- CA-C2 test_cac2_* (item que no es objeto, item sin uuid, chat_messages con forma rara, JSON truncado, raiz que no es array, archivo vacio, archivo que desaparece, mensaje que no es objeto, bloque que no es objeto)
- CA-C3 test_cac3_the_first_conversation_arrives_without_reading_the_whole_file: con un fixture de >3 MB, pedir la PRIMERA conversacion lee menos de 500 KB (json.load habria leido los 3 MB antes de devolver nada). No hay techo de tamano como en memories: aqui el streaming es la regla.
- CA-C4 test_cac4_unknown_fields_are_preserved (account acaba en extra). chat_messages y project_uuid NO se duplican en extra: ya estan en messages y project_id, y copiarlos seria meter el export entero en memoria.
- CA-C5 test_cac5_parse_sorted_orders_by_date_then_id, test_cac5_conversations_without_date_go_last_and_keep_their_relative_order, test_cac5_two_runs_produce_the_same_order. El orden canonico lo da parse_sorted(), que materializa la lista (~291 entidades); parse() emite en streaming en el orden del archivo, que ya es deterministico. Se separan a proposito: la ruta de salida de cada conversacion depende solo de si misma, asi que convert puede escribir en streaming y usar la lista ordenada solo donde el orden importa (el _index.md).

Decisiones adicionales del parser, que el export no trae resueltas:
- Mensaje sin uuid: NO se descarta (perder el texto de un turno por un identificador ausente seria peor). Recibe el id sintetico y deterministico <uuid de la conversacion>#<posicion>, se marca con extra["synthetic_id"]=True y se avisa en report.warnings. El identificador del ITEM (la conversacion) si es obligatorio: sin uuid, ParseError y no se emite.
- chat_messages ilegible: la conversacion se conserva igual (titulo, fechas y enlace a proyecto siguen siendo utiles) y el problema va a report.errors con item_id = uuid de la conversacion.
- Igual que memories, el parser anota en extra["source_file"] el archivo del export del que salio cada conversacion, porque el frontmatter obligatorio del spec 04 lo pide y el dominio no conoce el sistema de archivos.

- Origen confirmado: conversations-000/conversations.json, archivo UNICO (no hay parte mayor a 0 en este export), root_type=array, unos 291 items, unos 98 MB.
- Cada item: uuid, name, summary, created_at, updated_at, project_uuid (nullable), account.uuid, chat_messages[].
- Cada mensaje: uuid, sender ("human" o "assistant"), parent_message_uuid, text, created_at, updated_at, content[]. NO se confirmaron attachments[] ni files[] en la muestra (spec 02 los preveia como hipotesis).
- content[] trae al menos 4 formas de bloque distintas (ver docs/export-format/conversations.md): texto plano, "thinking" (razonamiento, con summaries[] y thinking_hidden), invocacion de herramienta tipo tool_use (con input de forma libre segun la tool, y muchos campos de integracion/MCP casi siempre null), y resultado de herramienta tipo tool_result (con content[] anidado, structured_content, display_content de forma variable).
- CA-1 Mensaje con content[] de tipos mixtos produce blocks en el mismo orden, preservando los 4 tipos observados (texto, thinking, tool_use, tool_result) como ContentBlock distintos.
- CA-2 Conversacion con project_uuid no-null enlaza a Project por uuid. No verificado end-to-end porque los 3 items del fixture tienen project_uuid=null.
- CA-3 display_content e input dentro de un bloque tool_use o tool_result son objetos de esquema libre (se observaron combinaciones de text/type, json_block/type, description/path, command/description). El parser no debe asumir claves fijas ahi, debe preservarlas completas en extra o payload.
- CA-4 name y summary pueden ser cadena vacia. No se debe tratar cadena vacia como campo ausente ni descartarlo.
- CA-5 Artefactos embebidos en el texto no se observaron en la muestra de 3 conversaciones. El parser puede implementar esa extraccion como fallback opcional pero no puede asumir que es el mecanismo principal de artefactos, dado que existe una categoria dedicada frames que parece cumplir ese rol.

## memories [OK] [IMPLEMENTADO] - corrige hipotesis de CLAUDE.md y spec 01
Implementado en adapters/parsers/memories.py con la firma parse(source, report) -> Iterator[Memory] (sin el argumento category: el modulo YA es la categoria; el registro por nombre se hara en usecases/convert.py). Cobertura por tests en packages/core/tests/test_parse_memories.py:
- CA-1 test_ca1_reads_the_single_json_of_the_account
- CA-2 test_ca2_memory_files_keep_their_real_path_and_content, test_memory_file_dates_are_normalised_to_utc, test_unreadable_date_does_not_invalidate_the_memory
- CA-3 test_ca3_conversations_memory_gets_the_synthetic_path (+ los casos de cadena vacia y tipo inesperado)
- CA-4 test_ca4_project_memories_link_to_their_project, test_project_memories_are_emitted_sorted_by_uuid
- CA-5 test_ca5_empty_collections_are_tolerated, test_ca5_missing_collections_are_tolerated
- CA-C1 test_cac1_parts_are_concatenated_without_duplicating (dedupe por Memory.path, que es el identificador segun ADR-0005)
- CA-C2 test_cac2_broken_json_is_reported_and_the_run_continues + los casos de raiz que no es objeto, entrada sin path y entrada que no es objeto
- CA-C3 no aplica el streaming aqui: el archivo es un OBJETO de ~110 KB (no un array de items) y hay uno por cuenta, asi que se lee entero con json.load. El parser comprueba el tamano antes (MAX_JSON_BYTES = 10 MB) y registra un ParseError en vez de cargarlo si algun export lo superara (test_oversized_file_is_reported_instead_of_loaded). La regla de ijson sigue siendo obligatoria para conversations.
- CA-C4 test_cac4_unknown_fields_are_preserved
- CA-C5 test_cac5_two_runs_produce_the_same_order, test_memory_files_come_before_the_synthetic_ones (orden: memory_files en el orden del array, luego conversations_memory, luego project_memories ordenadas por uuid)
Ademas: el parser anota en extra["source_file"] el archivo del export del que salio cada memoria, porque el frontmatter obligatorio del spec 04 lo pide y el dominio no conoce el sistema de archivos.

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

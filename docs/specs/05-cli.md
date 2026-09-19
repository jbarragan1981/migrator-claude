# 05 — CLI

## Objetivo
`claude-export-md` como punto de entrada para usuarios técnicos y para automatización.

## Comandos
```
claude-export-md inventory <ruta> [--out inventory.json] [--json]
claude-export-md convert   <ruta> <salida> [--templates DIR] [--only conversations,memories] [--overwrite] [--quiet]
claude-export-md validate  <salida>          # verifica frontmatter, enlaces relativos rotos, determinismo
claude-export-md serve     [--port 8000] [--open]   # levanta API + web estático (M5)
```

## Criterios de aceptación
- **CA-1** `convert` sobre un fixture produce el árbol del spec 04 y termina con código 0.
- **CA-2** Con errores de parseo termina con código 0 y muestra "N ítems con error → _report/errors.jsonl"; con `--strict` termina con código 3.
- **CA-3** Directorio de salida no vacío sin `--overwrite` → código 2 y mensaje claro, sin tocar nada.
- **CA-4** Barra de progreso (rich) por categoría; con `--quiet` o sin TTY, solo resumen final.
- **CA-5** `--json` imprime únicamente JSON en stdout (para scripts).
- **CA-6** Rutas con espacios y acentos en Windows funcionan (test en CI con matriz windows-latest).
- **CA-7** `uvx claude-export-md --help` funciona sin clonar el repo (M5).
- **CA-8** Todo error de la librería (`ClaudeExportMdError`: formato desconocido, zip corrupto usado como origen…) se muestra como un mensaje de una línea en stderr y termina con código 2; nunca como traceback.

## Estado de `convert` (M2)

Implementado: `claude-export-md convert <ruta> <salida> [--templates DIR] [--overwrite] [--quiet]`
(`apps/cli/src/claude_export_md_cli/commands/convert.py` sobre `usecases/convert.py`).
Cubre CA-1, CA-2 (sin `--strict`), CA-3, CA-4, CA-6 y CA-8; tests en
`apps/cli/tests/test_convert_cmd.py` y `packages/core/tests/test_convert.py`.
Desde el cierre de M2 convierte las CINCO categorías (`memories`, `light_metadata`,
`projects`, `conversations`, `frames`) y el árbol de salida es el de CLAUDE.md §5
completo. El comando no cambió: es el mismo, con más categorías en la tabla final.

Pendiente (no implementado todavía, ninguno bloquea el uso normal):

| Flag | Por qué no está |
|---|---|
| `--only conversations,memories` | Ya hay cinco categorías, pero la cara de la conversión sigue siendo `conversations` (los ~98 MB); las otras cuatro suman unos 40 KB, así que filtrar todavía no ahorra tiempo apreciable. Se implementará cuando haya una razón de uso (convertir solo las memorias para probar plantillas, por ejemplo), no por completar la firma. |
| `--strict` (CA-2, código 3) | Requiere decidir qué cuenta como "estricto" (¿cualquier `ParseError`? ¿también las advertencias?). Se define junto con la API (M3), que necesita la misma semántica para marcar un job como fallido. |
| `--json` (CA-5) | `inventory --json` ya cubre el caso "script que inspecciona"; para `convert` el equivalente es `_report/summary.json`, que ya se escribe siempre. Falta solo volcarlo también a stdout. |

Decisiones tomadas al implementarlo:

- **`--overwrite` no borra nada.** Autoriza a escribir en una carpeta que ya tiene
  contenido; los archivos que la conversión regenera se sobrescriben (es idempotente) y
  lo que no reconoce se queda donde estaba. Borrar el árbol del usuario sería una
  operación destructiva que un flag de una palabra no debería disparar.
- **La comprobación de "salida no vacía" vive en el adapter**
  (`FilesystemSink.ensure_writable`), porque es una pregunta al disco, y se hace ANTES
  de escribir el primer byte (CA-3). El error propio es `OutputNotEmptyError`, que
  hereda de `ClaudeExportMdError` y por tanto ya sale con código 2.
- **El destino lo construye el CLI, no el core.** `convert(source, sink, …)` recibe el
  puerto `MarkdownSink` (ADR-0006); el comando crea el `FilesystemSink(salida)` y se lo
  pasa. Por eso los mensajes finales (`Salida:` / `Índice:`) imprimen el `Path` que el
  usuario escribió, no `ConvertResult.destination`, que es un `str` genérico válido
  también para un zip.
- **Progreso (CA-4)**: `Console.status` con el contador por categoría, alimentado por un
  callback `(categoría, ítems)` que el caso de uso llama mientras convierte. No se usa
  una barra con total porque las conversaciones se recorren en streaming y el total no
  se conoce hasta el final. Con `--quiet` o sin TTY no se imprime nada durante la
  corrida, solo el resumen.
- **Advertencias**: se agrupan por FAMILIA antes de truncar (`group_warnings`). Una
  familia es el mensaje sin rutas, uuids ni cantidades, así que los avisos que solo
  cambian en el archivo cuentan como uno: se imprime el primero de la familia con
  `(+N similares)`. Las familias se ordenan de menos a más repetidas —lo que sale una
  sola vez suele ser lo accionable— y se muestran 5 (`MAX_WARNINGS`); el resto se cuenta
  como "… y N tipos de aviso más en `_report/summary.json`", que las lleva todas y sin
  agrupar. Truncar la lista cruda escondía, con 8 proyectos, el aviso único de proyectos
  huérfanos detrás de tres copias del mismo "documento sin contenido" (revisión de M2).

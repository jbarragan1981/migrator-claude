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

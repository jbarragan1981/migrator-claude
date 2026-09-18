# Especificaciones — claude-export-md

Cada spec sigue la misma forma: **Objetivo · Alcance · Fuera de alcance · Criterios de aceptación (Dado/Cuando/Entonces) · Dependencias · Riesgos**. Un spec es la fuente de verdad para los tests de aceptación; si el código y el spec discrepan, se corrige uno de los dos en el mismo cambio.

| # | Spec | Milestone | Agente principal |
|---|---|---|---|
| 01 | [Inventario del export](01-inventory.md) | M0 | format-explorer / core-developer |
| 02 | [Modelo de dominio](02-domain-model.md) | M1 | core-developer |
| 03 | [Parsers por categoría](03-parsers.md) | M1–M2 | core-developer |
| 04 | [Salida Markdown](04-markdown-output.md) | M1–M2 | core-developer |
| 05 | [CLI](05-cli.md) | M1 | core-developer |
| 06 | [API](06-api.md) | M3 | api-developer |
| 07 | [Web](07-web.md) | M4 | web-developer |
| 08 | [Distribución](08-distribution.md) | M5 | release-engineer |

Estado vivo del proyecto: [STATUS.md](STATUS.md). Decisiones: [../adr/](../adr/). Formato descubierto: [../export-format/](../export-format/).

## Requisitos transversales (aplican a todos los specs)
- **RT-1 Privacidad**: ningún dato del export sale de la máquina; sin telemetría; `exports/` y `output/` fuera del repo.
- **RT-2 Determinismo**: misma entrada → misma salida byte a byte (nombres, orden, fechas UTC).
- **RT-3 Tolerancia**: un ítem inválido se reporta y no detiene la corrida.
- **RT-4 Escala**: 1 GB de `conversations.json` debe procesarse con < 500 MB de RAM.
- **RT-5 Portabilidad**: Windows 11, macOS y Linux; rutas con espacios y acentos.
- **RT-6 Idioma**: interfaz y mensajes en español por defecto, inglés disponible.

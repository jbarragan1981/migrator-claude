# ADR-0002: Lectura en streaming con ijson para archivos grandes
Fecha: 2026-09-18   Estado: Aceptada
## Contexto
`conversations.json` de una cuenta con años de uso puede pesar cientos de MB o más de 1 GB; `json.load` lo carga completo en RAM.
## Decisión
Todo archivo del export que pueda ser un array grande se lee con `ijson.items(f, "item")`. Los fixtures pequeños se leen igual, para que el camino probado sea el real.
## Alternativas consideradas
- `json.load` + confiar en que el usuario tenga RAM — falla justo en las cuentas que más necesitan la herramienta.
- Dividir el archivo previamente con `jq` — dependencia externa y paso manual.
## Consecuencias
+ Memoria acotada (RT-4). — Un hook bloquea `json.load(` en el parser de conversations.

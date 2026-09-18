# ADR-0001: Arquitectura hexagonal con `core` como librería pura
Fecha: 2026-09-18   Estado: Aceptada
## Contexto
Queremos que la herramienta sirva a otros por tres canales (CLI, web local, ejecutable) y que el formato del export, que Anthropic cambia sin aviso, esté aislado del resto.
## Decisión
`packages/core` es una librería Python sin dependencias de framework. Define entidades (pydantic), ports (`Protocol`) y adapters. `cli`, `api` y `web` son capas delgadas que solo llaman a la API pública de core.
## Alternativas consideradas
- Una app FastAPI monolítica con el parseo dentro — acopla el parseo al servidor; el CLI tendría que arrancar FastAPI.
- Parseo en el navegador (Angular) — obliga a reimplementar en TS y limita el tamaño de archivos.
## Consecuencias
+ Un solo lugar para adaptar cambios de formato; CLI publicable en PyPI sin peso extra.
- Disciplina extra: un hook (`guard_files.py`) bloquea imports de frameworks en core.

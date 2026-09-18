---
name: adr
description: Redacta un Architecture Decision Record corto en docs/adr/ cuando se toma o cambia una decisión de arquitectura (nueva dependencia, cambio en domain/ o ports/, formato de salida, estrategia de jobs). Úsalo cuando el usuario diga "documenta la decisión", "por qué elegimos X", "ADR", o cuando el hook de stop lo pida.
---

# ADR

Archivo: `docs/adr/ADR-NNNN-<slug>.md` (NNNN = siguiente número; ver `ls docs/adr`).

```
# ADR-NNNN: <título en una línea>
Fecha: YYYY-MM-DD   Estado: Propuesta | Aceptada | Reemplazada por ADR-XXXX
## Contexto
Qué problema o fuerza obliga a decidir. 3–6 líneas.
## Decisión
Qué se decidió, en presente ("Usamos ijson para…").
## Alternativas consideradas
- Opción A — por qué no.
- Opción B — por qué no.
## Consecuencias
+ beneficios concretos
- costos / riesgos y cómo se mitigan
## Referencias
Spec o issue relacionado.
```

Reglas: máximo una página; una decisión por ADR; no se edita un ADR aceptado, se reemplaza; añade una fila al índice `docs/adr/README.md`.

# light_metadata

Version de formato: batched-manifest (2026)
Archivos: 1 archivo con patron `light_metadata-000/*.json`
Tamano observado: 152 bytes en el export real del usuario
Items: 1 (approx_item_count=1, item_count_exact=true - el unico caso del inventario con conteo exacto, por ser un archivo diminuto)
Partes: 1 (parts=[0])

Fuente: docs/export-format/inventory.json (categoria light_metadata) + fixture anonimizado packages/core/tests/fixtures/v2026-batched/light_metadata/sample-01.json.

## Estructura

- raiz: array con exactamente 1 item (perfil de la cuenta).
- item:
  - email_address: string (obligatorio, 26 chars anonimizados - el correo de la cuenta)
  - full_name: string (obligatorio, 7 chars anonimizados)
  - uuid: string (obligatorio, 36 chars - identificador de cuenta)
  - verified_phone_number: null en la muestra (clave presente pero valor null - no se pudo observar el caso con un telefono verificado)

Mapea limpio a la entidad Account de docs/specs/02-domain-model.md (id=uuid, email=email_address, display_name=full_name).

## Variantes observadas

Solo hay 1 item en todo el export (una cuenta), asi que no hay variantes entre items que comparar. No se puede determinar a partir de esta muestra si light_metadata alguna vez trae mas de 1 item (p.ej. cuentas de equipo/organizacion con varios miembros).

## Ejemplo anonimizado (unico item)

```json
[
  {
    "email_address": "<str:26>",
    "full_name": "<str:7>",
    "uuid": "<str:36>",
    "verified_phone_number": null
  }
]
```

## Dudas / no determinable

- No determinable si verified_phone_number alguna vez trae un valor no-null en otras cuentas (siempre null en esta muestra de 1).
- No determinable si light_metadata puede traer mas de 1 item (cuentas de organizacion/equipo) - esta cuenta es individual y solo se observo 1.
- No hay campos de configuracion/settings visibles (CLAUDE.md seccion 5 menciona "perfil, configuracion" para account.md) - en este export light_metadata solo trae identidad basica, ningun campo de preferencias/settings aparecio en la muestra.

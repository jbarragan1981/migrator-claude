---
name: angular-feature
description: Receta para crear una feature en apps/web (Angular 21 standalone, signals, Material outline, Tailwind 3, Transloco es/en) consumiendo el cliente OpenAPI generado. Úsalo cuando el usuario pida una pantalla, componente, tabla, formulario o flujo nuevo en el front.
---

# Nueva feature en apps/web

## Estructura
```
apps/web/src/app/features/<feature>/
├── <feature>.routes.ts          # lazy: loadComponent
├── <feature>-page.component.ts  # contenedor: inyecta servicio, expone signals
├── components/                  # presentacionales, @Input()/@Output() o input()/output()
└── <feature>.service.ts         # llama al cliente generado en core/api; expone signals
```

## Pasos
1. Verifica que el endpoint existe en `apps/web/src/app/core/api` (generado). Si no, `just gen-client`; si tampoco existe en la API, pide al `api-developer` que lo implemente. Nunca lo mockees en código de producción.
2. Componente standalone, `changeDetection: ChangeDetectionStrategy.OnPush`, `inject()` en vez de constructor, estado en `signal()` / `computed()`; efectos solo con `effect()` y justificados.
3. Formularios: `ReactiveFormsModule`, `mat-form-field appearance="outline"`, mensajes de error por Transloco.
4. Textos: `{{ 'feature.clave' | transloco }}`; agrega la clave en `assets/i18n/es.json` y `en.json` en el mismo cambio.
5. Estilos con utilidades Tailwind; nada de CSS global nuevo. Verifica ≥ 360 px.
6. Test `<feature>-page.component.spec.ts` con `TestBed` + `HttpTestingController` (o `provideHttpClientTesting`).
7. `pnpm -C apps/web lint && pnpm -C apps/web test --watch=false && pnpm -C apps/web build`.

## Prohibido
- `any`, `subscribe` sin `takeUntilDestroyed`, lógica de parseo del export en el navegador, NgModules, NgRx.

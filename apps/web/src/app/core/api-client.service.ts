import { Injectable, inject } from '@angular/core';

import { DefaultService } from './api/services/DefaultService';
import { ExportsService } from './api/services/ExportsService';
import { JobsService } from './api/services/JobsService';
import { OutputService } from './api/services/OutputService';

/**
 * Punto único de inyección para el cliente OpenAPI generado (`core/api/`, no se
 * edita a mano — CLAUDE.md §3, `just gen-client`). Las features inyectan
 * `ApiClientService` en vez de cada `*Service` generado por separado, así que si
 * `just gen-client` reorganiza los servicios (p. ej. agrupa endpoints distinto tras
 * agregar un tag en el OpenAPI) el cambio se absorbe en un solo lugar.
 *
 * `OpenAPI.BASE` se deja en '' (default del generador): en dev, `proxy.conf.json`
 * reenvía `/api` y `/health` a `http://localhost:8000` (ver angular.json, target
 * `serve`); en producción, el mismo origen debe servir la API detrás de un proxy
 * (nginx u otro) — todavía no configurado en docker-compose (pendiente de cuando
 * se agregue el servicio `web`, ver docs/specs/STATUS.md M4).
 *
 * SSE (`GET /jobs/{id}/events`) NO se consume a través de este servicio: el
 * cliente generado lo expone sobre HttpClient sin tipo fuerte de retorno (no puede
 * modelar `text/event-stream`), pero la convención del proyecto es envolver
 * `EventSource` directamente en un servicio de features que exponga una signal
 * (ver .claude/skills/angular-feature y CLAUDE.md §7) — eso se hace en la feature
 * `jobs`, no acá.
 */
@Injectable({ providedIn: 'root' })
export class ApiClientService {
  readonly health = inject(DefaultService);
  readonly exports = inject(ExportsService);
  readonly jobs = inject(JobsService);
  readonly output = inject(OutputService);
}

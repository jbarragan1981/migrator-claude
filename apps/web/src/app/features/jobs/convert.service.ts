import { Injectable, inject, signal } from '@angular/core';

import { ApiClientService } from '../../core/api-client.service';
import { ApiError } from '../../core/api/core/ApiError';

export type ConvertStatus = 'idle' | 'starting' | 'started' | 'error';

export type ConvertErrorKey =
  | 'jobs.errors.notFound'
  | 'jobs.errors.conflict'
  | 'jobs.errors.network'
  | 'jobs.errors.generic';

/**
 * Envuelve `POST /api/v1/exports/{id}/convert` (spec 06). Se provee a nivel de
 * `ConvertPageComponent` (no `providedIn: 'root'`) para que cada visita a la
 * pantalla arranque con signals limpias, igual que `UploadService`/`InventoryService`.
 *
 * No manda `only`/`templates` en el body (encargo de la tarea: `only` es un
 * no-op documentado en `docs/specs/06-api.md`, todavía no filtra categorías).
 */
@Injectable()
export class ConvertService {
  private readonly api = inject(ApiClientService);

  readonly status = signal<ConvertStatus>('idle');
  readonly errorKey = signal<ConvertErrorKey | null>(null);
  readonly jobId = signal<string | null>(null);

  start(exportId: string): void {
    this.status.set('starting');
    this.errorKey.set(null);
    this.jobId.set(null);
    this.api.jobs.convertExportApiV1ExportsExportIdConvertPost(exportId, undefined).subscribe({
      next: (response) => {
        this.status.set('started');
        this.jobId.set(response.job_id);
      },
      error: (error: unknown) => {
        this.status.set('error');
        this.errorKey.set(this.toErrorKey(error));
      },
    });
  }

  private toErrorKey(error: unknown): ConvertErrorKey {
    if (error instanceof ApiError) {
      switch (error.status) {
        case 404:
          return 'jobs.errors.notFound';
        case 409:
          return 'jobs.errors.conflict';
        default:
          return 'jobs.errors.generic';
      }
    }
    // status 0 / sin ApiError -> sin conexión al API (CA-2 de spec 07).
    return 'jobs.errors.network';
  }
}

import { Injectable, inject, signal } from '@angular/core';

import { ApiClientService } from '../../core/api-client.service';
import { ApiError } from '../../core/api/core/ApiError';

export type UploadStatus = 'idle' | 'uploading' | 'error' | 'success';

/** Claves de Transloco (`upload.errors.*`) — nunca se muestra el mensaje crudo del backend (CA-2). */
export type UploadErrorKey =
  | 'upload.errors.network'
  | 'upload.errors.tooLarge'
  | 'upload.errors.badFile'
  | 'upload.errors.forbidden'
  | 'upload.errors.generic';

/**
 * Envuelve `POST /api/v1/exports` (multipart). Se provee a nivel de componente
 * (`UploadPageComponent`, no `providedIn: 'root'`) para que cada visita a la
 * pantalla arranque con signals limpias en vez de arrastrar el estado de una
 * subida anterior.
 */
@Injectable()
export class UploadService {
  private readonly api = inject(ApiClientService);

  readonly status = signal<UploadStatus>('idle');
  readonly errorKey = signal<UploadErrorKey | null>(null);

  /** Sube los archivos elegidos y resuelve con el `export_id` del 201. */
  upload(files: File[]): Promise<string> {
    this.status.set('uploading');
    this.errorKey.set(null);
    return new Promise<string>((resolve, reject) => {
      this.api.exports.createExportApiV1ExportsPost({ file: files }).subscribe({
        next: (response) => {
          this.status.set('success');
          resolve(response.export_id);
        },
        error: (error: unknown) => {
          this.status.set('error');
          this.errorKey.set(this.toErrorKey(error));
          reject(error instanceof Error ? error : new Error('upload failed'));
        },
      });
    });
  }

  retry(): void {
    this.status.set('idle');
    this.errorKey.set(null);
  }

  private toErrorKey(error: unknown): UploadErrorKey {
    if (error instanceof ApiError) {
      switch (error.status) {
        case 413:
          return 'upload.errors.tooLarge';
        case 400:
          return 'upload.errors.badFile';
        case 403:
          return 'upload.errors.forbidden';
        default:
          return 'upload.errors.generic';
      }
    }
    // status 0 / sin ApiError: el cliente generado no envuelve los fallos de red
    // (sin conexión al API) en ApiError, solo los de status HTTP != 0 (ver
    // core/api/core/request.ts). CA-2: sin conexión -> error traducible.
    return 'upload.errors.network';
  }
}

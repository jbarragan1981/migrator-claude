import { KeyValuePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, effect, inject, input } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatListModule } from '@angular/material/list';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { Router, RouterLink } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

import { CurrentExportService } from '../../core/current-export.service';
import { ConvertService } from './convert.service';
import { JobProgressService } from './job-progress.service';

export type ConvertScreenState =
  | 'no-export'
  | 'starting'
  | 'convert-error'
  | 'connecting'
  | 'streaming'
  | 'reconciling'
  | 'connection-lost'
  | 'job-error'
  | 'done';

/**
 * Pantalla 3 de spec 07 (Conversión): al entrar, lanza `POST /convert`
 * automáticamente con el `exportId` que llega por query param
 * (`/convert?exportId=...`, ver `inventory-page.html` — `withComponentInputBinding()`
 * en `app.config.ts` también resuelve query params, no solo params de ruta) y sigue
 * el progreso por SSE (`JobProgressService`).
 *
 * Botón "Cancelar" (spec 07 menciona uno): el backend de M3 NO tiene endpoint de
 * cancelación de un job en curso (ver `docs/specs/STATUS.md`, M4). En vez de
 * simular una llamada que no existe, el botón SOLO navega de vuelta al inventario
 * sin tocar la API — el texto de la propia pantalla aclara que la conversión sigue
 * corriendo en el servidor.
 */
@Component({
  selector: 'app-convert-page',
  imports: [
    KeyValuePipe,
    MatButtonModule,
    MatCardModule,
    MatListModule,
    MatProgressBarModule,
    MatProgressSpinnerModule,
    RouterLink,
    TranslocoPipe,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [ConvertService, JobProgressService],
  templateUrl: './convert-page.html',
})
export class ConvertPageComponent {
  private readonly convertService = inject(ConvertService);
  private readonly jobProgress = inject(JobProgressService);
  private readonly router = inject(Router);
  private readonly currentExport = inject(CurrentExportService);

  /**
   * Opcional (no `input.required`) a propósito: la barra de navegación del layout
   * (`app.html`) tiene un link fijo a `/convert` sin query param — visitarlo
   * directo no debe tirar la app abajo (CA-2), sino mostrar un estado vacío que
   * lleva de vuelta al inicio.
   */
  readonly exportId = input<string | null>(null);

  readonly convertStatus = this.convertService.status;
  readonly convertErrorKey = this.convertService.errorKey;
  readonly phase = this.jobProgress.phase;
  readonly events = this.jobProgress.events;
  readonly summary = this.jobProgress.summary;
  readonly failureReason = this.jobProgress.failureReason;
  readonly reconciliationFailed = this.jobProgress.reconciliationFailed;

  readonly screenState = computed<ConvertScreenState>(() => {
    if (!this.exportId()) {
      return 'no-export';
    }
    const convertStatus = this.convertStatus();
    if (convertStatus === 'error') {
      return 'convert-error';
    }
    if (convertStatus !== 'started') {
      return 'starting';
    }
    switch (this.phase()) {
      case 'idle':
      case 'connecting':
        return 'connecting';
      case 'streaming':
        return 'streaming';
      case 'reconciling':
        return 'reconciling';
      case 'connection-lost':
        return 'connection-lost';
      case 'error':
        return 'job-error';
      case 'done':
        return 'done';
    }
  });

  readonly isTimeout = computed(() => this.failureReason() === 'timeout');

  constructor() {
    // Arranca la conversión automáticamente al entrar (o si cambia el exportId de
    // la ruta), mismo patrón que `InventoryPageComponent` para su `GET /inventory`.
    effect(() => {
      const exportId = this.exportId();
      if (exportId) {
        this.currentExport.set(exportId);
        this.convertService.start(exportId);
      }
    });
    // Conecta el SSE en cuanto el POST /convert devuelve un `job_id`.
    effect(() => {
      const jobId = this.convertService.jobId();
      if (jobId) {
        this.jobProgress.connect(jobId);
      }
    });
  }

  retryConvert(): void {
    const exportId = this.exportId();
    if (exportId) {
      this.convertService.start(exportId);
    }
  }

  retryConnectionCheck(): void {
    this.jobProgress.retryConnectionCheck();
  }

  cancel(): void {
    const exportId = this.exportId();
    if (exportId) {
      void this.router.navigate(['/inventory', exportId]);
    } else {
      void this.router.navigate(['/']);
    }
  }

  viewResult(): void {
    const exportId = this.exportId();
    if (exportId) {
      void this.router.navigate(['/result', exportId]);
    }
  }
}

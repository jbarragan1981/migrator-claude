import { Injectable, OnDestroy, inject, signal } from '@angular/core';

import { ApiClientService } from '../../core/api-client.service';
import type { ProgressEventSchema } from '../../core/api/models/ProgressEventSchema';
import { EventSourceFactory, type EventSourceLike } from './event-source-factory';

export type JobPhase =
  | 'idle'
  | 'connecting'
  | 'streaming'
  | 'reconciling'
  | 'connection-lost'
  | 'done'
  | 'error';

/** Mismo subconjunto que expone `GET /jobs/{id}` y el evento SSE `done` (spec 06). */
export interface JobDoneSummary {
  counts: Record<string, number> | null;
  errors: number | null;
  warnings: number | null;
}

interface JobDoneEventPayload {
  counts?: Record<string, number> | null;
  errors?: number | null;
  warnings?: number | null;
}

interface JobErrorEventPayload {
  reason?: string | null;
}

/**
 * Envuelve `GET /jobs/{id}/events` (SSE, spec 06 CA-3) con `EventSource` (vía
 * `EventSourceFactory` para poder sustituirlo en tests) y expone el progreso como
 * signals (CLAUDE.md §7 / .claude/agents/web-developer.md).
 *
 * Un evento nativo `error` de `EventSource` es AMBIGUO: el navegador dispara el
 * mismo nombre de evento tanto para un corte de conexión real (sin `data`) como
 * para el evento `event: error` que manda el propio servidor cuando el job
 * termina en `failed` (con `data` JSON). Se distinguen mirando si `event.data` es
 * un string no vacío.
 *
 * CA-2 de spec 07: un corte de conexión NUNCA se interpreta como "el job falló" —
 * se consulta `GET /jobs/{id}` una única vez (`reconcileAfterConnectionLoss`) para
 * ver el estado real del lado del servidor antes de decidir qué mostrar.
 */
@Injectable()
export class JobProgressService implements OnDestroy {
  private readonly eventSourceFactory = inject(EventSourceFactory);
  private readonly api = inject(ApiClientService);

  private source: EventSourceLike | null = null;
  private currentJobId: string | null = null;

  readonly phase = signal<JobPhase>('idle');
  readonly events = signal<ProgressEventSchema[]>([]);
  readonly summary = signal<JobDoneSummary | null>(null);
  readonly failureReason = signal<string | null>(null);
  /** `true` si el intento de reconciliación (GET /jobs/{id}) también falló por red. */
  readonly reconciliationFailed = signal(false);

  connect(jobId: string): void {
    this.disconnect();
    this.currentJobId = jobId;
    this.phase.set('connecting');
    this.events.set([]);
    this.summary.set(null);
    this.failureReason.set(null);
    this.reconciliationFailed.set(false);

    const source = this.eventSourceFactory.create(`/api/v1/jobs/${jobId}/events`);
    this.source = source;

    source.addEventListener('open', () => {
      if (this.phase() === 'connecting') {
        this.phase.set('streaming');
      }
    });

    source.addEventListener('progress', (event) => {
      this.phase.set('streaming');
      const payload = this.parse<ProgressEventSchema>(event);
      if (payload) {
        this.events.update((current) => [...current, payload]);
      }
    });

    source.addEventListener('done', (event) => {
      const payload = this.parse<JobDoneEventPayload>(event) ?? {};
      this.summary.set({
        counts: payload.counts ?? null,
        errors: payload.errors ?? null,
        warnings: payload.warnings ?? null,
      });
      this.phase.set('done');
      this.disconnect();
    });

    source.addEventListener('error', (event) => {
      if (this.isServerSentEvent(event)) {
        const payload = this.parse<JobErrorEventPayload>(event) ?? {};
        this.failureReason.set(payload.reason ?? null);
        this.phase.set('error');
        this.disconnect();
        return;
      }
      // Corte de conexión real (sin `data`): la conversión puede seguir corriendo
      // en el servidor, no se asume que falló (CA-2 de spec 07).
      if (this.phase() !== 'done' && this.phase() !== 'error') {
        this.disconnect();
        this.reconcileAfterConnectionLoss(jobId);
      }
    });
  }

  /** Reintento manual desde la UI cuando la propia reconciliación falló por red. */
  retryConnectionCheck(): void {
    if (this.currentJobId) {
      this.reconcileAfterConnectionLoss(this.currentJobId);
    }
  }

  private reconcileAfterConnectionLoss(jobId: string): void {
    this.phase.set('reconciling');
    this.reconciliationFailed.set(false);
    this.api.jobs.getJobApiV1JobsJobIdGet(jobId).subscribe({
      next: (status) => {
        this.events.set(status.progress);
        if (status.status === 'done') {
          this.summary.set({
            counts: status.counts ?? null,
            errors: status.errors ?? null,
            warnings: status.warnings ?? null,
          });
          this.phase.set('done');
        } else if (status.status === 'failed') {
          this.failureReason.set(status.reason ?? null);
          this.phase.set('error');
        } else {
          // Sigue pending/running del lado del servidor: reconectamos el stream.
          this.connect(jobId);
        }
      },
      error: () => {
        this.phase.set('connection-lost');
        this.reconciliationFailed.set(true);
      },
    });
  }

  disconnect(): void {
    this.source?.close();
    this.source = null;
  }

  ngOnDestroy(): void {
    this.disconnect();
  }

  private isServerSentEvent(event: MessageEvent): boolean {
    return typeof event.data === 'string' && event.data.length > 0;
  }

  private parse<T>(event: MessageEvent): T | null {
    if (typeof event.data !== 'string' || event.data.length === 0) {
      return null;
    }
    try {
      return JSON.parse(event.data) as T;
    } catch {
      return null;
    }
  }
}

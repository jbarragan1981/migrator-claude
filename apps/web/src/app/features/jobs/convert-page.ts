import { ChangeDetectionStrategy, Component } from '@angular/core';
import { ComingSoonComponent } from '../../shared/coming-soon';

/**
 * Pantalla 3 de spec 07 (Conversión): POST /convert + progreso por SSE.
 * Vive en `features/jobs` (CLAUDE.md §3: la feature se llama "jobs", no "convert").
 * Placeholder de scaffold (M4) — se implementa en la próxima ronda.
 */
@Component({
  selector: 'app-convert-page',
  imports: [ComingSoonComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<app-coming-soon titleKey="nav.convert" />`,
})
export class ConvertPageComponent {}

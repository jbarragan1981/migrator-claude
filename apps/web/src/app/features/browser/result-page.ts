import { ChangeDetectionStrategy, Component } from '@angular/core';
import { ComingSoonComponent } from '../../shared/coming-soon';

/**
 * Pantalla 4 de spec 07 (Resultado): árbol de carpetas + visor Markdown + búsqueda +
 * descarga zip. Vive en `features/browser` (CLAUDE.md §3). Placeholder de scaffold
 * (M4) — se implementa en la próxima ronda.
 */
@Component({
  selector: 'app-result-page',
  imports: [ComingSoonComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<app-coming-soon titleKey="nav.result" />`,
})
export class ResultPageComponent {}

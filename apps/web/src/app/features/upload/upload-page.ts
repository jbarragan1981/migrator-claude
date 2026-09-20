import { ChangeDetectionStrategy, Component } from '@angular/core';
import { ComingSoonComponent } from '../../shared/coming-soon';

/**
 * Pantalla 1 de spec 07 (Inicio/Carga): dropzone de zips/manifiesto + nota de
 * privacidad + POST /exports. Placeholder de scaffold (M4) — se implementa en la
 * próxima ronda siguiendo .claude/skills/angular-feature/SKILL.md.
 */
@Component({
  selector: 'app-upload-page',
  imports: [ComingSoonComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<app-coming-soon titleKey="nav.upload" />`,
})
export class UploadPageComponent {}

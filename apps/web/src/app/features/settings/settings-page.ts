import { ChangeDetectionStrategy, Component } from '@angular/core';
import { ComingSoonComponent } from '../../shared/coming-soon';

/**
 * Pantalla 5 de spec 07 (Ajustes): idioma es/en, tema claro/oscuro, plantillas
 * personalizadas. `features/settings` no está en la lista de CLAUDE.md §3
 * (upload/inventory/jobs/browser) porque esa lista se escribió antes de completar
 * spec 07; se agrega siguiendo la misma receta (angular-feature skill) para cubrir
 * la 5ta pantalla del spec. Placeholder de scaffold (M4) — se implementa después.
 */
@Component({
  selector: 'app-settings-page',
  imports: [ComingSoonComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<app-coming-soon titleKey="nav.settings" />`,
})
export class SettingsPageComponent {}

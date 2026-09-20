import { ChangeDetectionStrategy, Component } from '@angular/core';
import { ComingSoonComponent } from '../../shared/coming-soon';

/**
 * Pantalla 2 de spec 07 (Inventario): tabla por categoría + GET /inventory.
 * Placeholder de scaffold (M4) — se implementa en la próxima ronda.
 */
@Component({
  selector: 'app-inventory-page',
  imports: [ComingSoonComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<app-coming-soon titleKey="nav.inventory" />`,
})
export class InventoryPageComponent {}

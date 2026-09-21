import { KeyValuePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, effect, inject, input } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTableModule } from '@angular/material/table';
import { RouterLink } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

import { CurrentExportService } from '../../core/current-export.service';
import { BytesSizePipe } from '../../shared/byte-size.pipe';
import { InventoryService } from './inventory.service';

/**
 * Pantalla 2 de spec 07 (Inventario): `GET /exports/{id}/inventory` + tabla por
 * categoría + avisos de categorías/partes faltantes. `exportId` llega desde la
 * ruta `/inventory/:exportId` vía `withComponentInputBinding()` (app.config.ts).
 */
@Component({
  selector: 'app-inventory-page',
  imports: [
    KeyValuePipe,
    MatButtonModule,
    MatCardModule,
    MatProgressSpinnerModule,
    MatTableModule,
    RouterLink,
    TranslocoPipe,
    BytesSizePipe,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [InventoryService],
  templateUrl: './inventory-page.html',
})
export class InventoryPageComponent {
  readonly inventoryService = inject(InventoryService);
  private readonly currentExport = inject(CurrentExportService);

  readonly exportId = input.required<string>();

  readonly status = this.inventoryService.status;
  readonly errorKey = this.inventoryService.errorKey;
  readonly inventory = this.inventoryService.inventory;
  readonly rows = this.inventoryService.rows;
  readonly hasIssues = this.inventoryService.hasIssues;

  readonly displayedColumns = ['name', 'files', 'size', 'items', 'status'];

  constructor() {
    // Vuelve a cargar el inventario si cambia el `exportId` de la ruta (p. ej.
    // navegación directa entre dos exports sin recarga completa de la página).
    effect(() => {
      const exportId = this.exportId();
      this.currentExport.set(exportId);
      this.inventoryService.load(exportId);
    });
  }

  reload(): void {
    this.inventoryService.load(this.exportId());
  }
}

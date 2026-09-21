import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatToolbarModule } from '@angular/material/toolbar';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

import { CurrentExportService } from './core/current-export.service';

@Component({
  selector: 'app-root',
  imports: [
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    MatToolbarModule,
    MatButtonModule,
    TranslocoPipe,
  ],
  templateUrl: './app.html',
  styleUrl: './app.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class App {
  private readonly currentExport = inject(CurrentExportService);
  private readonly router = inject(Router);

  /**
   * El export activo (persistido en localStorage por `CurrentExportService`) es
   * lo que le permite al menú de arriba seguir apuntando a Inventario/
   * Conversión/Resultado con el id correcto incluso después de navegar a otra
   * pantalla - antes esos links iban a una ruta sin id que el router no podía
   * resolver y la pantalla quedaba vacía.
   */
  readonly exportId = this.currentExport.exportId;
  readonly exportIdShort = computed(() => this.exportId()?.slice(0, 8) ?? null);

  startOver(): void {
    this.currentExport.clear();
    void this.router.navigate(['/']);
  }
}

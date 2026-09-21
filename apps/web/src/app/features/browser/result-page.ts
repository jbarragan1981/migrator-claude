import { ChangeDetectionStrategy, Component, computed, effect, inject, input } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { TranslocoPipe } from '@jsverse/transloco';

import { CurrentExportService } from '../../core/current-export.service';
import { BytesSizePipe } from '../../shared/byte-size.pipe';
import { flattenTree } from './result-tree';
import { ResultService } from './result.service';

/**
 * Pantalla 4 de spec 07 (Resultado): árbol de `GET /output/tree` (izquierda) +
 * visor de archivo (derecha) + búsqueda por nombre + descarga del zip completo.
 *
 * `exportId` llega SIEMPRE (path param, `browser.routes.ts::':exportId'`; una
 * visita a `/result` sin id redirige a `/` antes de instanciar este componente).
 */
@Component({
  selector: 'app-result-page',
  imports: [
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressSpinnerModule,
    TranslocoPipe,
    BytesSizePipe,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [ResultService],
  templateUrl: './result-page.html',
})
export class ResultPageComponent {
  readonly resultService = inject(ResultService);
  private readonly currentExport = inject(CurrentExportService);

  readonly exportId = input.required<string>();

  readonly treeStatus = this.resultService.treeStatus;
  readonly treeErrorKey = this.resultService.treeErrorKey;
  readonly searchQuery = this.resultService.searchQuery;
  readonly rows = computed(() => flattenTree(this.resultService.filteredTree()));

  readonly selectedPath = this.resultService.selectedPath;
  readonly fileStatus = this.resultService.fileStatus;
  readonly fileErrorKey = this.resultService.fileErrorKey;
  readonly fileContent = this.resultService.fileContent;

  /**
   * `GET /exports/{id}/download` (spec 06) devuelve un zip binario, no JSON:
   * un `<a href>` plano que apunta directo al endpoint es el mecanismo más
   * simple y estándar para que el navegador lo descargue (deja que responda con
   * su propio `Content-Disposition: attachment; filename=...`, ver
   * `services/output.py::TempZipResponse` del lado de la API) — evita además el
   * mismo problema de `responseType` documentado en `ResultService` para
   * `/output/file` (acá sería aún peor: `JSON.parse` sobre un zip binario).
   */
  readonly downloadHref = computed(() => `/api/v1/exports/${encodeURIComponent(this.exportId())}/download`);

  constructor() {
    effect(() => {
      const exportId = this.exportId();
      this.currentExport.set(exportId);
      this.resultService.loadTree(exportId);
    });
  }

  reloadTree(): void {
    this.resultService.reloadTree();
  }

  onSearchInputEvent(event: Event): void {
    const target = event.target as HTMLInputElement;
    this.resultService.setSearchQuery(target.value);
  }

  selectFile(path: string): void {
    const row = this.rows().find((entry) => entry.node.path === path);
    if (row) {
      this.resultService.selectFile(this.exportId(), row.node);
    }
  }

  retryFile(): void {
    this.resultService.retryFile(this.exportId());
  }
}

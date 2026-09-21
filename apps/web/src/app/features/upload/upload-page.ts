import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatListModule } from '@angular/material/list';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { Router } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

import { CurrentExportService } from '../../core/current-export.service';
import { BytesSizePipe } from '../../shared/byte-size.pipe';
import { UploadDropzoneComponent } from './components/upload-dropzone';
import { UploadService } from './upload.service';

/**
 * Pantalla 1 de spec 07 (Inicio/Carga): dropzone de zips/manifiesto + nota de
 * privacidad + POST /exports. Al tener éxito navega a `/inventory/:exportId`
 * (CA-1: primer tramo del flujo de ≤ 5 clics).
 */
@Component({
  selector: 'app-upload-page',
  imports: [
    MatButtonModule,
    MatCardModule,
    MatListModule,
    MatProgressBarModule,
    TranslocoPipe,
    BytesSizePipe,
    UploadDropzoneComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [UploadService],
  templateUrl: './upload-page.html',
})
export class UploadPageComponent {
  private readonly uploadService = inject(UploadService);
  private readonly router = inject(Router);
  private readonly currentExport = inject(CurrentExportService);

  readonly selectedFiles = signal<File[]>([]);
  readonly status = this.uploadService.status;
  readonly errorKey = this.uploadService.errorKey;
  readonly isUploading = computed(() => this.status() === 'uploading');
  readonly canSubmit = computed(() => this.selectedFiles().length > 0 && !this.isUploading());

  onFilesSelected(files: File[]): void {
    // Se acumula por nombre (no se reemplaza) para permitir soltar los zips y
    // luego el member-manifest-*.json por separado, o al revés.
    const byName = new Map(this.selectedFiles().map((file) => [file.name, file]));
    for (const file of files) {
      byName.set(file.name, file);
    }
    this.selectedFiles.set(Array.from(byName.values()));
  }

  removeFile(name: string): void {
    this.selectedFiles.set(this.selectedFiles().filter((file) => file.name !== name));
  }

  async submit(): Promise<void> {
    if (!this.canSubmit()) {
      return;
    }
    try {
      const exportId = await this.uploadService.upload(this.selectedFiles());
      this.currentExport.set(exportId);
      await this.router.navigate(['/inventory', exportId]);
    } catch {
      // El error ya quedó reflejado en `status`/`errorKey` (signals del servicio).
    }
  }

  retry(): void {
    this.uploadService.retry();
  }
}

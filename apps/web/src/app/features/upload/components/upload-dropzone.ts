import { ChangeDetectionStrategy, Component, ElementRef, output, signal, viewChild } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { TranslocoPipe } from '@jsverse/transloco';

/**
 * Presentacional: solo captura archivos (drag & drop o input tradicional) y los
 * emite hacia el contenedor. No sube nada ni conoce el cliente API (CA-7: el
 * front nunca lee/parsea el contenido de los archivos, esto es un mero selector).
 */
@Component({
  selector: 'app-upload-dropzone',
  imports: [MatButtonModule, TranslocoPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div
      class="flex flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed p-6 text-center transition-colors focus:outline-2 focus:outline-offset-2"
      [class.border-blue-600]="isDragOver()"
      [class.bg-blue-50]="isDragOver()"
      role="button"
      tabindex="0"
      [attr.aria-label]="'upload.dropzone.ariaLabel' | transloco"
      (click)="openFilePicker()"
      (keydown.enter)="openFilePicker()"
      (keydown.space)="openFilePicker($event)"
      (dragover)="onDragOver($event)"
      (dragleave)="onDragLeave()"
      (drop)="onDrop($event)"
    >
      <p>{{ 'upload.dropzone.instructions' | transloco }}</p>
      <button mat-stroked-button type="button" (click)="onChooseClick($event)">
        {{ 'upload.dropzone.chooseFiles' | transloco }}
      </button>
      <input
        #fileInput
        type="file"
        multiple
        accept=".zip,.json,application/zip,application/json"
        class="hidden"
        [attr.aria-label]="'upload.dropzone.chooseFiles' | transloco"
        (change)="onFileInputChange($event)"
      />
    </div>
  `,
})
export class UploadDropzoneComponent {
  readonly filesSelected = output<File[]>();
  readonly isDragOver = signal(false);
  private readonly fileInput = viewChild.required<ElementRef<HTMLInputElement>>('fileInput');

  openFilePicker(event?: Event): void {
    event?.preventDefault();
    this.fileInput().nativeElement.click();
  }

  onChooseClick(event: Event): void {
    event.stopPropagation();
    this.fileInput().nativeElement.click();
  }

  onDragOver(event: DragEvent): void {
    event.preventDefault();
    this.isDragOver.set(true);
  }

  onDragLeave(): void {
    this.isDragOver.set(false);
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    this.isDragOver.set(false);
    const files = event.dataTransfer?.files;
    if (files && files.length > 0) {
      this.filesSelected.emit(Array.from(files));
    }
  }

  onFileInputChange(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (input.files && input.files.length > 0) {
      this.filesSelected.emit(Array.from(input.files));
      input.value = '';
    }
  }
}

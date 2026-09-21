import { HttpClient, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';

import { ApiClientService } from '../../core/api-client.service';
import { ApiError } from '../../core/api/core/ApiError';
import type { OutputTreeEntry } from '../../core/api/models/OutputTreeEntry';
import { buildOutputTree, filterTree, type TreeNode } from './result-tree';

export type TreeLoadStatus = 'idle' | 'loading' | 'error' | 'success';
export type FileLoadStatus = 'idle' | 'loading' | 'error' | 'not-previewable' | 'success';

export type TreeErrorKey = 'result.errors.notFound' | 'result.errors.network' | 'result.errors.generic';
export type FileErrorKey =
  | 'result.errors.file.notFound'
  | 'result.errors.file.network'
  | 'result.errors.file.generic';

/**
 * Extensiones que sabemos binarias (imágenes, empaquetados, fuentes…). El export
 * de Claude.ai que produce `core` es texto de punta a punta (Markdown + los
 * artefactos de código extraídos de las conversaciones, todos texto), así que se
 * trata como binario SOLO lo que reconocemos como tal, en vez de mantener una
 * lista blanca — más robusto a extensiones de código que no anticipamos.
 */
const KNOWN_BINARY_EXTENSIONS = new Set([
  'png',
  'jpg',
  'jpeg',
  'gif',
  'webp',
  'bmp',
  'ico',
  'pdf',
  'zip',
  'gz',
  'exe',
  'bin',
  'woff',
  'woff2',
  'ttf',
  'mp3',
  'mp4',
  'mov',
]);

function extensionOf(path: string): string {
  const lastDot = path.lastIndexOf('.');
  return lastDot === -1 ? '' : path.slice(lastDot + 1).toLowerCase();
}

function isLikelyBinary(path: string): boolean {
  return KNOWN_BINARY_EXTENSIONS.has(extensionOf(path));
}

/**
 * Envuelve `GET /exports/{id}/output/tree` y `GET /exports/{id}/output/file`
 * (spec 06, pantalla 4 de spec 07). Se provee a nivel de `ResultPageComponent`.
 *
 * `GET /output/file` se llama con `HttpClient` DIRECTO en vez del método generado
 * (`OutputService.getOutputFileApiV1ExportsExportIdOutputFileGet`, que devuelve
 * `any`): el cliente generado (`core/api/core/request.ts::sendRequest`) no fija
 * `responseType`, así que `HttpClient` usa su default `'json'` y hace
 * `JSON.parse()` sobre la respuesta — que para un `.md`/`.py`/texto plano real
 * FALLA y el request sale como error incluso con un 200 real del servidor
 * (comportamiento documentado de Angular: un fallo de `JSON.parse` con
 * `responseType: 'json'` se propaga como `HttpErrorResponse`, no como éxito). No
 * es una limitación de este endpoint en particular: pasa lo mismo con `/download`
 * (por eso ese otro se resuelve con un `<a href>` plano, ver `result-page.html`).
 * Corregirlo en el generador queda fuera de esta ronda (no toca `apps/api`); acá
 * se evita pidiendo `responseType: 'text'` explícito a la MISMA URL que usaría el
 * cliente generado.
 */
@Injectable()
export class ResultService {
  private readonly api = inject(ApiClientService);
  private readonly http = inject(HttpClient);

  readonly treeStatus = signal<TreeLoadStatus>('idle');
  readonly treeErrorKey = signal<TreeErrorKey | null>(null);
  readonly entries = signal<OutputTreeEntry[]>([]);

  readonly searchQuery = signal('');
  readonly tree = computed<TreeNode[]>(() => buildOutputTree(this.entries()));
  readonly filteredTree = computed<TreeNode[]>(() => filterTree(this.tree(), this.searchQuery()));

  readonly selectedPath = signal<string | null>(null);
  readonly fileStatus = signal<FileLoadStatus>('idle');
  readonly fileErrorKey = signal<FileErrorKey | null>(null);
  readonly fileContent = signal<string | null>(null);

  private lastExportId: string | null = null;

  loadTree(exportId: string): void {
    this.lastExportId = exportId;
    this.treeStatus.set('loading');
    this.treeErrorKey.set(null);
    this.api.output.getOutputTreeApiV1ExportsExportIdOutputTreeGet(exportId).subscribe({
      next: (response) => {
        this.entries.set(response.entries);
        this.treeStatus.set('success');
      },
      error: (error: unknown) => {
        this.treeStatus.set('error');
        this.treeErrorKey.set(this.toTreeErrorKey(error));
      },
    });
  }

  reloadTree(): void {
    if (this.lastExportId) {
      this.loadTree(this.lastExportId);
    }
  }

  setSearchQuery(query: string): void {
    this.searchQuery.set(query);
  }

  selectFile(exportId: string, node: TreeNode): void {
    if (node.kind !== 'file') {
      return;
    }
    this.selectedPath.set(node.path);
    this.fileContent.set(null);
    this.fileErrorKey.set(null);
    if (isLikelyBinary(node.path)) {
      this.fileStatus.set('not-previewable');
      return;
    }
    this.fetchFile(exportId, node.path);
  }

  retryFile(exportId: string): void {
    const path = this.selectedPath();
    if (path) {
      this.fetchFile(exportId, path);
    }
  }

  private fetchFile(exportId: string, path: string): void {
    this.fileStatus.set('loading');
    this.fileErrorKey.set(null);
    const params = new HttpParams().set('path', path);
    this.http
      .get(`/api/v1/exports/${encodeURIComponent(exportId)}/output/file`, { params, responseType: 'text' })
      .subscribe({
        next: (content) => {
          this.fileContent.set(content);
          this.fileStatus.set('success');
        },
        error: (error: unknown) => {
          this.fileStatus.set('error');
          this.fileErrorKey.set(this.toFileErrorKey(error));
        },
      });
  }

  private toTreeErrorKey(error: unknown): TreeErrorKey {
    if (error instanceof ApiError) {
      return error.status === 404 ? 'result.errors.notFound' : 'result.errors.generic';
    }
    return 'result.errors.network';
  }

  private toFileErrorKey(error: unknown): FileErrorKey {
    if (error instanceof HttpErrorResponse) {
      if (error.status === 404) {
        return 'result.errors.file.notFound';
      }
      if (error.status === 0) {
        return 'result.errors.file.network';
      }
      return 'result.errors.file.generic';
    }
    return 'result.errors.file.network';
  }
}

import { Injectable, computed, inject, signal } from '@angular/core';

import { ApiClientService } from '../../core/api-client.service';
import { ApiError } from '../../core/api/core/ApiError';
import type { CategoryRow, InventoryView } from './inventory.models';

export type InventoryLoadStatus = 'idle' | 'loading' | 'error' | 'success';

export type InventoryErrorKey =
  | 'inventory.errors.notFound'
  | 'inventory.errors.network'
  | 'inventory.errors.generic';

/**
 * Envuelve `GET /api/v1/exports/{id}/inventory`. Se provee a nivel de
 * componente (`InventoryPageComponent`) para que cada `exportId` de ruta
 * arranque con signals limpias.
 */
@Injectable()
export class InventoryService {
  private readonly api = inject(ApiClientService);

  readonly status = signal<InventoryLoadStatus>('idle');
  readonly errorKey = signal<InventoryErrorKey | null>(null);
  readonly inventory = signal<InventoryView | null>(null);

  /** Filas de tabla: unión de categorías presentes y `missing_categories`. */
  readonly rows = computed<CategoryRow[]>(() => {
    const inventory = this.inventory();
    if (!inventory) {
      return [];
    }
    const names = new Set<string>([
      ...Object.keys(inventory.categories),
      ...inventory.missing_categories,
    ]);
    return Array.from(names)
      .sort((a, b) => a.localeCompare(b))
      .map((name) => this.toRow(inventory, name));
  });

  readonly hasIssues = computed(() => {
    const inventory = this.inventory();
    if (!inventory) {
      return false;
    }
    return (
      inventory.missing_categories.length > 0 ||
      Object.keys(inventory.missing_parts).length > 0 ||
      inventory.warnings.length > 0
    );
  });

  load(exportId: string): void {
    this.status.set('loading');
    this.errorKey.set(null);
    this.api.exports.getExportInventoryApiV1ExportsExportIdInventoryGet(exportId).subscribe({
      next: (raw) => {
        this.inventory.set(raw as InventoryView);
        this.status.set('success');
      },
      error: (error: unknown) => {
        this.status.set('error');
        this.errorKey.set(this.toErrorKey(error));
      },
    });
  }

  private toRow(inventory: InventoryView, name: string): CategoryRow {
    const category = inventory.categories[name];
    const missingParts = inventory.missing_parts[name] ?? [];
    const hasFileError = category?.files.some((file) => Boolean(file.error)) ?? false;
    const present = category !== undefined;
    return {
      name,
      present,
      fileCount: category?.file_count ?? 0,
      totalBytes: category?.total_bytes ?? 0,
      approxItemCount: category?.approx_item_count ?? null,
      itemCountExact: category?.item_count_exact ?? false,
      missingParts,
      hasWarning: !present || missingParts.length > 0 || hasFileError,
    };
  }

  private toErrorKey(error: unknown): InventoryErrorKey {
    if (error instanceof ApiError) {
      return error.status === 404 ? 'inventory.errors.notFound' : 'inventory.errors.generic';
    }
    // status 0 / sin ApiError -> sin conexión al API (CA-2 de spec 07).
    return 'inventory.errors.network';
  }
}

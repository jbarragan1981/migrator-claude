/**
 * Espejo de `packages/core/src/claude_export_md/domain/inventory.py` (pydantic,
 * `extra="allow"`). El cliente generado tipa `Inventory`/`CategoryInventory`/
 * `FileInventory` como `Record<string, any>` (openapi-typescript-codegen no
 * puede inferir un shape más preciso de un modelo con `extra="allow"` y sin
 * `additionalProperties: false`), así que estas interfaces documentan en un
 * único lugar los campos que la pantalla de Inventario realmente usa — no se
 * inventan campos que no existan en `domain/inventory.py` (encargo de la tarea).
 */

export interface FileInventoryView {
  path?: string | null;
  pattern?: string | null;
  count: number;
  bytes: number;
  part: number;
  root_type: string;
  top_keys?: string[];
  approx_item_count: number | null;
  item_count_exact: boolean;
  truncated: boolean;
  error?: string | null;
}

export interface CategoryInventoryView {
  name: string;
  parts: number[];
  files: FileInventoryView[];
  file_count: number;
  total_bytes: number;
  root_type: string;
  approx_item_count: number | null;
  item_count_exact: boolean;
}

export type InventoryFormatVersion = 'batched-manifest' | 'legacy-single-zip';

export interface InventoryView {
  root: string;
  format_version: InventoryFormatVersion;
  categories: Record<string, CategoryInventoryView>;
  missing_categories: string[];
  missing_parts: Record<string, number[]>;
  manifest_path?: string | null;
  warnings: string[];
}

/** Una fila ya combinada (categorías presentes + faltantes) para la tabla. */
export interface CategoryRow {
  name: string;
  present: boolean;
  fileCount: number;
  totalBytes: number;
  approxItemCount: number | null;
  itemCountExact: boolean;
  missingParts: number[];
  hasWarning: boolean;
}

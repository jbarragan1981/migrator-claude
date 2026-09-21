import { Pipe, PipeTransform } from '@angular/core';

const UNITS = ['B', 'KB', 'MB', 'GB', 'TB'] as const;

/**
 * Formatea bytes en una unidad legible (`1536` -> `1.5 KB`). Pipe puro, sin
 * Transloco: las unidades SI de tamaño de archivo (B/KB/MB…) son abreviaturas
 * estándar, no texto de interfaz a traducir (CA-3 de spec 07 cubre oraciones y
 * etiquetas de la UI, no unidades de medida).
 */
@Pipe({ name: 'bytesSize' })
export class BytesSizePipe implements PipeTransform {
  transform(bytes: number | null | undefined): string {
    if (bytes === null || bytes === undefined || Number.isNaN(bytes)) {
      return '—';
    }
    if (bytes <= 0) {
      return '0 B';
    }
    const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), UNITS.length - 1);
    const value = bytes / Math.pow(1024, exponent);
    const formatted = exponent === 0 ? value.toString() : value.toFixed(1);
    return `${formatted} ${UNITS[exponent]}`;
  }
}

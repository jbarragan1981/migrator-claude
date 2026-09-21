import { Injectable, signal } from '@angular/core';

const STORAGE_KEY = 'cem.currentExportId';

/**
 * Recuerda el `exportId` de la sesión activa (localStorage) para que la barra
 * de navegación (app.html) pueda enlazar a Inventario/Conversión/Resultado con
 * el id correcto en vez de a una ruta sin parámetro que el router no puede
 * resolver. Sin esto, salir de una de esas pantallas por el menú (en vez del
 * botón "Continuar"/"Ver resultado" de cada una, que sí llevan el id en la URL)
 * perdía el contexto y volvía a una pantalla vacía o al inicio.
 */
@Injectable({ providedIn: 'root' })
export class CurrentExportService {
  readonly exportId = signal<string | null>(this.readStorage());

  set(exportId: string): void {
    this.exportId.set(exportId);
    this.writeStorage(exportId);
  }

  clear(): void {
    this.exportId.set(null);
    this.writeStorage(null);
  }

  private readStorage(): string | null {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch {
      // localStorage puede no estar disponible (modo privado del navegador);
      // el signal sigue funcionando en memoria para la sesión actual.
      return null;
    }
  }

  private writeStorage(exportId: string | null): void {
    try {
      if (exportId) {
        localStorage.setItem(STORAGE_KEY, exportId);
      } else {
        localStorage.removeItem(STORAGE_KEY);
      }
    } catch {
      // ver comentario de `readStorage`.
    }
  }
}

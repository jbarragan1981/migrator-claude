import { Injectable } from '@angular/core';

/**
 * Superficie mínima de `EventSource` que necesita `JobProgressService`. Existe
 * para poder sustituirla en tests (`EventSource` nativo no está disponible en el
 * entorno de test de Vitest/jsdom, y aunque lo estuviera no conviene depender de
 * timing de red real en un spec) sin tocar el código de producción.
 */
export interface EventSourceLike {
  addEventListener(type: string, listener: (event: MessageEvent) => void): void;
  close(): void;
}

/**
 * Envuelve la construcción de `EventSource` nativo (CLAUDE.md §7 / spec 07: "SSE de
 * progreso con `EventSource` envuelto en un servicio que expone una signal").
 * `providedIn: 'root'` a propósito: los tests de `features/jobs` sobreescriben este
 * provider con un doble de prueba en `TestBed`, en vez de mockear `EventSource` global.
 */
@Injectable({ providedIn: 'root' })
export class EventSourceFactory {
  create(url: string): EventSourceLike {
    // El cast es necesario porque el `EventSourceLike` declarado arriba tipa todos
    // los listeners como `(event: MessageEvent) => void` por simplicidad (los tres
    // eventos que nos interesan — `progress`/`done`/`error` del servidor — llegan
    // como `MessageEvent`; el evento `error` de fallo de conexión nativo llega como
    // `Event` simple, sin `data`, pero accederla da `undefined`, no un error).
    return new EventSource(url) as unknown as EventSourceLike;
  }
}

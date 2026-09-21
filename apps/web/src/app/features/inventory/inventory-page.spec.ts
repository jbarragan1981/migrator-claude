import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';

import { InventoryPageComponent } from './inventory-page';
import type { InventoryView } from './inventory.models';

/**
 * El cliente generado resuelve las cabeceras con `forkJoin` sobre `Promise`s
 * (`core/api/core/request.ts::getHeaders`), así que el GET real llega al
 * backend de test unos microtasks después de que el `effect()` de la página
 * llama a `load()`. Un `setTimeout(0)` deja drenar toda la cola de microtasks
 * antes de buscar la request.
 */
function flushAsync(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

// Mismo mecanismo que `core/i18n/i18n-parity.spec.ts` (ver upload-page.spec.ts
// para la nota sobre por qué se inlinea en vez de factorizarse).
function loadTranslations(lang: 'es' | 'en'): Record<string, unknown> {
  const here = dirname(fileURLToPath(import.meta.url));
  const path = join(here, '..', '..', '..', '..', 'public', 'assets', 'i18n', `${lang}.json`);
  return JSON.parse(readFileSync(path, 'utf-8')) as Record<string, unknown>;
}

const FIXTURE_INVENTORY: InventoryView = {
  root: 'mi-export.zip',
  format_version: 'batched-manifest',
  categories: {
    conversations: {
      name: 'conversations',
      parts: [0],
      files: [
        {
          path: 'conversations-000/conversations.json',
          count: 1,
          bytes: 2048,
          part: 0,
          root_type: 'array',
          approx_item_count: 42,
          item_count_exact: false,
          truncated: false,
        },
      ],
      file_count: 1,
      total_bytes: 2048,
      root_type: 'array',
      approx_item_count: 42,
      item_count_exact: false,
    },
    memories: {
      name: 'memories',
      parts: [0],
      files: [],
      file_count: 5,
      total_bytes: 512,
      root_type: 'markdown',
      approx_item_count: 5,
      item_count_exact: true,
    },
  },
  missing_categories: ['frames'],
  missing_parts: { memories: [1] },
  manifest_path: 'member-manifest-000.json',
  warnings: ['light_metadata-000 no trae perfil de cuenta'],
};

describe('InventoryPageComponent', () => {
  let httpMock: HttpTestingController;

  async function createComponent(exportId = 'export-123') {
    const fixture = TestBed.createComponent(InventoryPageComponent);
    fixture.componentRef.setInput('exportId', exportId);
    fixture.detectChanges();
    // El `effect()` que dispara la carga inicial (inventory-page.ts) corre en un
    // microtask del scheduler de reactividad, y el propio cliente HTTP generado
    // resuelve sus cabeceras de forma asíncrona (ver nota de `flushAsync`).
    await fixture.whenStable();
    await flushAsync();
    return fixture;
  }

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [
        InventoryPageComponent,
        TranslocoTestingModule.forRoot({
          langs: { es: loadTranslations('es'), en: loadTranslations('en') },
          translocoConfig: { availableLangs: ['es', 'en'], defaultLang: 'es' },
          preloadLangs: true,
        }),
      ],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('carga el inventario y muestra la tabla con los datos de la respuesta', async () => {
    const fixture = await createComponent();

    const req = httpMock.expectOne('/api/v1/exports/export-123/inventory');
    expect(req.request.method).toBe('GET');
    req.flush(FIXTURE_INVENTORY);
    fixture.detectChanges();

    const component = fixture.componentInstance;
    expect(component.status()).toBe('success');

    const rows = component.rows();
    expect(rows.map((row) => row.name).sort()).toEqual(['conversations', 'frames', 'memories']);

    const conversations = rows.find((row) => row.name === 'conversations');
    expect(conversations?.fileCount).toBe(1);
    expect(conversations?.approxItemCount).toBe(42);
    expect(conversations?.hasWarning).toBe(false);

    const memories = rows.find((row) => row.name === 'memories');
    expect(memories?.hasWarning).toBe(true); // falta la parte 1

    const frames = rows.find((row) => row.name === 'frames');
    expect(frames?.present).toBe(false);
    expect(frames?.hasWarning).toBe(true);

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('conversations');
    expect(compiled.textContent).toContain('memories');
    expect(compiled.textContent).toContain('Categorías faltantes');
    expect(compiled.textContent).toContain('frames');
    expect(compiled.textContent).toContain('light_metadata-000 no trae perfil de cuenta');
  });

  it('sin conexión al API muestra un error traducido y reintenta al hacer clic (CA-2 de spec 07)', async () => {
    const fixture = await createComponent();

    const firstRequest = httpMock.expectOne('/api/v1/exports/export-123/inventory');
    firstRequest.flush({ detail: 'not found' }, { status: 404, statusText: 'Not Found' });
    fixture.detectChanges();

    const component = fixture.componentInstance;
    expect(component.status()).toBe('error');

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain(
      'No se encontró este export. Puede haberse borrado o el enlace es incorrecto.',
    );

    const retryButton = Array.from(compiled.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('Reintentar'),
    );
    expect(retryButton).toBeTruthy();
    retryButton?.dispatchEvent(new Event('click', { bubbles: true }));
    fixture.detectChanges();
    await flushAsync();

    const secondRequest = httpMock.expectOne('/api/v1/exports/export-123/inventory');
    secondRequest.flush(FIXTURE_INVENTORY);
    fixture.detectChanges();

    expect(component.status()).toBe('success');
  });
});

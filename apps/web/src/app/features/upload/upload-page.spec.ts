import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';

import { UploadPageComponent } from './upload-page';

// Mismo mecanismo que `core/i18n/i18n-parity.spec.ts`: se lee el JSON real servido
// como asset en vez de duplicar a mano un subconjunto de claves que podría
// desincronizarse del contenido real. Se inlinea (no se factoriza a un módulo
// compartido) porque el bundler de test reescribe `import.meta.url` de forma
// distinta cuando el código vive en un módulo importado en vez del propio spec.
function loadTranslations(lang: 'es' | 'en'): Record<string, unknown> {
  const here = dirname(fileURLToPath(import.meta.url));
  const path = join(here, '..', '..', '..', '..', 'public', 'assets', 'i18n', `${lang}.json`);
  return JSON.parse(readFileSync(path, 'utf-8')) as Record<string, unknown>;
}

function fakeFile(name = 'conversations-000.zip'): File {
  return new File(['contenido'], name, { type: 'application/zip' });
}

/**
 * El cliente generado resuelve las cabeceras con `forkJoin` sobre `Promise`s
 * (`core/api/core/request.ts::getHeaders`), así que el POST real llega al
 * backend de test unos microtasks después de llamar a `.subscribe()`, no en el
 * mismo turno de ejecución. Un `setTimeout(0)` deja drenar toda la cola de
 * microtasks (más profunda que la de Angular) antes de buscar la request.
 */
function flushAsync(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

describe('UploadPageComponent', () => {
  let navigateSpy: ReturnType<typeof vi.fn>;
  let httpMock: HttpTestingController;

  function createComponent() {
    const fixture = TestBed.createComponent(UploadPageComponent);
    fixture.detectChanges();
    return fixture;
  }

  beforeEach(() => {
    navigateSpy = vi.fn().mockResolvedValue(true);
    TestBed.configureTestingModule({
      imports: [
        UploadPageComponent,
        TranslocoTestingModule.forRoot({
          langs: { es: loadTranslations('es'), en: loadTranslations('en') },
          translocoConfig: { availableLangs: ['es', 'en'], defaultLang: 'es' },
          preloadLangs: true,
        }),
      ],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: Router, useValue: { navigate: navigateSpy } },
      ],
    });
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('sube los archivos elegidos (multipart) y navega al inventario del export creado', async () => {
    const fixture = createComponent();
    const component = fixture.componentInstance;

    component.onFilesSelected([fakeFile()]);
    fixture.detectChanges();
    expect(component.canSubmit()).toBe(true);

    const submitPromise = component.submit();
    fixture.detectChanges();
    expect(component.status()).toBe('uploading');

    await flushAsync();
    const req = httpMock.expectOne('/api/v1/exports');
    expect(req.request.method).toBe('POST');
    const body = req.request.body as FormData;
    expect(body.getAll('file')).toHaveLength(1);

    req.flush({ export_id: 'export-123' });
    await submitPromise;
    fixture.detectChanges();

    expect(component.status()).toBe('success');
    expect(navigateSpy).toHaveBeenCalledWith(['/inventory', 'export-123']);
  });

  it('sin conexión al API muestra un error traducido y permite reintentar (CA-2 de spec 07)', async () => {
    const fixture = createComponent();
    const component = fixture.componentInstance;

    component.onFilesSelected([fakeFile()]);
    fixture.detectChanges();

    const submitPromise = component.submit();
    await flushAsync();
    const req = httpMock.expectOne('/api/v1/exports');
    req.error(new ProgressEvent('error'));

    await submitPromise;
    fixture.detectChanges();

    expect(component.status()).toBe('error');
    expect(navigateSpy).not.toHaveBeenCalled();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain(
      'No se pudo conectar con la API. Revisá que esté corriendo y volvé a intentar.',
    );

    const retryButton = Array.from(compiled.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('Reintentar'),
    );
    expect(retryButton).toBeTruthy();
    retryButton?.dispatchEvent(new Event('click', { bubbles: true }));
    fixture.detectChanges();

    expect(component.status()).toBe('idle');
    expect(component.errorKey()).toBeNull();
  });

  it('un 413 del servidor se traduce como "archivo demasiado grande", nunca el mensaje crudo', async () => {
    const fixture = createComponent();
    const component = fixture.componentInstance;

    component.onFilesSelected([fakeFile()]);
    fixture.detectChanges();

    const submitPromise = component.submit();
    await flushAsync();
    const req = httpMock.expectOne('/api/v1/exports');
    req.flush(
      { detail: 'payload too large, some internal backend detail' },
      { status: 413, statusText: 'Payload Too Large' },
    );

    await submitPromise;
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('El archivo supera el tamaño máximo permitido por el servidor.');
    expect(compiled.textContent).not.toContain('payload too large, some internal backend detail');
  });
});

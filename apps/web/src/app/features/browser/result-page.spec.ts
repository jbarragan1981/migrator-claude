import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';

import { ResultPageComponent } from './result-page';

function loadTranslations(lang: 'es' | 'en'): Record<string, unknown> {
  const here = dirname(fileURLToPath(import.meta.url));
  const path = join(here, '..', '..', '..', '..', 'public', 'assets', 'i18n', `${lang}.json`);
  return JSON.parse(readFileSync(path, 'utf-8')) as Record<string, unknown>;
}

function flushAsync(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

const FIXTURE_TREE = {
  entries: [
    { path: 'README.md', kind: 'file', size: 42 },
    { path: 'memories', kind: 'dir', size: null },
    { path: 'memories/profile.md', kind: 'file', size: 128 },
  ],
};

describe('ResultPageComponent', () => {
  let httpMock: HttpTestingController;

  async function createComponent(exportId = 'export-123') {
    const fixture = TestBed.createComponent(ResultPageComponent);
    fixture.componentRef.setInput('exportId', exportId);
    fixture.detectChanges();
    await fixture.whenStable();
    await flushAsync();
    return fixture;
  }

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [
        ResultPageComponent,
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

  it('carga el árbol, muestra el contenido de un archivo elegido y arma el link de descarga', async () => {
    const fixture = await createComponent();

    const treeReq = httpMock.expectOne('/api/v1/exports/export-123/output/tree');
    expect(treeReq.request.method).toBe('GET');
    treeReq.flush(FIXTURE_TREE);
    fixture.detectChanges();

    const component = fixture.componentInstance;
    expect(component.treeStatus()).toBe('success');
    expect(component.rows().map((row) => row.node.name)).toEqual(['memories', 'profile.md', 'README.md']);
    expect(component.downloadHref()).toBe('/api/v1/exports/export-123/download');

    let compiled = fixture.nativeElement as HTMLElement;
    const downloadLink = compiled.querySelector('a[href="/api/v1/exports/export-123/download"]');
    expect(downloadLink).toBeTruthy();

    component.selectFile('memories/profile.md');
    fixture.detectChanges();
    await flushAsync();

    const fileReq = httpMock.expectOne(
      (req) => req.url === '/api/v1/exports/export-123/output/file' && req.params.get('path') === 'memories/profile.md',
    );
    expect(fileReq.request.method).toBe('GET');
    fileReq.flush('# Perfil\n\nContenido de prueba.');
    fixture.detectChanges();

    expect(component.fileStatus()).toBe('success');
    compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('Contenido de prueba.');
  });

  it('sin conexión al API al cargar el árbol muestra error traducido y reintenta (CA-2)', async () => {
    const fixture = await createComponent();

    const firstReq = httpMock.expectOne('/api/v1/exports/export-123/output/tree');
    firstReq.flush({ detail: 'not found' }, { status: 404, statusText: 'Not Found' });
    fixture.detectChanges();

    const component = fixture.componentInstance;
    expect(component.treeStatus()).toBe('error');
    let compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('Este export todavía no fue convertido, o no existe.');

    const retryButton = Array.from(compiled.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('Reintentar'),
    );
    expect(retryButton).toBeTruthy();
    retryButton?.dispatchEvent(new Event('click', { bubbles: true }));
    fixture.detectChanges();
    await flushAsync();

    const secondReq = httpMock.expectOne('/api/v1/exports/export-123/output/tree');
    secondReq.flush(FIXTURE_TREE);
    fixture.detectChanges();

    expect(component.treeStatus()).toBe('success');
    compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).not.toContain('Este export todavía no fue convertido');
  });

  it('filtra el árbol por nombre con el buscador', async () => {
    const fixture = await createComponent();

    const treeReq = httpMock.expectOne('/api/v1/exports/export-123/output/tree');
    treeReq.flush(FIXTURE_TREE);
    fixture.detectChanges();

    const component = fixture.componentInstance;
    component.onSearchInputEvent({ target: { value: 'README' } } as unknown as Event);
    fixture.detectChanges();

    expect(component.rows().map((row) => row.node.name)).toEqual(['README.md']);
  });

  it('un archivo con extensión binaria conocida se marca como no previsualizable sin pedirlo al servidor', async () => {
    const fixture = await createComponent();

    const treeReq = httpMock.expectOne('/api/v1/exports/export-123/output/tree');
    treeReq.flush({ entries: [...FIXTURE_TREE.entries, { path: 'assets/logo.png', kind: 'file', size: 999 }] });
    fixture.detectChanges();

    const component = fixture.componentInstance;
    component.selectFile('assets/logo.png');
    fixture.detectChanges();
    await flushAsync();

    httpMock.expectNone((req) => req.url.includes('/output/file'));
    expect(component.fileStatus()).toBe('not-previewable');
  });
});

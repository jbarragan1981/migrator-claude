import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';

import { ConvertPageComponent } from './convert-page';
import { EventSourceFactory, type EventSourceLike } from './event-source-factory';

/**
 * Doble de prueba de `EventSourceLike`: `EventSource` nativo no existe en el
 * entorno jsdom de Vitest, así que `JobProgressService` recibe este doble en vez
 * del real (`EventSourceFactory` provisto de nuevo en `TestBed`). Permite disparar
 * a mano los eventos `progress`/`done`/`error` que mandaría el servidor.
 */
class FakeEventSource implements EventSourceLike {
  readonly url: string;
  closed = false;
  private readonly listeners = new Map<string, ((event: MessageEvent) => void)[]>();

  constructor(url: string) {
    this.url = url;
  }

  addEventListener(type: string, listener: (event: MessageEvent) => void): void {
    const current = this.listeners.get(type) ?? [];
    current.push(listener);
    this.listeners.set(type, current);
  }

  close(): void {
    this.closed = true;
  }

  /** `data` ausente simula el evento nativo de corte de conexión (sin payload). */
  emit(type: string, data?: unknown): void {
    const event = { data: data === undefined ? undefined : JSON.stringify(data) } as MessageEvent;
    for (const listener of this.listeners.get(type) ?? []) {
      listener(event);
    }
  }
}

class FakeEventSourceFactory extends EventSourceFactory {
  readonly instances: FakeEventSource[] = [];

  override create(url: string): EventSourceLike {
    const source = new FakeEventSource(url);
    this.instances.push(source);
    return source;
  }
}

function loadTranslations(lang: 'es' | 'en'): Record<string, unknown> {
  const here = dirname(fileURLToPath(import.meta.url));
  const path = join(here, '..', '..', '..', '..', 'public', 'assets', 'i18n', `${lang}.json`);
  return JSON.parse(readFileSync(path, 'utf-8')) as Record<string, unknown>;
}

function flushAsync(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

describe('ConvertPageComponent', () => {
  let httpMock: HttpTestingController;
  let fakeEventSourceFactory: FakeEventSourceFactory;
  let navigateSpy: ReturnType<typeof vi.fn>;

  async function createComponent(exportId: string | null = 'export-123') {
    const fixture = TestBed.createComponent(ConvertPageComponent);
    if (exportId !== null) {
      fixture.componentRef.setInput('exportId', exportId);
    }
    fixture.detectChanges();
    await fixture.whenStable();
    await flushAsync();
    return fixture;
  }

  beforeEach(() => {
    fakeEventSourceFactory = new FakeEventSourceFactory();
    TestBed.configureTestingModule({
      imports: [
        ConvertPageComponent,
        TranslocoTestingModule.forRoot({
          langs: { es: loadTranslations('es'), en: loadTranslations('en') },
          translocoConfig: { availableLangs: ['es', 'en'], defaultLang: 'es' },
          preloadLangs: true,
        }),
      ],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        // `provideRouter([])` real (no un doble a mano): `convert-page.html` usa
        // `routerLink` de forma declarativa (estados "no-export"/"convert-error"),
        // que necesita `ActivatedRoute` disponible por inyección — un `Router`
        // completamente falso rompe esa resolución (NG0201).
        provideRouter([]),
        { provide: EventSourceFactory, useValue: fakeEventSourceFactory },
      ],
    });
    httpMock = TestBed.inject(HttpTestingController);
    navigateSpy = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('lanza la conversión, sigue el progreso por SSE y navega al resultado (flujo exitoso)', async () => {
    const fixture = await createComponent();

    const convertReq = httpMock.expectOne('/api/v1/exports/export-123/convert');
    expect(convertReq.request.method).toBe('POST');
    convertReq.flush({ job_id: 'job-abc' });
    await flushAsync();
    fixture.detectChanges();

    expect(fakeEventSourceFactory.instances).toHaveLength(1);
    const source = fakeEventSourceFactory.instances[0];
    expect(source.url).toBe('/api/v1/jobs/job-abc/events');

    source.emit('progress', { category: 'memories', done: 1 });
    fixture.detectChanges();
    expect(fixture.componentInstance.events()).toEqual([{ category: 'memories', done: 1 }]);
    let compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('memories');

    source.emit('done', { counts: { memories: 3 }, errors: 0, warnings: 1 });
    fixture.detectChanges();

    expect(source.closed).toBe(true);
    expect(fixture.componentInstance.phase()).toBe('done');
    compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('memories: 3');
    expect(compiled.textContent).toContain('Advertencias: 1');

    const viewResultButton = Array.from(compiled.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('Ver resultado'),
    );
    expect(viewResultButton).toBeTruthy();
    viewResultButton?.dispatchEvent(new Event('click', { bubbles: true }));
    fixture.detectChanges();

    expect(navigateSpy).toHaveBeenCalledWith(['/result', 'export-123']);
  });

  it('un 409 al iniciar la conversión muestra un error traducido y reintenta al hacer clic (CA-2)', async () => {
    const fixture = await createComponent();

    const firstReq = httpMock.expectOne('/api/v1/exports/export-123/convert');
    firstReq.flush({ detail: 'ya hay una conversion en curso' }, { status: 409, statusText: 'Conflict' });
    fixture.detectChanges();

    expect(fixture.componentInstance.convertStatus()).toBe('error');
    let compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain(
      'Ya hay una conversión en curso para este export. Esperá a que termine e intentá de nuevo.',
    );

    const retryButton = Array.from(compiled.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('Reintentar'),
    );
    expect(retryButton).toBeTruthy();
    retryButton?.dispatchEvent(new Event('click', { bubbles: true }));
    fixture.detectChanges();
    await flushAsync();

    const secondReq = httpMock.expectOne('/api/v1/exports/export-123/convert');
    secondReq.flush({ job_id: 'job-def' });
    await flushAsync();
    fixture.detectChanges();

    expect(fixture.componentInstance.convertStatus()).toBe('started');
    compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).not.toContain('Ya hay una conversión en curso');
  });

  it('un corte de conexión SSE consulta GET /jobs/{id} antes de mostrar error (CA-2, no asume que el job falló)', async () => {
    const fixture = await createComponent();

    const convertReq = httpMock.expectOne('/api/v1/exports/export-123/convert');
    convertReq.flush({ job_id: 'job-abc' });
    await flushAsync();
    fixture.detectChanges();

    const source = fakeEventSourceFactory.instances[0];
    // Evento nativo de corte de conexión: sin `data`, a diferencia del `event: error`
    // que manda el propio servidor con un `reason`.
    source.emit('error');
    fixture.detectChanges();
    await flushAsync();

    const statusReq = httpMock.expectOne('/api/v1/jobs/job-abc');
    expect(statusReq.request.method).toBe('GET');
    statusReq.flush({
      status: 'done',
      progress: [{ category: 'conversations', done: 5 }],
      counts: { conversations: 5 },
      errors: 0,
      warnings: 0,
    });
    fixture.detectChanges();

    expect(fixture.componentInstance.phase()).toBe('done');
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('conversations: 5');
  });

  it('sin exportId (visita directa a /convert) muestra un estado vacío en vez de romper (CA-2)', async () => {
    const fixture = await createComponent(null);

    httpMock.expectNone((req) => req.url.includes('/convert'));
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain(
      'No hay un export seleccionado. Volvé al inicio para subir o elegir uno.',
    );
  });
});

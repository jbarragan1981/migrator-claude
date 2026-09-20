import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';

import { App } from './app';
import { routes } from './app.routes';

// Subconjunto mínimo de assets/i18n/{es,en}.json: solo las claves que este smoke
// test necesita. El test de paridad real de TODAS las claves (CA-3 de spec 07) se
// agrega junto con la primera feature real, leyendo los JSON completos.
const ES = { app: { title: 'claude-export-md' }, nav: { upload: 'Inicio', settings: 'Ajustes' } };
const EN = { app: { title: 'claude-export-md' }, nav: { upload: 'Home', settings: 'Settings' } };

describe('App', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [
        App,
        TranslocoTestingModule.forRoot({
          langs: { es: ES, en: EN },
          translocoConfig: { availableLangs: ['es', 'en'], defaultLang: 'es' },
          preloadLangs: true,
        }),
      ],
      providers: [provideRouter(routes)],
    }).compileComponents();
  });

  it('should create the app', () => {
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    expect(app).toBeTruthy();
  });

  it('renders the nav with the Spanish title by default (CLAUDE.md §7: es por defecto)', async () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('claude-export-md');
    expect(compiled.textContent).toContain('Inicio');
    expect(compiled.textContent).toContain('Ajustes');
  });
});

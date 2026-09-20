import { provideHttpClient } from '@angular/common/http';
import { ApplicationConfig, isDevMode, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideAnimationsAsync } from '@angular/platform-browser/animations/async';
import { provideRouter } from '@angular/router';
import { provideTransloco } from '@jsverse/transloco';

import { routes } from './app.routes';
import { TranslocoHttpLoader } from './core/i18n/transloco-http-loader';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes),
    provideHttpClient(),
    // Ripple/overlay de Angular Material necesitan el motor de animaciones; la variante
    // "Async" lo carga en un chunk aparte para no sumarlo al bundle inicial (CA-6).
    provideAnimationsAsync(),
    // Español por defecto (CLAUDE.md §7); `availableLangs` es la lista completa que
    // ofrecerá la pantalla de Ajustes (spec 07, pantalla 5) para cambiar de idioma.
    provideTransloco({
      config: {
        availableLangs: ['es', 'en'],
        defaultLang: 'es',
        fallbackLang: 'es',
        reRenderOnLangChange: true,
        prodMode: !isDevMode(),
      },
      loader: TranslocoHttpLoader,
    }),
  ],
};

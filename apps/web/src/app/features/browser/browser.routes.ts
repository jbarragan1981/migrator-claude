import { Routes } from '@angular/router';

export const BROWSER_ROUTES: Routes = [
  {
    // `exportId` llega como `input.required<string>()` gracias a
    // `withComponentInputBinding()` (ver app.config.ts), mismo mecanismo que
    // `features/inventory`.
    path: ':exportId',
    loadComponent: () => import('./result-page').then((m) => m.ResultPageComponent),
  },
  {
    // La barra de navegación (`app.html`) tiene un link fijo a `/result` sin id;
    // visitarlo directo no matchea `:exportId` (necesita al menos un segmento) y
    // sin esta ruta el router quedaría sin ninguna coincidencia (CA-2: nunca una
    // pantalla rota/en blanco).
    path: '',
    redirectTo: '/',
    pathMatch: 'full',
  },
];

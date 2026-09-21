import { Routes } from '@angular/router';

/**
 * Rutas raíz de spec 07: cada pantalla es una feature cargada perezosamente
 * (`loadChildren`) para que el bundle inicial no crezca con código que todavía no
 * se visitó (CA-6, <600 kB). Los componentes reales de cada feature llegan en las
 * próximas rondas; hoy son placeholders "en construcción" (ver shared/coming-soon.ts).
 */
export const routes: Routes = [
  {
    path: '',
    loadChildren: () => import('./features/upload/upload.routes').then((m) => m.UPLOAD_ROUTES),
  },
  {
    path: 'inventory',
    loadChildren: () =>
      import('./features/inventory/inventory.routes').then((m) => m.INVENTORY_ROUTES),
  },
  {
    path: 'convert',
    loadChildren: () => import('./features/jobs/jobs.routes').then((m) => m.JOBS_ROUTES),
  },
  {
    path: 'result',
    loadChildren: () => import('./features/browser/browser.routes').then((m) => m.BROWSER_ROUTES),
  },
  {
    path: 'settings',
    loadChildren: () =>
      import('./features/settings/settings.routes').then((m) => m.SETTINGS_ROUTES),
  },
  {
    path: '**',
    redirectTo: '',
  },
];

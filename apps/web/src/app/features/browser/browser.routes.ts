import { Routes } from '@angular/router';

export const BROWSER_ROUTES: Routes = [
  {
    path: '',
    loadComponent: () => import('./result-page').then((m) => m.ResultPageComponent),
  },
];

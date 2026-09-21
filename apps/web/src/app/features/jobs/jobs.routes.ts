import { Routes } from '@angular/router';

export const JOBS_ROUTES: Routes = [
  {
    path: '',
    loadComponent: () => import('./convert-page').then((m) => m.ConvertPageComponent),
  },
];

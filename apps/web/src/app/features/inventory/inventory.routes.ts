import { Routes } from '@angular/router';

export const INVENTORY_ROUTES: Routes = [
  {
    // `exportId` llega como `input.required<string>()` gracias a
    // `withComponentInputBinding()` (ver app.config.ts).
    path: ':exportId',
    loadComponent: () => import('./inventory-page').then((m) => m.InventoryPageComponent),
  },
];

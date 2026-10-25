import { Routes } from '@angular/router';

import { customerGuard, ownerGuard } from './core/guards';

export const routes: Routes = [
  {
    path: '',
    pathMatch: 'full',
    loadComponent: () => import('./landing').then((m) => m.Landing),
    title: 'SlotSaver',
  },
  {
    path: 'customer',
    canActivate: [customerGuard],
    loadComponent: () => import('./customer/customer-page').then((m) => m.CustomerPage),
    title: 'SlotSaver · Book a repair',
  },
  {
    path: 'owner',
    canActivate: [ownerGuard],
    loadComponent: () => import('./owner/owner-page').then((m) => m.OwnerPage),
    title: 'SlotSaver · Owner workspace',
  },
  { path: '**', redirectTo: '' },
];

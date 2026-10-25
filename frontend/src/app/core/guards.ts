import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { SessionStore } from './session.store';

async function ensure(session: SessionStore): Promise<void> {
  if (!session.ready()) {
    await session.bootstrap();
  }
}

export const customerGuard: CanActivateFn = async () => {
  const session = inject(SessionStore);
  const router = inject(Router);
  await ensure(session);
  if (session.isCustomer()) return true;
  return session.isOwner() ? router.createUrlTree(['/owner']) : router.createUrlTree(['/']);
};

export const ownerGuard: CanActivateFn = async () => {
  const session = inject(SessionStore);
  const router = inject(Router);
  await ensure(session);
  if (session.isOwner()) return true;
  return session.isCustomer() ? router.createUrlTree(['/customer']) : router.createUrlTree(['/']);
};

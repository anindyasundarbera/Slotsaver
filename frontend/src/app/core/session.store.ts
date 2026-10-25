import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiFailure, ApiService } from './api.service';
import { AppConfig, Role } from './models';

export interface SessionUser {
  id: string;
  email: string;
  display_name: string;
  role: string;
}

@Injectable({ providedIn: 'root' })
export class SessionStore {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);

  readonly user = signal<SessionUser | null>(null);
  readonly config = signal<AppConfig | null>(null);
  readonly ready = signal(false);
  readonly authError = signal<string | null>(null);

  readonly isOwner = computed(() => this.user()?.role === 'owner');
  readonly isCustomer = computed(() => this.user()?.role === 'customer');
  readonly displayName = computed(() => this.user()?.display_name ?? '');
  readonly initials = computed(() => {
    const name = this.user()?.display_name ?? '';
    return name
      .split(' ')
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]!.toUpperCase())
      .join('');
  });
  readonly role = computed<Role | null>(() => {
    const value = this.user()?.role;
    return value === 'owner' || value === 'customer' ? value : null;
  });
  readonly isSimulated = computed(() => this.config()?.paypal_mode === 'simulated');

  async bootstrap(): Promise<void> {
    try {
      if (!this.config()) {
        this.config.set(await firstValueFrom(this.api.config()));
      }
    } catch {
      // Config failing means the API is down; the shell shows a banner.
    }
    try {
      this.user.set(await firstValueFrom(this.api.me()));
    } catch (error) {
      // 401 simply means signed out; anything else is worth surfacing.
      if (error instanceof ApiFailure && error.status !== 401) {
        this.authError.set(error.message);
      }
      this.user.set(null);
    } finally {
      this.ready.set(true);
    }
  }

  async signIn(email: string): Promise<void> {
    this.authError.set(null);
    try {
      this.user.set(await firstValueFrom(this.api.login(email)));
      const target = this.user()?.role === 'owner' ? '/owner' : '/customer';
      await this.router.navigateByUrl(target);
    } catch (error) {
      const message = error instanceof ApiFailure ? error.message : 'Sign-in failed.';
      this.authError.set(message);
      throw error;
    }
  }

  async signOut(): Promise<void> {
    try {
      await firstValueFrom(this.api.logout());
    } catch {
      // Even if the call fails, drop local state; the server session will expire.
    }
    this.user.set(null);
    await this.router.navigateByUrl('/');
  }
}

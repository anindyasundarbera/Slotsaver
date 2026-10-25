import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { Router } from '@angular/router';

import { present, PresentedError } from './core/errors';
import { SessionStore } from './core/session.store';
import { DemoUser } from './core/models';
import { ErrorLine } from './shared/error-line';
import { Spinner } from './shared/spinner';

@Component({
  selector: 'ss-landing',
  imports: [ErrorLine, Spinner],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="grid-2">
      <section class="hero">
        <span class="eyebrow">SlotSaver · appliance repair POC</span>
        <h1>Describe the job. Hold a real slot. Pay to confirm.</h1>
        <p class="lead">
          A customer asks in plain language, gets validated appointment options from the
          backend, holds one, pays through PayPal Sandbox, and gets a persistent booking.
          When plans change, the owner can flag a technician and only the customer can
          approve the replacement.
        </p>

        <div class="stack-sm">
          <h2>Try the demo request</h2>
          <p class="small muted">
            “I need washing-machine service tomorrow after 4 PM. My budget is $80, and it
            must finish before 6.”
          </p>
        </div>

        <dl class="grid-3 small">
          <div>
            <dt class="eyebrow">Money</dt>
            <dd class="muted">Integer cents, USD, never floating point.</dd>
          </div>
          <div>
            <dt class="eyebrow">Slots</dt>
            <dd class="muted">A database constraint decides, not a check-then-insert.</dd>
          </div>
          <div>
            <dt class="eyebrow">AI</dt>
            <dd class="muted">Reads availability only. It cannot pay or confirm.</dd>
          </div>
        </dl>

        @if (session.config(); as config) {
          <p class="small muted">
            Demo business date <strong>{{ config.demo_date }}</strong> · hold
            {{ config.hold_ttl_minutes }} min · {{ config.timezone }}
          </p>
        }
      </section>

      <section class="card">
        <div class="card-header">
          <h2>Choose a demo account</h2>
        </div>
        <p class="small muted" style="margin-bottom: 16px">
          These are synthetic identities. The server decides what each one may do — a
          browser toggle cannot grant a role.
        </p>

        @if (session.authError(); as message) {
          <ss-error-line [error]="authError() ?? { message: message, correlationId: '', code: 'AUTH' }" />
        }
        @if (error(); as err) {
          <ss-error-line [error]="err" />
        }

        @if (session.config(); as config) {
          <div class="account-list">
            @for (user of config.demo_users; track user.email) {
              <button
                type="button"
                class="account-btn"
                [disabled]="busy() !== null"
                (click)="signIn(user)"
              >
                <span class="avatar" aria-hidden="true">{{ initials(user) }}</span>
                <span class="stack-sm" style="gap: 0">
                  <strong>{{ user.display_name }}</strong>
                  <span class="small muted">{{ user.email }}</span>
                </span>
                <span class="topbar-spacer"></span>
                @if (busy() === user.email) {
                  <ss-spinner label="Signing in…" />
                } @else {
                  <span class="tag">{{ user.role }}</span>
                }
              </button>
            }
          </div>
        } @else {
          <ss-spinner label="Loading demo accounts…" />
        }

        <div class="notice notice-info" style="margin-top: 20px">
          <span class="notice-icon" aria-hidden="true">i</span>
          <span>
            Offline rehearsal mode uses a labelled simulated payment provider. Set
            <span class="mono">PAYPAL_MODE=sandbox</span> with real credentials for the
            connected journey. The mode is never switched silently.
          </span>
        </div>
      </section>
    </div>
  `,
})
export class Landing {
  protected readonly session = inject(SessionStore);
  private readonly router = inject(Router);

  protected readonly busy = signal<string | null>(null);
  protected readonly error = signal<PresentedError | null>(null);

  protected initials(user: DemoUser): string {
    return user.display_name
      .split(' ')
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]!.toUpperCase())
      .join('');
  }

  protected authError(): PresentedError | null {
    const message = this.session.authError();
    return message ? { message, correlationId: '', code: 'AUTH' } : null;
  }

  protected async signIn(user: DemoUser): Promise<void> {
    this.busy.set(user.email);
    this.error.set(null);
    try {
      await this.session.signIn(user.email);
    } catch (err) {
      this.error.set(present(err));
    } finally {
      this.busy.set(null);
    }
  }
}

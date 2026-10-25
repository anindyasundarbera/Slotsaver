import { ChangeDetectionStrategy, Component, computed, inject, input, output, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../core/api.service';
import { present, PresentedError } from '../core/errors';
import { formatMoney } from '../core/format';
import { BookingInfo } from '../core/models';
import { ErrorLine } from '../shared/error-line';
import { StatusChip } from '../shared/status-chip';

@Component({
  selector: 'ss-bookings-panel',
  imports: [ErrorLine, StatusChip],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="card" aria-labelledby="my-bookings">
      <div class="card-header">
        <h2 id="my-bookings">My bookings</h2>
        <button type="button" class="btn btn-secondary btn-sm" [disabled]="busy()" (click)="refresh.emit()">
          @if (busy()) { <span class="spinner" aria-hidden="true"></span> }
          Refresh
        </button>
      </div>

      @if (error(); as err) {
        <ss-error-line [error]="err" />
      }

      @if (!bookings().length) {
        <p class="muted small">No bookings yet. Hold a slot and pay to confirm one.</p>
      } @else {
        <div class="stack">
          @for (booking of sorted(); track booking.id) {
            <article class="card card-tight" style="box-shadow: none">
              <div class="spread">
                <div class="row-tight">
                  <ss-status-chip [status]="booking.status" [labelOverride]="booking.status_label" />
                  <strong class="mono">{{ booking.reference }}</strong>
                  @if (booking.needs_attention) {
                    <span class="tag" style="color:#991b1b;border-color:#fca5a5;background:#fee2e2">
                      needs attention
                    </span>
                  }
                </div>
                <span class="small nowrap">{{ money(booking.price_cents, booking.currency) }}</span>
              </div>

              <div class="row small muted" style="margin-top: 6px">
                <span>{{ booking.service_name }}</span>
                <span aria-hidden="true">·</span>
                <span class="row-tight">
                  <span class="tech-dot" [style.background]="booking.technician_color" aria-hidden="true"></span>
                  {{ booking.technician_name }}
                </span>
                <span aria-hidden="true">·</span>
                <span>{{ booking.start_local }} – {{ booking.end_local }} ({{ booking.timezone_label }})</span>
              </div>

              @if (booking.exception_reason) {
                <div class="small" style="margin-top: 6px; color:#991b1b">
                  {{ booking.exception_reason }}
                </div>
              }

              @if (booking.proposal; as proposal) {
                @if (proposal.status === 'proposed') {
                  <div class="notice notice-warn" style="margin-top: 12px">
                    <span class="notice-icon" aria-hidden="true">!</span>
                    <div class="stack-sm" style="flex:1">
                      <strong>Your technician is unavailable — approve a replacement?</strong>
                      <span class="small">
                        {{ proposal.reason }}. Same time, same price. Nothing changes until you approve.
                      </span>

                      <div role="radiogroup" aria-label="Replacement technician" class="stack-sm">
                        @for (candidate of proposal.candidates; track candidate.technician_id) {
                          <button
                            type="button"
                            role="radio"
                            class="option-card"
                            style="padding: 10px 12px"
                            [attr.aria-checked]="picked() === candidate.technician_id"
                            [disabled]="!candidate.available"
                            (click)="picked.set(candidate.technician_id)"
                          >
                            <div class="spread">
                              <span class="option-title">
                                <span class="tech-dot" [style.background]="candidate.technician_color" aria-hidden="true"></span>
                                {{ candidate.technician_name }}
                              </span>
                              <span class="small muted">{{ candidate.note }}</span>
                            </div>
                          </button>
                        }
                      </div>

                      <div class="row">
                        <button
                          type="button"
                          class="btn btn-primary btn-sm"
                          [disabled]="!picked() || working()"
                          (click)="approve(booking)"
                        >
                          @if (working()) { <span class="spinner" aria-hidden="true"></span> }
                          Approve replacement
                        </button>
                        <button type="button" class="btn btn-ghost btn-sm" [disabled]="working()" (click)="decline(booking)">
                          Decline
                        </button>
                      </div>
                    </div>
                  </div>
                } @else if (proposal.status === 'unresolved') {
                  <div class="notice notice-error" style="margin-top: 12px">
                    <span class="notice-icon" aria-hidden="true">!</span>
                    <span>
                      No qualified technician is free at this time. Nothing was rescheduled
                      automatically — the owner will follow up.
                    </span>
                  </div>
                }
              }

              @if (booking.status === 'payment_exception') {
                <div class="notice notice-exception" style="margin-top: 12px">
                  <span class="notice-icon" aria-hidden="true">!</span>
                  <span>
                    Your payment was captured but the slot is gone. The owner must resolve this
                    manually; you have not been double-charged.
                  </span>
                </div>
              }
            </article>
          }
        </div>
      }
    </section>
  `,
})
export class BookingsPanel {
  private readonly api = inject(ApiService);

  readonly bookings = input.required<BookingInfo[]>();
  readonly busy = input(false);
  readonly refresh = output<void>();
  readonly changed = output<BookingInfo>();

  protected readonly working = signal(false);
  protected readonly picked = signal<string | null>(null);
  protected readonly error = signal<PresentedError | null>(null);

  protected readonly sorted = computed(() =>
    [...this.bookings()].sort((a, b) => (a.start_utc < b.start_utc ? 1 : -1)),
  );

  protected money(cents: number, currency: string): string {
    return formatMoney(cents, currency);
  }

  protected async approve(booking: BookingInfo): Promise<void> {
    const proposal = booking.proposal;
    const technicianId = this.picked();
    if (!proposal || !technicianId) return;
    this.error.set(null);
    this.working.set(true);
    try {
      const updated = await firstValueFrom(
        this.api.approveReassignment(booking.id, proposal.id, technicianId),
      );
      this.picked.set(null);
      this.changed.emit(updated);
    } catch (error) {
      this.error.set(present(error));
    } finally {
      this.working.set(false);
    }
  }

  protected async decline(booking: BookingInfo): Promise<void> {
    const proposal = booking.proposal;
    if (!proposal) return;
    this.error.set(null);
    this.working.set(true);
    try {
      const updated = await firstValueFrom(
        this.api.declineReassignment(booking.id, proposal.id),
      );
      this.changed.emit(updated);
    } catch (error) {
      this.error.set(present(error));
    } finally {
      this.working.set(false);
    }
  }
}

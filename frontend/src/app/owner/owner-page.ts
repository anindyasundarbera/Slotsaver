import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../core/api.service';
import { present, PresentedError } from '../core/errors';
import { addBusinessDays, formatMoney, shiftDays, statusLabel } from '../core/format';
import {
  AnalyticsInfo,
  BookingInfo,
  DisruptionResult,
  TechnicianInfo,
  TimelineInfo,
} from '../core/models';
import { SessionStore } from '../core/session.store';
import { ErrorLine } from '../shared/error-line';
import { Notice } from '../shared/notice';
import { Spinner } from '../shared/spinner';
import { StatusChip } from '../shared/status-chip';
import { AnalyticsPanel } from './analytics-panel';
import { DisruptionPanel } from './disruption-panel';
import { TimelineComponent } from './timeline.component';

@Component({
  selector: 'ss-owner-page',
  imports: [
    ErrorLine,
    Notice,
    Spinner,
    StatusChip,
    AnalyticsPanel,
    DisruptionPanel,
    TimelineComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './owner-page.html',
})
export class OwnerPage implements OnInit {
  private readonly api = inject(ApiService);
  protected readonly session = inject(SessionStore);

  protected readonly timeline = signal<TimelineInfo | null>(null);
  protected readonly analytics = signal<AnalyticsInfo | null>(null);
  protected readonly bookings = signal<BookingInfo[]>([]);
  protected readonly technicians = signal<TechnicianInfo[]>([]);
  protected readonly audit = signal<
    Array<{
      at: string;
      action: string;
      actor_role: string;
      subject_type: string;
      subject_id: string;
      detail: Record<string, unknown>;
    }>
  >([]);

  protected readonly day = signal('');
  protected readonly from = signal('');
  protected readonly to = signal('');
  protected readonly busy = signal(false);
  protected readonly error = signal<PresentedError | null>(null);
  protected readonly flash = signal<string | null>(null);
  protected readonly resolving = signal<string | null>(null);

  protected readonly exceptions = computed(() =>
    this.bookings().filter((booking) => booking.status === 'payment_exception'),
  );
  protected readonly currency = computed(() => this.session.config()?.currency ?? 'USD');

  async ngOnInit(): Promise<void> {
    const demoDay = this.session.config()?.demo_date ?? '';
    this.day.set(demoDay);
    this.from.set(addBusinessDays(demoDay, -6));
    this.to.set(addBusinessDays(demoDay, 7));
    await this.loadAll();
  }

  private async loadAll(): Promise<void> {
    await Promise.all([this.loadTimeline(), this.loadAnalytics(), this.loadBookings(), this.loadAudit()]);
  }

  protected async loadTimeline(): Promise<void> {
    this.busy.set(true);
    try {
      this.timeline.set(await firstValueFrom(this.api.timeline(this.day())));
      const info = this.timeline();
      if (info) this.technicians.set(info.technicians);
    } catch (error) {
      this.setError(error);
    } finally {
      this.busy.set(false);
    }
  }

  protected async loadAnalytics(): Promise<void> {
    try {
      this.analytics.set(await firstValueFrom(this.api.analytics(this.from(), this.to())));
    } catch (error) {
      this.setError(error);
    }
  }

  protected async loadBookings(): Promise<void> {
    try {
      this.bookings.set(await firstValueFrom(this.api.allBookings()));
    } catch (error) {
      this.setError(error);
    }
  }

  protected async loadAudit(): Promise<void> {
    try {
      this.audit.set(await firstValueFrom(this.api.audit(30)));
    } catch {
      // Audit is supporting evidence; do not block the page on it.
    }
  }

  protected async shiftDay(direction: number): Promise<void> {
    this.day.set(direction === 0 ? (this.session.config()?.demo_date ?? this.day()) : shiftDays(this.day(), direction));
    await this.loadTimeline();
  }

  protected async changeRange(range: { from: string; to: string }): Promise<void> {
    this.from.set(range.from);
    this.to.set(range.to);
    await this.loadAnalytics();
  }

  protected async refreshAll(): Promise<void> {
    this.flash.set(null);
    await this.loadAll();
    this.flash.set('Timeline and analytics reloaded from the server.');
  }

  protected async onDisruption(result: DisruptionResult): Promise<void> {
    // Refresh from canonical server state, never from the mutation response.
    await this.loadAll();
    this.flash.set(
      `Recorded: ${result.affected_booking_ids.length} booking(s) affected, ` +
        `${result.proposals_created.length} proposal(s) raised.`,
    );
  }

  protected async resolveException(
    booking: BookingInfo,
    resolution: 'cancelled' | 'confirmed_manually',
  ): Promise<void> {
    const label =
      resolution === 'cancelled'
        ? 'Cancel this booking and record the money as unresolved?'
        : 'Force-confirm this booking without a verified capture?';
    if (!window.confirm(`${label}\n\nThis action is audited.`)) return;
    this.resolving.set(booking.id);
    try {
      const updated = await firstValueFrom(
        this.api.resolveException(booking.id, resolution, 'Owner resolved from workspace'),
      );
      this.flash.set(`Booking ${updated.reference} is now ${statusLabel(updated.status)}.`);
      await this.loadAll();
    } catch (error) {
      this.setError(error);
    } finally {
      this.resolving.set(null);
    }
  }

  private setError(error: unknown): void {
    this.error.set(present(error));
  }

  protected money(cents: number): string {
    return formatMoney(cents, this.currency());
  }
}

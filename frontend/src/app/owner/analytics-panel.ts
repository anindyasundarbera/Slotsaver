import { ChangeDetectionStrategy, Component, computed, inject, input, output, signal } from '@angular/core';

import { formatMoney, formatMoneyShort } from '../core/format';
import { AnalyticsBucket, AnalyticsInfo, AnalyticsRow } from '../core/models';
import { Spinner } from '../shared/spinner';

type Filter = { kind: 'service' | 'technician' | 'status'; key: string } | null;

@Component({
  selector: 'ss-analytics-panel',
  imports: [Spinner],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="card" aria-labelledby="analytics-heading">
      <div class="card-header">
        <h2 id="analytics-heading">Operational analytics</h2>
        <div class="row-tight">
          <label class="small muted" for="from">From</label>
          <input id="from" type="date" class="input" style="width: auto"
                 [value]="from()" (change)="onFrom($any($event.target).value)" />
          <label class="small muted" for="to">To</label>
          <input id="to" type="date" class="input" style="width: auto"
                 [value]="to()" (change)="onTo($any($event.target).value)" />
          <button type="button" class="btn btn-secondary btn-sm" (click)="reload.emit()">Refresh</button>
        </div>
      </div>

      @if (!data()) {
        <ss-spinner label="Loading analytics…" />
      } @else if (data(); as info) {
        <div class="grid-3" style="margin-bottom: 16px">
          <div class="kpi">
            <span class="kpi-value">{{ info.confirmed_count }}</span>
            <span class="kpi-label">Confirmed bookings</span>
            <span class="small muted">{{ money(info.confirmed_revenue_cents) }} service revenue</span>
          </div>
          <div class="kpi">
            <span class="kpi-value">{{ money(info.captured_all_cents) }}</span>
            <span class="kpi-label">All captured money</span>
            <span class="small muted">includes unresolved exceptions</span>
          </div>
          <div class="kpi" [class.is-warning]="info.exception_count > 0">
            <span class="kpi-value">{{ info.exception_count }}</span>
            <span class="kpi-label">Payment exceptions</span>
            <span class="small muted">{{ money(info.exception_cents) }} needs manual resolution</span>
          </div>
        </div>

        <div class="grid-3" style="margin-bottom: 20px">
          <div>
            <p class="eyebrow" style="margin-bottom: 8px">By service · confirmed revenue</p>
            <div class="bars">
              @for (bucket of info.by_service; track bucket.key) {
                <button
                  type="button"
                  class="bar-row"
                  [attr.aria-pressed]="isActive('service', bucket.key)"
                  (click)="toggle('service', bucket.key)"
                >
                  <span class="bar-label">{{ bucket.label }}</span>
                  <span class="bar-track">
                    <span class="bar-fill" [style.width.%]="pct(bucket, info)"></span>
                  </span>
                  <span class="bar-value">{{ short(bucket.revenue_cents) }} · {{ bucket.booking_count }}</span>
                </button>
              }
            </div>
          </div>

          <div>
            <p class="eyebrow" style="margin-bottom: 8px">By technician · confirmed revenue</p>
            <div class="bars">
              @for (bucket of info.by_technician; track bucket.key) {
                <button
                  type="button"
                  class="bar-row"
                  [attr.aria-pressed]="isActive('technician', bucket.key)"
                  (click)="toggle('technician', bucket.key)"
                >
                  <span class="bar-label">{{ bucket.label }}</span>
                  <span class="bar-track">
                    <span class="bar-fill" [style.width.%]="pct(bucket, info)"></span>
                  </span>
                  <span class="bar-value">{{ short(bucket.revenue_cents) }} · {{ bucket.booking_count }}</span>
                </button>
              }
            </div>
          </div>

          <div>
            <p class="eyebrow" style="margin-bottom: 8px">By status · bookings</p>
            <div class="bars">
              @for (bucket of info.by_status; track bucket.key) {
                <button
                  type="button"
                  class="bar-row"
                  [attr.aria-pressed]="isActive('status', bucket.key)"
                  (click)="toggle('status', bucket.key)"
                >
                  <span class="bar-label">{{ bucket.label }}</span>
                  <span class="bar-track">
                    <span class="bar-fill" [style.width.%]="pctCount(bucket, info)"></span>
                  </span>
                  <span class="bar-value">{{ bucket.booking_count }}</span>
                </button>
              }
            </div>
          </div>
        </div>

        <div class="row" style="margin-bottom: 12px">
          <strong class="small">Underlying rows</strong>
          <span class="small muted">{{ filteredRows().length }} of {{ info.rows.length }}</span>
          @if (filter(); as active) {
            <span class="tag">{{ active.kind }}: {{ active.key }}</span>
            <button type="button" class="btn btn-ghost btn-sm" (click)="filter.set(null)">
              Clear filter
            </button>
          }
        </div>

        <div class="table-wrap">
          <table class="data">
            <caption class="sr-only">Bookings behind the aggregates above</caption>
            <thead>
              <tr>
                <th scope="col">Reference</th>
                <th scope="col">Status</th>
                <th scope="col">Service</th>
                <th scope="col">Technician</th>
                <th scope="col">Customer</th>
                <th scope="col">Day</th>
                <th scope="col">Start</th>
                <th scope="col">Price</th>
                <th scope="col">Counted</th>
              </tr>
            </thead>
            <tbody>
              @for (row of filteredRows(); track row.booking_id) {
                <tr [class.is-attention]="row.needs_attention">
                  <td class="mono">{{ row.reference }}</td>
                  <td>{{ row.status_label }}</td>
                  <td>{{ row.service_name }}</td>
                  <td>{{ row.technician_name }}</td>
                  <td>{{ row.customer_name }}</td>
                  <td>{{ row.day }}</td>
                  <td>{{ row.start_local }}</td>
                  <td class="nowrap">{{ money(row.price_cents) }}</td>
                  <td>
                    @if (row.counted_as_revenue) {
                      <span class="tag" style="color:#166534;border-color:#86efac;background:#dcfce7">revenue</span>
                    } @else {
                      <span class="tag">no</span>
                    }
                  </td>
                </tr>
              } @empty {
                <tr><td colspan="9" class="muted">No rows for this filter.</td></tr>
              }
            </tbody>
          </table>
        </div>

        <ul class="small muted" style="margin: 12px 0 0; padding-left: 18px">
          @for (note of info.notes; track $index) {
            <li>{{ note }}</li>
          }
        </ul>
      }
    </section>
  `,
})
export class AnalyticsPanel {
  readonly data = input<AnalyticsInfo | null>(null);
  readonly from = input.required<string>();
  readonly to = input.required<string>();
  readonly reload = output<void>();
  readonly rangeChange = output<{ from: string; to: string }>();

  protected readonly filter = signal<Filter>(null);

  protected readonly filteredRows = computed<AnalyticsRow[]>(() => {
    const info = this.data();
    if (!info) return [];
    const active = this.filter();
    if (!active) return info.rows;
    if (active.kind === 'service') {
      return info.rows.filter((row) => row.service_name === active.key);
    }
    if (active.kind === 'technician') {
      return info.rows.filter((row) => row.technician_name === active.key);
    }
    return info.rows.filter((row) => row.status_label === active.key);
  });

  protected money(cents: number): string {
    return formatMoney(cents, this.data()?.currency ?? 'USD');
  }
  protected short(cents: number): string {
    return formatMoneyShort(cents);
  }

  protected pct(bucket: AnalyticsBucket, info: AnalyticsInfo): number {
    const max = Math.max(1, ...info.by_service.concat(info.by_technician).map((b) => b.revenue_cents));
    return Math.round((bucket.revenue_cents / max) * 100);
  }
  protected pctCount(bucket: AnalyticsBucket, info: AnalyticsInfo): number {
    const max = Math.max(1, ...info.by_status.map((b) => b.booking_count));
    return Math.round((bucket.booking_count / max) * 100);
  }

  protected isActive(kind: 'service' | 'technician' | 'status', key: string): boolean {
    const active = this.filter();
    return active !== null && active.kind === kind && active.key === key;
  }

  protected toggle(kind: 'service' | 'technician' | 'status', key: string): void {
    const active = this.filter();
    this.filter.set(active && active.kind === kind && active.key === key ? null : { kind, key });
  }

  protected onFrom(value: string): void {
    this.rangeChange.emit({ from: value, to: this.to() });
  }
  protected onTo(value: string): void {
    this.rangeChange.emit({ from: this.from(), to: value });
  }
}

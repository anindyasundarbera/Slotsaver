import {
  AfterViewInit,
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  OnDestroy,
  effect,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import type { Scheduler } from '@bryntum/scheduler';

import { TimelineEvent, TimelineInfo } from '../core/models';

interface FallbackBar {
  left: number;
  width: number;
  label: string;
  color: string;
  title: string;
}

interface FallbackRow {
  technicianId: string;
  name: string;
  color: string;
  bars: FallbackBar[];
}

const DAY_START_HOUR = 8;
const DAY_END_HOUR = 18;

/** Bryntum Scheduler trial wrapper with a functional fallback view. */
@Component({
  selector: 'ss-timeline',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="card">
      <div class="card-header">
        <h2>Technician timeline</h2>
        <div class="row-tight">
          <button type="button" class="btn btn-secondary btn-sm" (click)="shift.emit(-1)">
            ← Prev
          </button>
          <button type="button" class="btn btn-ghost btn-sm" (click)="shift.emit(0)">Demo day</button>
          <button type="button" class="btn btn-secondary btn-sm" (click)="shift.emit(1)">
            Next →
          </button>
        </div>
      </div>

      @if (data(); as info) {
        <div class="row" style="margin-bottom: 12px">
          <span class="tag">{{ info.day }}</span>
          <span class="small muted">
            Times in {{ info.timezone_label }} · {{ info.events.length }} event(s) ·
            {{ info.technicians.length }} technician(s)
          </span>
        </div>
      }

      @if (failed()) {
        <div class="notice notice-warn" style="margin-bottom: 12px" role="status">
          <span class="notice-icon" aria-hidden="true">!</span>
          <span>
            The Bryntum widget did not start here, so the equivalent built-in timeline is
            shown. Same data, same colours.
          </span>
        </div>
        <div class="fallback-grid" role="table" aria-label="Technician schedule">
          @for (row of fallbackRows(); track row.technicianId) {
            <div class="fallback-row" role="row">
              <div class="fallback-name" role="rowheader">
                <span class="tech-dot" [style.background]="row.color" aria-hidden="true"></span>
                {{ row.name }}
              </div>
              <div class="fallback-track" role="cell">
                @for (bar of row.bars; track $index) {
                  <div
                    class="fallback-chip"
                    [style.left.%]="bar.left"
                    [style.width.%]="bar.width"
                    [style.background]="bar.color"
                    [title]="bar.title"
                  >
                    {{ bar.label }}
                  </div>
                }
              </div>
            </div>
          }
          <div class="fallback-hours">
            <div></div>
            <div><span>8 AM</span><span>1 PM</span><span>6 PM</span></div>
          </div>
        </div>
      } @else {
        <div #host style="height: 320px; min-width: 0"></div>
      }

      <p class="hint" style="margin-top: 12px">
        Bryntum Scheduler (trial build) — evaluation watermark; a licensed key is required
        for production. Amber = held, green = confirmed, red = needs reassignment,
        purple = payment exception, slate = unavailable.
      </p>
    </div>
  `,
})
export class TimelineComponent implements AfterViewInit, OnDestroy {
  readonly data = input<TimelineInfo | null>(null);
  readonly timezone = input<string>('America/New_York');
  readonly shift = output<number>();
  private readonly host = viewChild<ElementRef<HTMLDivElement>>('host');

  protected readonly failed = signal(false);

  private scheduler: Scheduler | null = null;
  private destroyed = false;
  private viewReady = false;
  private lastSignature = '';
  private starting = false;

  constructor() {
    // The data arrives after the view is created, and changes whenever the
    // presenter navigates days. Both must rebuild the widget.
    effect(() => {
      const info = this.data();
      if (!info) return;
      const signature = `${info.day}:${info.events.length}:${info.technicians.length}`;
      if (!this.viewReady || signature === this.lastSignature || this.starting) return;
      this.lastSignature = signature;
      void this.start();
    });
  }

  ngAfterViewInit(): void {
    this.viewReady = true;
    const info = this.data();
    if (info) {
      this.lastSignature = `${info.day}:${info.events.length}:${info.technicians.length}`;
      void this.start();
    }
  }

  ngOnDestroy(): void {
    this.destroyed = true;
    this.teardown();
  }

  private async start(): Promise<void> {
    if (this.starting || this.destroyed) return;
    this.starting = true;
    try {
      const module = await import('@bryntum/scheduler');
      const info = this.data();
      const element = this.host()?.nativeElement;
      if (!info || !element || this.destroyed) return;
      if (element.childElementCount > 0) {
        this.teardown();
        element.replaceChildren();
      }

      this.scheduler = new module.Scheduler({
        appendTo: element,
        resources: info.technicians.map((tech) => ({
          id: tech.id,
          name: tech.name,
          eventColor: tech.color,
        })),
        events: info.events.map((event) => ({
          id: event.id,
          resourceId: event.technician_id,
          name: event.title,
          startDate: this.wallClock(event.start_utc),
          endDate: this.wallClock(event.end_utc),
          eventColor: event.color,
          dataStatus: event.status,
        })),
        // The widget renders in browser-local time, so feed it the *business*
        // wall clock. That keeps the axis at 08:00-18:00 whatever timezone the
        // presenter's machine is in, which matches the labels on screen.
        startDate: this.dayStart(info.day),
        endDate: this.dayEnd(info.day),
        viewPreset: 'hourAndDay',
        rowHeight: 60,
        height: 320,
        flex: '1 1 auto',
        barMargin: 6,
        columns: [{ field: 'name', text: 'Technician', width: 160 }],
        features: {
          eventEdit: false,
          eventDrag: false,
          eventResize: false,
          dependencies: false,
          timeRanges: false,
        },
      });
      this.failed.set(false);
    } catch {
      this.teardown();
      this.failed.set(true);
    } finally {
      this.starting = false;
    }
  }

  /** Convert a UTC instant into a Date carrying the business wall-clock readings. */
  private wallClock(iso: string): Date {
    const formatter = new Intl.DateTimeFormat('en-CA', {
      timeZone: this.timezone(),
      hour12: false,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
    const parts = formatter.formatToParts(new Date(iso));
    const get = (type: string): number => Number(parts.find((p) => p.type === type)?.value ?? '0');
    return new Date(get('year'), get('month') - 1, get('day'), get('hour') % 24, get('minute'));
  }

  private dayStart(day: string): Date {
    const [year, month, date] = day.split('-').map(Number);
    return new Date(year, month - 1, date, DAY_START_HOUR, 0);
  }

  private dayEnd(day: string): Date {
    const [year, month, date] = day.split('-').map(Number);
    return new Date(year, month - 1, date, DAY_END_HOUR, 0);
  }

  private teardown(): void {
    try {
      this.scheduler?.destroy();
    } catch {
      // A partially-constructed widget can throw on destroy; nothing to recover.
    }
    this.scheduler = null;
  }

  protected fallbackRows(): FallbackRow[] {
    const info = this.data();
    if (!info) return [];
    const span = DAY_END_HOUR - DAY_START_HOUR;
    return info.technicians.map((tech) => ({
      technicianId: tech.id,
      name: tech.name,
      color: tech.color,
      bars: info.events
        .filter((event) => event.technician_id === tech.id)
        .map((event) => this.toBar(event, span)),
    }));
  }

  private toBar(event: TimelineEvent, spanHours: number): FallbackBar {
    const localStart = this.localHour(new Date(event.start_utc));
    const localEnd = this.localHour(new Date(event.end_utc));
    const left = Math.max(0, ((localStart - DAY_START_HOUR) / spanHours) * 100);
    const width = Math.max(2, ((localEnd - localStart) / spanHours) * 100);
    return {
      left,
      width: Math.min(width, 100 - left),
      label: event.title,
      color: event.color,
      title: `${event.title} — ${event.status_label}`,
    };
  }

  private localHour(date: Date): number {
    const formatter = new Intl.DateTimeFormat('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
      timeZone: this.timezone(),
    });
    const parts = formatter.formatToParts(date);
    const hour = Number(parts.find((p) => p.type === 'hour')?.value ?? '0');
    const minute = Number(parts.find((p) => p.type === 'minute')?.value ?? '0');
    return hour + minute / 60;
  }
}

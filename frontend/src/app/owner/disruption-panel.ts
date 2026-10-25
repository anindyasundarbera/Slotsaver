import { ChangeDetectionStrategy, Component, computed, effect, inject, input, output, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../core/api.service';
import { present, PresentedError } from '../core/errors';
import { zonedIso } from '../core/format';
import { BookingInfo, DisruptionResult, TechnicianInfo } from '../core/models';
import { ErrorLine } from '../shared/error-line';
import { Notice } from '../shared/notice';

@Component({
  selector: 'ss-disruption-panel',
  imports: [ReactiveFormsModule, ErrorLine, Notice],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="card" aria-labelledby="disruption-heading">
      <div class="card-header">
        <h2 id="disruption-heading">Technician unavailability</h2>
      </div>
      <p class="small muted" style="margin-bottom: 16px">
        Marking a technician unavailable never reschedules a paid booking on its own. It
        raises a proposal that the customer must approve.
      </p>

      @if (error(); as err) {
        <ss-error-line [error]="err" />
      }

      <form [formGroup]="form" (ngSubmit)="submit()" class="stack">
        <div class="field">
          <label for="tech">Technician</label>
          <select id="tech" class="select" formControlName="technicianId">
            @for (tech of technicians(); track tech.id) {
              <option [value]="tech.id">{{ tech.name }} · {{ tech.skills.join(', ') }}</option>
            }
          </select>
        </div>

        <div class="grid-3">
          <div class="field">
            <label for="uDay">Day</label>
            <input id="uDay" type="date" class="input" formControlName="day" />
          </div>
          <div class="field">
            <label for="uStart">From</label>
            <input id="uStart" type="time" class="input" formControlName="start" step="1800" />
          </div>
          <div class="field">
            <label for="uEnd">To</label>
            <input id="uEnd" type="time" class="input" formControlName="end" step="1800" />
          </div>
        </div>

        <div class="field">
          <label for="uReason">Reason (shown to the customer)</label>
          <input id="uReason" class="input" formControlName="reason" maxlength="120" />
        </div>

        <div class="row">
          <button type="submit" class="btn btn-danger" [disabled]="busy() || form.invalid">
            @if (busy()) { <span class="spinner" aria-hidden="true"></span> }
            Mark unavailable
          </button>
          <span class="hint">Times are interpreted in {{ timezone() }}.</span>
        </div>
      </form>

      @if (result(); as outcome) {
        <div class="stack-sm" style="margin-top: 16px">
          <ss-notice tone="info" title="Disruption recorded">
            {{ outcome.technician_name }} is unavailable.
            {{ outcome.affected_booking_ids.length }} paid booking(s) affected,
            {{ outcome.proposals_created.length }} proposal(s) raised,
            {{ outcome.unresolved_booking_ids.length }} with no qualified alternative.
          </ss-notice>

          @if (outcome.affected_booking_ids.length) {
            <div class="table-wrap">
              <table class="data">
                <thead>
                  <tr><th scope="col">Reference</th><th scope="col">Status now</th><th scope="col">Resolution</th></tr>
                </thead>
                <tbody>
                  @for (id of outcome.affected_booking_ids; track id) {
                    <tr>
                      <td class="mono">{{ referenceFor(id) }}</td>
                      <td>{{ statusFor(id) }}</td>
                      <td class="small muted">
                        @if (outcome.unresolved_booking_ids.includes(id)) {
                          No qualified technician free at this time
                        } @else {
                          Awaiting customer approval
                        }
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          }
        </div>
      }
    </section>
  `,
})
export class DisruptionPanel {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);

  readonly technicians = input.required<TechnicianInfo[]>();
  readonly bookings = input.required<BookingInfo[]>();
  readonly timezone = input.required<string>();
  readonly demoDay = input.required<string>();
  readonly done = output<DisruptionResult>();

  protected readonly busy = signal(false);
  protected readonly result = signal<DisruptionResult | null>(null);
  protected readonly error = signal<PresentedError | null>(null);

  protected readonly form = this.fb.nonNullable.group({
    technicianId: ['', Validators.required],
    day: ['', Validators.required],
    start: ['13:00', Validators.required],
    end: ['18:00', Validators.required],
    reason: ['Family emergency', Validators.required],
  });

  constructor() {
    // Populate as soon as the server data arrives, so the presenter never
    // faces an empty select on stage.
    effect(() => {
      const techs = this.technicians();
      if (techs.length && !this.form.controls.technicianId.value) {
        this.form.patchValue({ technicianId: techs[0].id });
      }
    });
    effect(() => {
      const day = this.disruptionDay();
      if (day && !this.form.controls.day.value) {
        this.form.patchValue({ day });
      }
    });
  }

  private readonly disruptionDay = computed(() => {
    // The day after the demo day is where the seeded disruption booking lives.
    const base = this.demoDay();
    if (!base) return '';
    const date = new Date(`${base}T12:00:00Z`);
    let remaining = 2;
    while (remaining > 0) {
      date.setUTCDate(date.getUTCDate() + 1);
      if (date.getUTCDay() !== 0) remaining -= 1;
    }
    return date.toISOString().slice(0, 10);
  });

  protected referenceFor(id: string): string {
    return this.bookings().find((booking) => booking.id === id)?.reference ?? id;
  }
  protected statusFor(id: string): string {
    return this.bookings().find((booking) => booking.id === id)?.status_label ?? '—';
  }

  protected async submit(): Promise<void> {
    if (this.form.invalid || this.busy()) return;
    const value = this.form.getRawValue();
    this.error.set(null);
    this.busy.set(true);
    try {
      const result = await firstValueFrom(
        this.api.markUnavailable({
          technician_id: value.technicianId,
          start_utc: zonedIso(value.day, value.start, this.timezone()),
          end_utc: zonedIso(value.day, value.end, this.timezone()),
          reason: value.reason,
        }),
      );
      this.result.set(result);
      this.done.emit(result);
    } catch (error) {
      this.error.set(present(error));
    } finally {
      this.busy.set(false);
    }
  }
}

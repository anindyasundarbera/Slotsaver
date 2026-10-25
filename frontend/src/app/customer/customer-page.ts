import { ChangeDetectionStrategy, Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../core/api.service';
import { present, PresentedError } from '../core/errors';
import {
  addBusinessDays,
  formatClock,
  formatDayLabel,
  formatMoney,
  statusLabel,
} from '../core/format';
import {
  AppointmentOption,
  AssistantReply,
  BookingInfo,
  CheckoutInfo,
  PaymentInfo,
  ServiceInfo,
  HoldInfo,
  ToolTrace,
} from '../core/models';
import { SessionStore } from '../core/session.store';
import { ErrorLine } from '../shared/error-line';
import { Notice } from '../shared/notice';
import { Spinner } from '../shared/spinner';
import { BookingsPanel } from './bookings-panel';

interface ChatEntry {
  role: 'user' | 'assistant';
  text: string;
}

const DEMO_REQUEST =
  'I need washing-machine service tomorrow after 4 PM. My budget is $80, and it must finish before 6.';

@Component({
  selector: 'ss-customer-page',
  imports: [ReactiveFormsModule, ErrorLine, Notice, Spinner, BookingsPanel],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './customer-page.html',
})
export class CustomerPage implements OnInit, OnDestroy {
  protected readonly session = inject(SessionStore);
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);

  // ------------------------------------------------------------ assistant
  protected readonly chat = signal<ChatEntry[]>([]);
  protected readonly draft = signal(DEMO_REQUEST);
  protected readonly asking = signal(false);
  protected readonly reply = signal<AssistantReply | null>(null);
  protected readonly trace = signal<ToolTrace[]>([]);
  protected readonly conversationId = signal<string | null>(null);
  protected readonly fallbackReason = signal<string | null>(null);

  // ------------------------------------------------------------ guided form
  protected readonly services = signal<ServiceInfo[]>([]);
  protected readonly searching = signal(false);
  protected readonly options = signal<AppointmentOption[]>([]);
  protected readonly optionsNote = signal<string | null>(null);
  protected readonly selected = signal<AppointmentOption | null>(null);
  protected readonly form = this.fb.nonNullable.group({
    serviceCode: ['washer-repair', Validators.required],
    day: ['', Validators.required],
    afterLocal: ['16:00'],
    beforeLocal: ['18:00'],
    budget: [80],
  });

  // ------------------------------------------------------------ hold + pay
  protected readonly hold = signal<HoldInfo | null>(null);
  protected readonly holding = signal(false);
  protected readonly checkout = signal<CheckoutInfo | null>(null);
  protected readonly checkoutBusy = signal(false);
  protected readonly payment = signal<PaymentInfo | null>(null);
  protected readonly paying = signal(false);
  protected readonly remaining = signal(0);
  protected readonly holdNotice = signal<string | null>(null);
  private timer: ReturnType<typeof setInterval> | null = null;

  protected readonly error = signal<PresentedError | null>(null);
  protected readonly flash = signal<string | null>(null);
  protected readonly busyLabel = signal<string | null>(null);

  protected readonly demoDate = computed(() => this.session.config()?.demo_date ?? '');
  protected readonly simulated = computed(() => this.session.config()?.paypal_mode === 'simulated');
  protected readonly confirmed = computed(() => this.payment()?.booking_status === 'confirmed');
  protected readonly exceptionRaised = computed(
    () => this.payment()?.booking_status === 'payment_exception',
  );
  protected readonly assistantModeLabel = computed(() =>
    this.reply()?.mode === 'llm' ? 'Live AI assistant' : 'Scripted assistant (offline)',
  );

  async ngOnInit(): Promise<void> {
    const config = this.session.config();
    const today = config?.demo_date ?? '';
    this.form.patchValue({ day: addBusinessDays(today, 1) });
    try {
      this.services.set(await firstValueFrom(this.api.services()));
    } catch (error) {
      this.error.set(present(error));
    }
    this.chat.set([
      {
        role: 'assistant',
        text: 'Tell me what you need. For example: “washing machine tomorrow after 4 PM, budget $80, finish before 6.”',
      },
    ]);
    await this.reloadBookings();
  }

  ngOnDestroy(): void {
    this.stopTimer();
  }

  // ------------------------------------------------------------ assistant
  protected async ask(): Promise<void> {
    const message = this.draft().trim();
    if (!message || this.asking()) return;
    this.error.set(null);
    this.fallbackReason.set(null);
    this.chat.update((entries) => [...entries, { role: 'user', text: message }]);
    this.asking.set(true);
    try {
      const reply = await firstValueFrom(this.api.assistant(message, this.conversationId()));
      this.reply.set(reply);
      this.trace.set(reply.tool_trace);
      this.conversationId.set(reply.conversation_id);
      this.chat.update((entries) => [...entries, { role: 'assistant', text: reply.reply }]);
      if (reply.options.length) {
        this.options.set(reply.options);
        this.selected.set(null);
        this.optionsNote.set(null);
      } else if (!reply.needs_clarification) {
        this.optionsNote.set('No bookable options matched. Adjust the form and search again.');
      }
      if (reply.fallback_required) {
        this.fallbackReason.set(reply.fallback_reason ?? 'The assistant could not answer.');
      }
    } catch (error) {
      const shown = present(error);
      this.error.set(shown);
      this.fallbackReason.set('The assistant is unavailable. Use the guided form below.');
    } finally {
      this.asking.set(false);
    }
  }

  protected useDemoRequest(): void {
    this.draft.set(DEMO_REQUEST);
  }

  protected async search(): Promise<void> {
    if (this.form.invalid || this.searching()) return;
    const value = this.form.getRawValue();
    this.error.set(null);
    this.searching.set(true);
    this.selected.set(null);
    try {
      const options = await firstValueFrom(
        this.api.availability({
          serviceCode: value.serviceCode,
          day: value.day,
          afterLocal: value.afterLocal || null,
          beforeLocal: value.beforeLocal || null,
          maxPriceCents: value.budget ? value.budget * 100 : null,
        }),
      );
      this.options.set(options);
      this.optionsNote.set(
        options.length
          ? null
          : `No ${value.serviceCode.replace('-', ' ')} appointments match those filters.`,
      );
    } catch (error) {
      this.error.set(present(error));
    } finally {
      this.searching.set(false);
    }
  }

  protected select(option: AppointmentOption): void {
    this.selected.set(option);
  }

  // ------------------------------------------------------------ hold
  protected async placeHold(): Promise<void> {
    const option = this.selected();
    if (!option || this.holding()) return;
    this.error.set(null);
    this.holding.set(true);
    this.busyLabel.set('Holding this slot…');
    try {
      const hold = await firstValueFrom(
        this.api.createHold({
          service_code: option.service_code,
          technician_id: option.technician_id,
          start_utc: option.start_utc,
        }),
      );
      this.hold.set(hold);
      this.checkout.set(null);
      this.payment.set(null);
      this.holdNotice.set(null);
      this.startTimer(hold.seconds_remaining);
      await this.reloadBookings();
    } catch (error) {
      this.error.set(present(error));
      await this.search();
    } finally {
      this.holding.set(false);
      this.busyLabel.set(null);
    }
  }

  protected async releaseHold(): Promise<void> {
    const hold = this.hold();
    if (!hold) return;
    this.busyLabel.set('Releasing the hold…');
    this.error.set(null);
    try {
      await firstValueFrom(this.api.releaseHold(hold.id));
      this.resetPurchase();
      this.holdNotice.set('Hold released. The slot is available again.');
      await this.search();
      await this.reloadBookings();
    } catch (error) {
      this.error.set(present(error));
    } finally {
      this.busyLabel.set(null);
    }
  }

  // ------------------------------------------------------------ payment
  protected async startCheckout(): Promise<void> {
    const hold = this.hold();
    if (!hold || this.checkoutBusy()) return;
    this.error.set(null);
    this.checkoutBusy.set(true);
    this.busyLabel.set('Creating the PayPal Sandbox order…');
    try {
      const checkout = await firstValueFrom(this.api.startCheckout(hold.id));
      this.checkout.set(checkout);
      if (checkout.approve_url && !checkout.simulated_token) {
        window.open(checkout.approve_url, '_blank', 'noopener');
      }
    } catch (error) {
      this.error.set(present(error));
    } finally {
      this.checkoutBusy.set(false);
      this.busyLabel.set(null);
    }
  }

  protected async approveSimulated(): Promise<void> {
    const checkout = this.checkout();
    if (!checkout?.simulated_token) return;
    this.error.set(null);
    this.busyLabel.set('Simulating buyer approval…');
    try {
      await firstValueFrom(this.api.simulateApprove(checkout.simulated_token));
      this.holdNotice.set('Buyer approved (simulated). Now capture the payment.');
    } catch (error) {
      this.error.set(present(error));
    } finally {
      this.busyLabel.set(null);
    }
  }

  protected async declineSimulated(): Promise<void> {
    const checkout = this.checkout();
    if (!checkout?.simulated_token) return;
    this.error.set(null);
    this.busyLabel.set('Cancelling the simulated checkout…');
    try {
      await firstValueFrom(this.api.simulateDecline(checkout.simulated_token));
      const payment = await firstValueFrom(this.api.cancelPayment(checkout.attempt_id));
      this.payment.set(payment);
      this.holdNotice.set('Checkout cancelled — no booking was confirmed.');
      this.stopTimer();
      await this.reloadBookings();
    } catch (error) {
      this.error.set(present(error));
    } finally {
      this.busyLabel.set(null);
    }
  }

  protected async capture(): Promise<void> {
    const checkout = this.checkout();
    if (!checkout || this.paying()) return;
    this.error.set(null);
    this.paying.set(true);
    this.busyLabel.set('Verifying the capture with PayPal…');
    try {
      const payment = await firstValueFrom(this.api.capturePayment(checkout.attempt_id));
      this.payment.set(payment);
      this.stopTimer();
      await this.reloadBookings();
    } catch (error) {
      this.error.set(present(error));
    } finally {
      this.paying.set(false);
      this.busyLabel.set(null);
    }
  }

  protected async refreshPayment(): Promise<void> {
    const checkout = this.checkout();
    if (!checkout) return;
    try {
      this.payment.set(await firstValueFrom(this.api.payment(checkout.attempt_id)));
    } catch (error) {
      this.error.set(present(error));
    }
  }

  protected resetPurchase(): void {
    this.hold.set(null);
    this.checkout.set(null);
    this.payment.set(null);
    this.stopTimer();
    this.remaining.set(0);
  }

  // ------------------------------------------------------------ bookings
  protected readonly bookings = signal<BookingInfo[]>([]);
  protected readonly bookingsBusy = signal(false);

  protected async reloadBookings(): Promise<void> {
    this.bookingsBusy.set(true);
    try {
      this.bookings.set(await firstValueFrom(this.api.bookings()));
    } catch (error) {
      this.error.set(present(error));
    } finally {
      this.bookingsBusy.set(false);
    }
  }

  protected onBookingChanged(booking: BookingInfo): void {
    this.bookings.update((list) => list.map((item) => (item.id === booking.id ? booking : item)));
    this.flash.set(`Booking ${booking.reference} is now ${statusLabel(booking.status).toLowerCase()}.`);
    void this.reloadBookings();
  }

  // ------------------------------------------------------------ timer
  private startTimer(seconds: number): void {
    this.stopTimer();
    this.remaining.set(seconds);
    this.timer = setInterval(() => {
      const next = this.remaining() - 1;
      this.remaining.set(next);
      if (next <= 0) {
        this.stopTimer();
        this.holdNotice.set('This hold expired. Pick a slot again.');
        this.hold.set(null);
        void this.search();
      }
    }, 1000);
  }

  private stopTimer(): void {
    if (this.timer !== null) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  // ------------------------------------------------------------ helpers
  protected money(cents: number, currency = 'USD'): string {
    return formatMoney(cents, currency);
  }
  protected clock(seconds: number): string {
    return formatClock(seconds);
  }
  protected dayLabel(day: string): string {
    return day ? formatDayLabel(day) : '';
  }
  protected hasHold(): boolean {
    return this.hold() !== null;
  }
}

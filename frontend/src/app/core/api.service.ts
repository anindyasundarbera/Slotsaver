import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError, throwError } from 'rxjs';

import { environment } from '../../environments';
import {
  AnalyticsInfo,
  ApiErrorBody,
  AppConfig,
  AssistantReply,
  BookingInfo,
  CheckoutInfo,
  DisruptionResult,
  HoldInfo,
  PaymentInfo,
  ServiceInfo,
  TechnicianInfo,
  TimelineInfo,
  AppointmentOption,
} from './models';

export class ApiFailure extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly status: number,
    readonly correlationId: string,
  ) {
    super(message);
    this.name = 'ApiFailure';
  }
}

function readCookie(name: string): string {
  const match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
  return match ? decodeURIComponent(match[1]) : '';
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBase;

  // ---------------------------------------------------------------- plumbing
  private csrf(): Record<string, string> {
    const token = readCookie('ss_csrf');
    return token ? { 'X-CSRF-Token': token } : {};
  }

  private request<T>(method: 'GET' | 'POST' | 'DELETE', path: string, body?: unknown): Observable<T> {
    return this.http
      .request<T>(method, `${this.base}${path}`, {
        body,
        headers: this.csrf(),
        withCredentials: true,
      })
      .pipe(catchError((error: unknown) => this.translate(error)));
  }

  private translate(error: unknown): Observable<never> {
    if (error instanceof HttpErrorResponse) {
      const body = error.error as ApiErrorBody | null;
      const payload = body?.error;
      if (payload?.code) {
        return throwError(
          () => new ApiFailure(payload.code, payload.message, error.status, payload.correlation_id ?? ''),
        );
      }
      const fallback =
        error.status === 0
          ? 'Cannot reach the server. Is the API running?'
          : `Request failed (${error.status}).`;
      return throwError(() => new ApiFailure('HTTP_ERROR', fallback, error.status, ''));
    }
    return throwError(() => new ApiFailure('UNKNOWN', 'Unexpected client error.', 0, ''));
  }

  // ---------------------------------------------------------------- auth
  login(email: string): Observable<{ id: string; email: string; display_name: string; role: string }> {
    return this.request('POST', '/auth/login', { email });
  }
  logout(): Observable<unknown> {
    return this.request('POST', '/auth/logout', {});
  }
  me(): Observable<{ id: string; email: string; display_name: string; role: string }> {
    return this.request('GET', '/auth/me');
  }

  // ---------------------------------------------------------------- public
  config(): Observable<AppConfig> {
    return this.request('GET', '/config');
  }
  services(): Observable<ServiceInfo[]> {
    return this.request('GET', '/services');
  }
  technicians(): Observable<TechnicianInfo[]> {
    return this.request('GET', '/technicians');
  }
  health(): Observable<{ status: string; database: string }> {
    return this.request('GET', '/health');
  }

  // ---------------------------------------------------------------- customer
  assistant(message: string, conversationId: string | null): Observable<AssistantReply> {
    return this.request('POST', '/assistant/message', {
      message,
      conversation_id: conversationId,
    });
  }

  availability(query: {
    serviceCode: string;
    day: string;
    afterLocal?: string | null;
    beforeLocal?: string | null;
    maxPriceCents?: number | null;
  }): Observable<AppointmentOption[]> {
    const params = new URLSearchParams({ service_code: query.serviceCode, day: query.day });
    if (query.afterLocal) params.set('after_local', query.afterLocal);
    if (query.beforeLocal) params.set('before_local', query.beforeLocal);
    if (query.maxPriceCents != null) params.set('max_price_cents', String(query.maxPriceCents));
    return this.request('GET', `/availability?${params.toString()}`);
  }

  createHold(payload: {
    service_code: string;
    technician_id: string;
    start_utc: string;
    notes?: string;
  }): Observable<HoldInfo> {
    return this.request('POST', '/holds', payload);
  }

  releaseHold(holdId: string): Observable<BookingInfo> {
    return this.request('DELETE', `/holds/${holdId}`);
  }

  startCheckout(holdId: string): Observable<CheckoutInfo> {
    return this.request('POST', `/holds/${holdId}/checkout`, {});
  }

  capturePayment(attemptId: string): Observable<PaymentInfo> {
    return this.request('POST', `/payments/${attemptId}/capture`, {});
  }

  cancelPayment(attemptId: string): Observable<PaymentInfo> {
    return this.request('POST', `/payments/${attemptId}/cancel`, {});
  }

  payment(attemptId: string): Observable<PaymentInfo> {
    return this.request('GET', `/payments/${attemptId}`);
  }

  simulateApprove(orderId: string): Observable<{ order_id: string; status: string }> {
    return this.request('POST', `/simulated-checkout/${orderId}/approve`, {});
  }

  simulateDecline(orderId: string): Observable<{ order_id: string; status: string }> {
    return this.request('POST', `/simulated-checkout/${orderId}/decline`, {});
  }

  bookings(): Observable<BookingInfo[]> {
    return this.request('GET', '/bookings');
  }

  booking(id: string): Observable<BookingInfo> {
    return this.request('GET', `/bookings/${id}`);
  }

  approveReassignment(bookingId: string, proposalId: string, technicianId: string): Observable<BookingInfo> {
    return this.request('POST', `/bookings/${bookingId}/reassignment/approve`, {
      proposal_id: proposalId,
      technician_id: technicianId,
    });
  }

  declineReassignment(bookingId: string, proposalId: string): Observable<BookingInfo> {
    return this.request('POST', `/bookings/${bookingId}/reassignment/decline`, {
      proposal_id: proposalId,
    });
  }

  // ---------------------------------------------------------------- owner
  timeline(day?: string): Observable<TimelineInfo> {
    return this.request('GET', `/owner/timeline${day ? `?day=${day}` : ''}`);
  }

  analytics(dateFrom?: string, dateTo?: string): Observable<AnalyticsInfo> {
    const params = new URLSearchParams();
    if (dateFrom) params.set('date_from', dateFrom);
    if (dateTo) params.set('date_to', dateTo);
    const qs = params.toString();
    return this.request('GET', `/owner/analytics${qs ? `?${qs}` : ''}`);
  }

  allBookings(status?: string): Observable<BookingInfo[]> {
    return this.request('GET', `/owner/bookings${status ? `?status=${status}` : ''}`);
  }

  markUnavailable(payload: {
    technician_id: string;
    start_utc: string;
    end_utc: string;
    reason: string;
  }): Observable<DisruptionResult> {
    const { technician_id, ...body } = payload;
    return this.request('POST', `/owner/technicians/${technician_id}/unavailable`, body);
  }

  resolveException(
    bookingId: string,
    resolution: 'cancelled' | 'confirmed_manually',
    note: string,
  ): Observable<BookingInfo> {
    return this.request('POST', `/owner/bookings/${bookingId}/resolve-exception`, {
      resolution,
      note,
    });
  }

  audit(limit = 40): Observable<
    Array<{
      at: string;
      action: string;
      actor_role: string;
      subject_type: string;
      subject_id: string;
      detail: Record<string, unknown>;
    }>
  > {
    return this.request('GET', `/owner/audit?limit=${limit}`);
  }
}

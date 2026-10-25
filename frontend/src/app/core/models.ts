export type Role = 'customer' | 'owner';
export type PaypalMode = 'simulated' | 'sandbox';
export type AssistantMode = 'scripted' | 'llm';
export type BookingStatus =
  | 'held'
  | 'awaiting_payment'
  | 'confirmed'
  | 'needs_reassignment'
  | 'payment_exception'
  | 'cancelled'
  | 'expired';

export interface DemoUser {
  email: string;
  display_name: string;
  role: string;
  hint: string;
}

export interface AppConfig {
  business_name: string;
  timezone: string;
  timezone_label: string;
  currency: string;
  demo_date: string;
  hold_ttl_minutes: number;
  paypal_mode: PaypalMode;
  assistant_mode: AssistantMode;
  demo_users: DemoUser[];
  supports_webhooks: boolean;
}

export interface ServiceInfo {
  id: string;
  code: string;
  name: string;
  duration_minutes: number;
  price_cents: number;
  currency: string;
  required_skill: string;
  description: string;
}

export interface TechnicianInfo {
  id: string;
  name: string;
  initials: string;
  skills: string[];
  color: string;
}

export interface AppointmentOption {
  option_id: string;
  technician_id: string;
  technician_name: string;
  technician_color: string;
  service_id: string;
  service_code: string;
  service_name: string;
  start_utc: string;
  end_utc: string;
  start_local: string;
  end_local: string;
  timezone_label: string;
  price_cents: number;
  currency: string;
  duration_minutes: number;
  within_budget: boolean;
}

export interface HoldInfo {
  id: string;
  status: string;
  technician_id: string;
  technician_name: string;
  service_name: string;
  start_utc: string;
  end_utc: string;
  start_local: string;
  end_local: string;
  timezone_label: string;
  price_cents: number;
  currency: string;
  expires_at: string;
  seconds_remaining: number;
  booking_id: string;
}

export interface ToolTrace {
  tool: string;
  summary: string;
  ok: boolean;
  redacted: boolean;
}

export interface AssistantReply {
  reply: string;
  conversation_id: string;
  constraints: Record<string, unknown>;
  options: AppointmentOption[];
  needs_clarification: boolean;
  clarification_question: string | null;
  tool_trace: ToolTrace[];
  fallback_required: boolean;
  fallback_reason: string | null;
  mode: AssistantMode;
}

export interface CheckoutInfo {
  attempt_id: string;
  booking_id: string;
  status: string;
  provider_mode: PaypalMode;
  amount_cents: number;
  currency: string;
  approve_url: string | null;
  simulated_token: string | null;
  expires_at: string;
}

export interface PaymentInfo {
  attempt_id: string;
  booking_id: string;
  status: string;
  provider_mode: string;
  amount_cents: number;
  captured_amount_cents: number | null;
  currency: string;
  failure_reason: string;
  booking_status: string;
}

export interface ProposalCandidate {
  technician_id: string;
  technician_name: string;
  technician_color: string;
  available: boolean;
  note: string;
}

export interface ProposalInfo {
  id: string;
  status: string;
  reason: string;
  original_technician_id: string;
  created_at: string;
  candidates: ProposalCandidate[];
}

export interface BookingInfo {
  id: string;
  reference: string;
  status: BookingStatus;
  status_label: string;
  technician_id: string;
  technician_name: string;
  technician_color: string;
  service_name: string;
  service_code: string;
  start_utc: string;
  end_utc: string;
  start_local: string;
  end_local: string;
  timezone_label: string;
  price_cents: number;
  currency: string;
  notes: string;
  customer_name: string;
  needs_attention: boolean;
  exception_reason: string;
  created_at: string;
  confirmed_at: string | null;
  payment_status: string | null;
  proposal: ProposalInfo | null;
}

export interface TimelineEvent {
  id: string;
  kind: 'hold' | 'booking' | 'block';
  technician_id: string;
  title: string;
  start_utc: string;
  end_utc: string;
  status: string;
  status_label: string;
  color: string;
  customer_name: string | null;
  service_name: string | null;
  reference: string | null;
  price_cents: number | null;
  needs_attention: boolean;
}

export interface TimelineInfo {
  day: string;
  timezone_label: string;
  technicians: TechnicianInfo[];
  events: TimelineEvent[];
  generated_at: string;
}

export interface AnalyticsBucket {
  key: string;
  label: string;
  booking_count: number;
  revenue_cents: number;
}

export interface AnalyticsRow {
  booking_id: string;
  reference: string;
  status: string;
  status_label: string;
  service_name: string;
  technician_name: string;
  customer_name: string;
  day: string;
  start_local: string;
  price_cents: number;
  currency: string;
  counted_as_revenue: boolean;
  needs_attention: boolean;
  exception_reason: string;
}

export interface AnalyticsInfo {
  date_from: string;
  date_to: string;
  currency: string;
  confirmed_count: number;
  confirmed_revenue_cents: number;
  captured_all_cents: number;
  exception_cents: number;
  exception_count: number;
  needs_reassignment_count: number;
  by_service: AnalyticsBucket[];
  by_technician: AnalyticsBucket[];
  by_status: AnalyticsBucket[];
  rows: AnalyticsRow[];
  notes: string[];
}

export interface DisruptionResult {
  block_id: string;
  technician_id: string;
  technician_name: string;
  affected_booking_ids: string[];
  proposals_created: string[];
  unresolved_booking_ids: string[];
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    correlation_id: string;
    details?: Record<string, unknown>;
  };
}

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, UtcDateTime, utcnow


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


class Role(str, enum.Enum):
    customer = "customer"
    owner = "owner"


class BookingStatus(str, enum.Enum):
    held = "held"
    awaiting_payment = "awaiting_payment"
    confirmed = "confirmed"
    needs_reassignment = "needs_reassignment"
    payment_exception = "payment_exception"
    cancelled = "cancelled"
    expired = "expired"


class HoldStatus(str, enum.Enum):
    active = "active"
    consumed = "consumed"
    released = "released"
    expired = "expired"


class AttemptStatus(str, enum.Enum):
    created = "created"
    approved = "approved"
    captured = "captured"
    reconciled_ok = "reconciled_ok"
    reconciled_exception = "reconciled_exception"
    cancelled = "cancelled"
    failed = "failed"


class ProposalStatus(str, enum.Enum):
    proposed = "proposed"
    accepted = "accepted"
    declined = "declined"
    unresolved = "unresolved"
    superseded = "superseded"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("usr"))
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20), default=Role.customer.value)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("ses"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime())
    revoked_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)

    user: Mapped[User] = relationship(lazy="joined")


class DemoClock(Base):
    """Single-row demo clock. Business dates derive from this, never from the wall clock."""

    __tablename__ = "demo_clock"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    demo_date: Mapped[str] = mapped_column(String(10))
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)


class Service(Base):
    __tablename__ = "services"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("svc"))
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    duration_minutes: Mapped[int] = mapped_column(Integer)
    price_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    required_skill: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (
        UniqueConstraint("code", name="ux_services_code"),
    )


class Technician(Base):
    __tablename__ = "technicians"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("tec"))
    name: Mapped[str] = mapped_column(String(120))
    initials: Mapped[str] = mapped_column(String(4))
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    color: Mapped[str] = mapped_column(String(20), default="#2563eb")
    timezone: Mapped[str] = mapped_column(String(64), default="America/New_York")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class TechnicianBlock(Base):
    __tablename__ = "technician_blocks"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("blk"))
    technician_id: Mapped[str] = mapped_column(ForeignKey("technicians.id"), index=True)
    start_utc: Mapped[datetime] = mapped_column(UtcDateTime())
    end_utc: Mapped[datetime] = mapped_column(UtcDateTime())
    reason: Mapped[str] = mapped_column(String(200), default="")
    created_by: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)

    __table_args__ = (
        Index("ix_technician_blocks_window", "technician_id", "start_utc", "end_utc"),
    )


class Hold(Base):
    __tablename__ = "holds"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("hold"))
    customer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    technician_id: Mapped[str] = mapped_column(ForeignKey("technicians.id"), index=True)
    service_id: Mapped[str] = mapped_column(ForeignKey("services.id"))
    start_utc: Mapped[datetime] = mapped_column(UtcDateTime())
    end_utc: Mapped[datetime] = mapped_column(UtcDateTime())
    price_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    status: Mapped[str] = mapped_column(String(24), default=HoldStatus.active.value, index=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime(), index=True)

    service: Mapped[Service] = relationship(lazy="joined")
    technician: Mapped[Technician] = relationship(lazy="joined")


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("bkg"))
    reference: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    technician_id: Mapped[str] = mapped_column(ForeignKey("technicians.id"), index=True)
    service_id: Mapped[str] = mapped_column(ForeignKey("services.id"))
    hold_id: Mapped[str | None] = mapped_column(ForeignKey("holds.id"), nullable=True)
    start_utc: Mapped[datetime] = mapped_column(UtcDateTime())
    end_utc: Mapped[datetime] = mapped_column(UtcDateTime())
    price_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    status: Mapped[str] = mapped_column(
        String(24), default=BookingStatus.held.value, index=True
    )
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, onupdate=utcnow)
    confirmed_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    exception_reason: Mapped[str] = mapped_column(String(240), default="")
    needs_attention: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    service: Mapped[Service] = relationship(lazy="joined")
    technician: Mapped[Technician] = relationship(lazy="joined")
    customer: Mapped[User] = relationship(lazy="joined")

    __table_args__ = (
        Index("ix_bookings_technician_time", "technician_id", "start_utc"),
        Index("ix_bookings_customer_created", "customer_id", "created_at"),
    )


class SlotBlock(Base):
    """30-minute capacity cell. Partial unique index is the concurrency primitive."""

    __tablename__ = "slot_blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    technician_id: Mapped[str] = mapped_column(ForeignKey("technicians.id"), index=True)
    slot_start_utc: Mapped[datetime] = mapped_column(UtcDateTime())
    owner_kind: Mapped[str] = mapped_column(String(16))
    owner_id: Mapped[str] = mapped_column(String(40), index=True)
    active: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)

    __table_args__ = (
        Index(
            "ux_slot_blocks_active",
            "technician_id",
            "slot_start_utc",
            unique=True,
            sqlite_where=text("active = 1"),
            postgresql_where=text("active = 1"),
        ),
        Index("ix_slot_blocks_owner", "owner_kind", "owner_id"),
    )


class PaymentAttempt(Base):
    __tablename__ = "payment_attempts"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("pay"))
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), index=True)
    hold_id: Mapped[str] = mapped_column(ForeignKey("holds.id"), index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    provider: Mapped[str] = mapped_column(String(20), default="paypal")
    provider_mode: Mapped[str] = mapped_column(String(20), default="simulated")
    provider_order_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    provider_capture_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    expected_amount_cents: Mapped[int] = mapped_column(Integer)
    captured_amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    status: Mapped[str] = mapped_column(String(24), default=AttemptStatus.created.value, index=True)
    failure_reason: Mapped[str] = mapped_column(String(240), default="")
    raw_status: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, onupdate=utcnow)
    captured_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)


class ProcessedPaymentEvent(Base):
    __tablename__ = "processed_payment_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), default="")
    signature_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    processed_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    note: Mapped[str] = mapped_column(String(240), default="")


class ReassignmentProposal(Base):
    __tablename__ = "reassignment_proposals"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("rsp"))
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), index=True)
    original_technician_id: Mapped[str] = mapped_column(String(40))
    candidates: Mapped[list[dict]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(
        String(20), default=ProposalStatus.proposed.value, index=True
    )
    reason: Mapped[str] = mapped_column(String(200), default="")
    created_by: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    accepted_technician_id: Mapped[str | None] = mapped_column(String(40), nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, index=True)
    actor_id: Mapped[str] = mapped_column(String(40), default="")
    actor_role: Mapped[str] = mapped_column(String(20), default="")
    action: Mapped[str] = mapped_column(String(60), index=True)
    subject_type: Mapped[str] = mapped_column(String(30), default="")
    subject_id: Mapped[str] = mapped_column(String(40), default="", index=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    correlation_id: Mapped[str] = mapped_column(String(40), default="")

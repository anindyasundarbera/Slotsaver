export function formatMoney(cents: number, currency = 'USD'): string {
  const value = (cents / 100).toFixed(2);
  return `$${value} ${currency}`;
}

export function formatMoneyShort(cents: number): string {
  return `$${(cents / 100).toFixed(cents % 100 === 0 ? 0 : 2)}`;
}

export function statusTone(status: string): string {
  switch (status) {
    case 'held':
      return 'tone-held';
    case 'awaiting_payment':
      return 'tone-awaiting';
    case 'confirmed':
      return 'tone-confirmed';
    case 'needs_reassignment':
      return 'tone-danger';
    case 'payment_exception':
      return 'tone-exception';
    case 'unavailable':
      return 'tone-neutral';
    default:
      return 'tone-neutral';
  }
}

export function statusLabel(status: string): string {
  switch (status) {
    case 'held':
      return 'Held';
    case 'awaiting_payment':
      return 'Awaiting payment';
    case 'confirmed':
      return 'Confirmed';
    case 'needs_reassignment':
      return 'Needs reassignment';
    case 'payment_exception':
      return 'Payment exception';
    case 'cancelled':
      return 'Cancelled';
    case 'expired':
      return 'Expired';
    case 'unavailable':
      return 'Unavailable';
    default:
      return status;
  }
}

/** Build an ISO-8601 instant with an explicit offset for a wall-clock time in `timeZone`. */
export function zonedIso(day: string, time: string, timeZone: string): string {
  const [year, month, date] = day.split('-').map(Number);
  const [hour, minute] = time.split(':').map(Number);
  const utcGuess = Date.UTC(year, month - 1, date, hour, minute, 0);
  const offsetMs = tzOffsetMs(new Date(utcGuess), timeZone);
  const actual = new Date(utcGuess - offsetMs);
  const finalOffset = tzOffsetMs(actual, timeZone);
  return new Date(utcGuess - finalOffset).toISOString();
}

function tzOffsetMs(at: Date, timeZone: string): number {
  const formatter = new Intl.DateTimeFormat('en-US', {
    timeZone,
    hour12: false,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
  const parts = formatter.formatToParts(at).reduce<Record<string, string>>((acc, part) => {
    if (part.type !== 'literal') acc[part.type] = part.value;
    return acc;
  }, {});
  const asUtc = Date.UTC(
    Number(parts['year']),
    Number(parts['month']) - 1,
    Number(parts['day']),
    Number(parts['hour']) % 24,
    Number(parts['minute']),
    Number(parts['second']),
  );
  return asUtc - at.getTime();
}

export function addBusinessDays(day: string, count: number): string {
  const date = new Date(`${day}T12:00:00Z`);
  let remaining = Math.abs(count);
  const step = count < 0 ? -1 : 1;
  while (remaining > 0) {
    date.setUTCDate(date.getUTCDate() + step);
    const weekday = date.getUTCDay();
    if (weekday !== 0) remaining -= 1;
  }
  return date.toISOString().slice(0, 10);
}

export function shiftDays(day: string, count: number): string {
  const date = new Date(`${day}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + count);
  return date.toISOString().slice(0, 10);
}

export function formatDayLabel(day: string): string {
  const date = new Date(`${day}T12:00:00Z`);
  return new Intl.DateTimeFormat('en-US', {
    weekday: 'short',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(date);
}

export function formatClock(totalSeconds: number): string {
  const safe = Math.max(0, Math.floor(totalSeconds));
  const minutes = Math.floor(safe / 60);
  const seconds = safe % 60;
  return `${minutes}:${seconds.toString().padStart(2, '0')}`;
}

/**
 * Public, browser-safe configuration only.
 *
 * Values here are compiled into the bundle, so never put a secret in this file.
 * The backend deliberately exposes nothing sensitive through /api/config either.
 */
export const environment = {
  apiBase: '/api',
  businessTimezoneFallback: 'America/New_York',
} as const;

import { ApiFailure } from './api.service';

export interface PresentedError {
  message: string;
  correlationId: string;
  code: string;
}

export function present(error: unknown): PresentedError {
  if (error instanceof ApiFailure) {
    return { message: error.message, correlationId: error.correlationId, code: error.code };
  }
  if (error instanceof Error) {
    return { message: error.message, correlationId: '', code: 'CLIENT_ERROR' };
  }
  return { message: 'Something went wrong.', correlationId: '', code: 'UNKNOWN' };
}

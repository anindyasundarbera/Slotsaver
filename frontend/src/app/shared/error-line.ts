import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { PresentedError } from '../core/errors';

@Component({
  selector: 'ss-error-line',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (error(); as err) {
      <div class="notice notice-error" role="alert">
        <span class="notice-icon" aria-hidden="true">!</span>
        <div class="stack-sm">
          <span>{{ err.message }}</span>
          @if (err.correlationId) {
            <span class="mono muted">Correlation ID {{ err.correlationId }}</span>
          }
        </div>
      </div>
    }
  `,
})
export class ErrorLine {
  readonly error = input<PresentedError | null>(null);
}

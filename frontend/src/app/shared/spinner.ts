import { ChangeDetectionStrategy, Component, input } from '@angular/core';

@Component({
  selector: 'ss-spinner',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span class="row-tight" role="status"><span class="spinner" aria-hidden="true"></span>
    <span class="small muted">{{ label() }}</span></span>`,
})
export class Spinner {
  readonly label = input('Loading…');
}

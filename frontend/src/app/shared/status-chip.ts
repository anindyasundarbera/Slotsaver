import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { statusLabel, statusTone } from '../core/format';

@Component({
  selector: 'ss-status-chip',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span class="status-chip" [class]="tone()">{{ label() }}</span>`,
  styles: [':host { display: inline-flex; }'],
})
export class StatusChip {
  readonly status = input.required<string>();
  readonly labelOverride = input<string | null>(null);

  tone(): string {
    return statusTone(this.status());
  }
  label(): string {
    return this.labelOverride() ?? statusLabel(this.status());
  }
}

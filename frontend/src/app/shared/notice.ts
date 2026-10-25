import { ChangeDetectionStrategy, Component, input } from '@angular/core';

const ICONS: Record<string, string> = {
  info: 'i',
  success: '✓',
  warn: '!',
  error: '!',
  exception: '!',
};

@Component({
  selector: 'ss-notice',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="notice notice-{{ tone() }}" [attr.role]="tone() === 'error' ? 'alert' : null">
      <span class="notice-icon" aria-hidden="true">{{ icon() }}</span>
      <div class="stack-sm">
        @if (title()) {
          <strong>{{ title() }}</strong>
        }
        <span><ng-content /></span>
      </div>
    </div>
  `,
})
export class Notice {
  readonly tone = input<'info' | 'success' | 'warn' | 'error' | 'exception'>('info');
  readonly title = input<string | null>(null);
  icon(): string {
    return ICONS[this.tone()] ?? 'i';
  }
}

import { ChangeDetectionStrategy, Component, OnInit, inject } from '@angular/core';
import { RouterLink, RouterOutlet } from '@angular/router';

import { SessionStore } from './core/session.store';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink],
  templateUrl: './app.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class App implements OnInit {
  protected readonly session = inject(SessionStore);

  ngOnInit(): void {
    void this.session.bootstrap();
  }

  protected async signOut(): Promise<void> {
    await this.session.signOut();
  }
}

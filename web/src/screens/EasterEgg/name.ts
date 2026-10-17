import type { Nav } from '../../routes';
import { blockedPlayerNameReason } from '../../lib/playerNamePolicy';

/** Check completed entries rather than keystrokes, so ordinary longer names remain usable. */
export function nameEasterEgg(nav: Pick<Nav, 'go'>, ...names: string[]): boolean {
  for (const name of names) {
    const reason = blockedPlayerNameReason(name);
    if (!reason) continue;
    nav.go({ name: 'zibran', playerName: reason === 'joke' ? name.trim() : undefined, reason });
    return true;
  }
  return false;
}

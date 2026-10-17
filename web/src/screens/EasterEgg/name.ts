import type { Nav } from '../../routes';

/** Check completed name entries, not every keystroke, so prefixes like zibran123 still work. */
export function nameEasterEgg(nav: Pick<Nav, 'go'>, ...names: string[]): boolean {
  if (!names.some(name => name.trim().toLowerCase() === 'zibran')) return false;
  nav.go({ name: 'zibran' });
  return true;
}

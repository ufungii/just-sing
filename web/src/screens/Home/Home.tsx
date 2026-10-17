import { useEffect, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import { BoomboxKun, MicChan, PixelSky } from '../../components/pixel';
import { useAccount } from '../../lib/auth';
import { PixelButton } from '../../ui';
import { PixelIcon } from '../../ui/PixelIcon';
import type { IconName } from '../../ui/PixelIcon';
import { ProfileDialog } from '../../components/players/ProfileDialog';
import { SettingsDialog } from '../../components/settings/SettingsDialog';
import type { Screen } from '../../screens';
import { KeyCard } from './KeyCard';
import type { KeyCardProps } from './KeyCard';
import { PixelLogo } from './PixelLogo';
import './Home.css';

type CardDef = Pick<KeyCardProps, 'title' | 'sub' | 'kao' | 'icon' | 'color'> & { to: Screen };

// Kaomoji here use only characters the bundled DotGothic16 subset contains (no ω, ◕, ✧, ⋆, ₊),
// otherwise the browser falls back to another font for single glyphs and they look broken.
// Solo karaoke and pronunciation practice come first, per CLAUDE.md.
const CARDS: CardDef[] = [
  {
    to: 'solo',
    title: 'SOLO SING',
    sub: 'pick a clip, sing along, get rated every phrase',
    kao: '(ﾉ≧▽≦)ﾉ*:･˚☆',
    icon: 'mic',
    color: 'pink',
  },
  {
    to: 'practice',
    title: 'SAY IT RIGHT',
    sub: '발음 연습 · speak a lyric, get word-by-word feedback',
    kao: '＼(^o^)／ ˚｡♪',
    icon: 'say',
    color: 'mint',
  },
  {
    to: 'battle',
    title: '1P VS 2P',
    sub: 'take turns on one laptop, same clip, same rules',
    kao: '(｀∀´)ﾉ☆ヽ(＾▽＾)',
    icon: 'versus',
    color: 'sky',
  },
  {
    to: 'online',
    title: 'ONLINE',
    sub: 'make a room, send the code, sing against a friend',
    kao: '(＾▽＾)ﾉ ⇄ ヽ(＾▽＾)',
    icon: 'versus',
    color: 'lav',
  },
];

/** Top-right corner buttons, left to right. History is a screen; the other two open dialogs. */
const CORNER: { icon: IconName; label: string }[] = [
  { icon: 'profile', label: 'PLAYERS' },
  { icon: 'history', label: 'HISTORY' },
  { icon: 'settings', label: 'SETTINGS' },
];

/** Long enough for the keycap to visibly press in before the screen changes. */
const PRESS_MS = 120;

/** Number of grid columns the menu is currently laid out in, so Up/Down can move by a row. */
function columnCount(grid: HTMLElement | null): number {
  if (!grid) return 1;
  return Math.max(1, getComputedStyle(grid).gridTemplateColumns.split(' ').filter(Boolean).length);
}

/** Title menu: logo, mascots, four keycap cards, and the players / history / settings corner. */
export function Home({ onNavigate }: { onNavigate: (screen: Screen) => void }) {
  const account = useAccount();
  const [dialog, setDialog] = useState<'players' | 'settings' | null>(null);
  const onCorner = (icon: IconName) => {
    if (icon === 'history') onNavigate('history');
    else setDialog(icon === 'profile' ? 'players' : 'settings');
  };
  const [sel, setSel] = useState(0);
  const [pressed, setPressed] = useState<number | null>(null);
  const gridRef = useRef<HTMLElement>(null);
  const cardRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const pressTimer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearTimeout(pressTimer.current), []);

  // Arcade feel: arrow keys work straight away, before anything has focus.
  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (document.activeElement && document.activeElement !== document.body) return;
      if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(e.key)) return;
      e.preventDefault();
      cardRefs.current[sel]?.focus();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [sel]);

  const activate = (i: number) => {
    if (pressed !== null) return;
    setSel(i);
    setPressed(i);
    pressTimer.current = window.setTimeout(() => onNavigate(CARDS[i].to), PRESS_MS);
  };

  const move = (to: number) => {
    const next = (to + CARDS.length) % CARDS.length;
    setSel(next);
    cardRefs.current[next]?.focus();
  };

  const onCardKey = (i: number) => (e: KeyboardEvent<HTMLButtonElement>) => {
    const cols = columnCount(gridRef.current);
    const step: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -cols, ArrowDown: cols };
    if (e.key in step) {
      e.preventDefault();
      move(i + step[e.key]);
    } else if (e.key === 'Home' || e.key === 'End') {
      e.preventDefault();
      move(e.key === 'Home' ? 0 : CARDS.length - 1);
    } else if (e.key === 'Enter' || e.key === ' ') {
      // Handle both keys here (not via the native click) so they share the press animation.
      e.preventDefault();
      activate(i);
    }
  };

  return (
    <main className="home">
      <PixelSky />
      <div className="home-frame" aria-hidden="true" />

      <nav className="home-corner" aria-label="Players, history and settings">
        {CORNER.map((c) => (
          <button key={c.icon} type="button" className="home-corner__btn" title={c.label} onClick={() => onCorner(c.icon)}>
            <PixelIcon name={c.icon} size={30} />
            <span className="home-corner__label">{c.label}</span>
          </button>
        ))}
      </nav>
      <ProfileDialog open={dialog === 'players'} onClose={() => setDialog(null)} />
      <SettingsDialog open={dialog === 'settings'} onClose={() => setDialog(null)} />

      <div className="home-inner">
        {account.enabled && !account.loading && (
          <header className="home-header">
            <div className="home-account">
              {account.name ? (
                <>
                  <span>signed in as {account.name}</span>
                  <PixelButton size="sm" tone="paper" onClick={account.logout}>LOG OUT</PixelButton>
                </>
              ) : (
                <>
                  <span>playing as guest</span>
                  <PixelButton size="sm" tone="sky" onClick={account.login}>LOG IN</PixelButton>
                </>
              )}
            </div>
          </header>
        )}

        <section className="home-hero">
          {/* Three columns: the mascots sit in their own cells, so poking one never moves the title. */}
          <div className="home-stage">
            <div className="home-stage__side home-stage__side--left">
              <MicChan className="home-mascot" />
            </div>

            <PixelLogo />

            <div className="home-stage__side home-stage__side--right">
              <BoomboxKun className="home-mascot" />
            </div>
          </div>

          {/* Plain text, not a box: nothing here is clickable. */}
          <p className="home-pop">
            <span lang="ko" className="home-pop__ko">
              노래해요!
            </span>
            <span className="home-pop__en">K-POP KARAOKE</span>
            <span className="home-kao home-kao--soft" aria-hidden="true">
              ヾ(≧▽≦*)o
            </span>
          </p>
          <p className="home-tagline">
            <span className="home-kao home-kao--hot" aria-hidden="true">
              ☆˚･♡
            </span>{' '}
            pick a clip · sing along · pitch + timing make your score{' '}
            <span className="home-kao home-kao--hot" aria-hidden="true">
              ♡･˚☆
            </span>
          </p>
        </section>

        <nav aria-label="Main menu" className="home-menu" ref={gridRef}>
          {CARDS.map((c, i) => (
            <KeyCard
              key={c.to}
              ref={(el) => {
                cardRefs.current[i] = el;
              }}
              title={c.title}
              sub={c.sub}
              kao={c.kao}
              icon={c.icon}
              color={c.color}
              selected={sel === i}
              pressed={pressed === i}
              onSelect={() => setSel(i)}
              onActivate={() => activate(i)}
              onKeyDown={onCardKey(i)}
            />
          ))}
        </nav>

      </div>
    </main>
  );
}

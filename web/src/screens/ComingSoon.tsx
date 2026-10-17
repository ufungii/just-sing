import type { Screen } from '../screens';

const NAMES: Record<Exclude<Screen, 'home'>, string> = {
  solo: 'Solo Sing',
  practice: 'Say It Right',
  battle: '1P vs 2P',
  history: 'History',
};

/** Placeholder for screens that are not built yet, so the menu never leads to a dead end. */
export function ComingSoon({ screen, onBack }: { screen: Exclude<Screen, 'home'>; onBack: () => void }) {
  return (
    <main style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 24, textAlign: 'center' }}>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 18 }}>
        <span style={{ fontFamily: 'var(--font-kao)', fontSize: 32, color: 'var(--hot)' }}>(,,&gt;﹏&lt;,,)</span>
        <h1 style={{ margin: 0, fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 40 }}>{NAMES[screen]}</h1>
        <p style={{ margin: 0, fontSize: 20 }}>still under construction <span style={{ fontFamily: 'var(--font-kao)' }}>☆˚･♡</span></p>
        <button
          type="button"
          onClick={onBack}
          style={{
            fontFamily: 'var(--font-display)',
            fontWeight: 700,
            fontSize: 18,
            padding: '12px 22px',
            background: 'var(--paper)',
            border: 'var(--border-thin) solid var(--ink)',
            boxShadow: '6px 7px 0 var(--ink)',
          }}
        >
          ◀ BACK
        </button>
      </div>
    </main>
  );
}

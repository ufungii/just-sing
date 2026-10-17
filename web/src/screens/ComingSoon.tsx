import { useNav } from '../routes';
import { Notice, Panel, PixelButton, ScreenShell } from '../ui';

/**
 * 1P vs 2P battle. Deferred on purpose: CLAUDE.md says no battle UI until solo karaoke and
 * spoken practice work end to end. The menu card stays so the plan is visible.
 */
export function ComingSoon() {
  const nav = useNav();
  return (
    <ScreenShell title="1P VS 2P" kao="(｀∀´)ﾉ☆ヽ(＾▽＾)">
      <Panel tone="sky" label="COMING SOON">
        <p style={{ margin: '0 0 18px', fontSize: 20 }}>
          Two singers take turns on the same clip under the same rules, and the higher total wins.
          It unlocks once solo singing and Say It Right are finished.
        </p>
        <Notice tone="info">Warm up in the meantime ♪</Notice>
        <div style={{ display: 'flex', gap: 18, marginTop: 22, flexWrap: 'wrap' }}>
          <PixelButton tone="hot" size="lg" onClick={() => nav.go({ name: 'solo' })}>
            ♪ SOLO SING
          </PixelButton>
          <PixelButton tone="mint" size="lg" onClick={() => nav.go({ name: 'practice' })}>
            SAY IT RIGHT
          </PixelButton>
        </div>
      </Panel>
    </ScreenShell>
  );
}

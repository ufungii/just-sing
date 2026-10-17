import { MicChan } from '../../components/pixel';
import { useNav } from '../../routes';
import { Panel, PixelButton, ScreenShell } from '../../ui';

/** A local joke screen: no account moderation, server calls, or persistent lockout. */
export function Zibran() {
  const nav = useNav();
  return (
    <ScreenShell title="ACCESS DENIED" kao="(¬_¬)">
      <Panel tone="pink" label="ERROR Z1BR4N">
        <MicChan />
        <h2>ZIBRAN HAS BEEN BANNED.</h2>
        <p>The karaoke council has reviewed your application. Absolutely not.</p>
        <p>Ban duration: until you press this button.</p>
        <PixelButton tone="hot" size="lg" onClick={nav.home}>APPEAL BAN ♪</PixelButton>
      </Panel>
    </ScreenShell>
  );
}

import { MicChan } from '../../components/pixel';
import { useNav } from '../../routes';
import { Panel, PixelButton, ScreenShell } from '../../ui';

/** A local joke screen: no account moderation, server calls, or persistent lockout. */
export function Zibran() {
  const nav = useNav();
  const route = nav.route.name === 'zibran' ? nav.route : null;
  const language = route?.reason === 'language';
  const name = (route?.playerName ?? 'Zibran').toUpperCase();
  return (
    <ScreenShell title="ACCESS DENIED" kao="(¬_¬)">
      <Panel tone="pink" label={language ? "NAME BLOCKED" : "ACCESS DENIED"}>
        <MicChan />
        <h2>{language ? "THIS NAME IS NOT ALLOWED." : `${name} HAS BEEN BANNED.`}</h2>
        <p>{language ? "Choose a player name without profanity or slurs." : "The karaoke council has reviewed your application. Absolutely not."}</p>
        {!language && <p>Ban duration: until you press this button.</p>}
        <PixelButton tone="hot" size="lg" onClick={nav.home}>{language ? "CHANGE NAME" : "APPEAL BAN ♪"}</PixelButton>
      </Panel>
    </ScreenShell>
  );
}

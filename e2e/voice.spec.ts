import { chromium, expect, test, type Page } from '@playwright/test';
import { duetPlayer, expectOwnedScores, openOnlineDuet, schedules, joinListedRoom } from './duetHarness';

/** Inspect actual decoded WebRTC audio, separately from the application's listening gain. */
async function observeVoice(page: Page) {
  await page.addInitScript(() => {
    const w = window as any;
    w.__voicePeers = [];
    w.__voiceSockets = [];
    w.__voiceSources = [];
    w.__voiceGains = [];
    const source = AudioContext.prototype.createMediaStreamSource;
    AudioContext.prototype.createMediaStreamSource = function (stream) {
      const node = source.call(this, stream); w.__voiceSources.push(node); return node;
    };
    const gain = AudioContext.prototype.createGain;
    AudioContext.prototype.createGain = function () {
      const node = gain.call(this); w.__voiceGains.push(node); return node;
    };
    const Peer = RTCPeerConnection;
    window.RTCPeerConnection = class extends Peer {
      constructor(config?: RTCConfiguration) {
        super(config);
        w.__voicePeers.push(this);
        this.addEventListener('track', ({ track }) => {
          const ctx = new AudioContext();
          void ctx.resume();
          const analyser = ctx.createAnalyser(); analyser.fftSize = 2048;
          const silent = ctx.createGain(); silent.gain.value = 0;
          ctx.createMediaStreamSource(new MediaStream([track])).connect(analyser).connect(silent).connect(ctx.destination);
          w.__voiceRms = () => {
            const samples = new Float32Array(analyser.fftSize); analyser.getFloatTimeDomainData(samples);
            return Math.sqrt(samples.reduce((sum, n) => sum + n * n, 0) / samples.length);
          };
        });
      }
    };
    const Socket = WebSocket;
    window.WebSocket = class extends Socket {
      constructor(url: string | URL, protocols?: string | string[]) {
        super(url, protocols); w.__voiceSockets.push(this);
      }
    };
  });
}
const rms = (page: Page) => page.evaluate(() => (window as any).__voiceRms?.() ?? Number.POSITIVE_INFINITY);
const status = (page: Page) => page.getByTestId('voice-status');

test('live voice: real peer audio, private count-in, section handoff, mute, socket recovery and teardown', async ({ baseURL }) => {
  const browser = await chromium.launch({ args: ['--autoplay-policy=no-user-gesture-required'] });
  try {
    const { page: host, errors: hostErrors } = await duetPlayer(browser, baseURL!);
    const { page: guest, errors: guestErrors } = await duetPlayer(browser, baseURL!);
    for (const page of [host, guest]) await observeVoice(page);
    const { song } = await openOnlineDuet(host, guest, 'duet-demo');
    for (const page of [host, guest]) await expect(status(page)).toHaveAttribute('data-state', 'connected', { timeout: 20_000 });
    for (const page of [host, guest]) await expect.poll(() => rms(page)).toBeLessThan(0.001);
    await host.getByRole('button', { name: 'READY TO SING' }).click();
    const prepared = guest.waitForResponse((r) => r.url().endsWith('/duet/ready'));
    await guest.getByRole('button', { name: 'READY TO SING' }).click();
    const match = await (await prepared).json();
    // No voice while waiting or during count-in, even though peers have negotiated.
    await expect.poll(() => rms(guest)).toBeLessThan(0.001);
    try { await expect.poll(() => rms(guest), { timeout: 12_000 }).toBeGreaterThan(0.02); }
    catch (e) {
      for (const page of [host, guest]) console.log('voice debug', await page.evaluate(async () => {
        const w = window as any;
        const pc = w.__voicePeers.at(-1);
        const stats = await pc.getStats();
        return { sources: w.__voiceSources.map((s: MediaStreamAudioSourceNode) => ({ state: s.context.state, time: s.context.currentTime, tracks: s.mediaStream.getAudioTracks().map((t) => ({ state: t.readyState, muted: t.muted })) })),
          gains: w.__voiceGains.map((g: GainNode) => ({ value: g.gain.value, time: g.context.currentTime })),
          stats: [...stats.values()].filter((s: any) => ['inbound-rtp', 'outbound-rtp', 'media-source'].includes(s.type)) };
      }));
      throw e;
    }
    await expect.poll(() => rms(host)).toBeLessThan(0.001);
    await host.getByRole('button', { name: 'Mute my mic to opponent' }).click();
    await expect.poll(() => rms(guest)).toBeLessThan(0.001);
    // Muting sharing must not stop scoring or request another mic.
    await expect(host.getByTestId('duet-score-0')).toHaveAttribute('data-scored', 'true', { timeout: 8000 });
    await host.getByRole('button', { name: 'Mute my mic to opponent' }).click();
    await expect.poll(() => rms(guest)).toBeGreaterThan(0.02);
    // Loss of signaling tears down the peer immediately, and reconnect rebuilds it on the running timeline.
    await guest.evaluate(() => (window as any).__voiceSockets.at(-1).close());
    await expect.poll(() => guest.evaluate(() => (window as any).__voicePeers.filter((p: RTCPeerConnection) => p.connectionState === 'closed').length)).toBeGreaterThan(0);
    for (const page of [host, guest]) await expect(status(page)).toHaveAttribute('data-state', 'connected', { timeout: 15_000 });
    for (const page of [host, guest]) await expect(page.getByTestId('duet-current')).toHaveAttribute('data-slot', '1', { timeout: 20_000 });
    await expect.poll(() => rms(host)).toBeGreaterThan(0.02);
    await expect.poll(() => rms(guest)).toBeLessThan(0.001);
    await host.getByLabel('Other singer volume').fill('25');
    await expect(host.getByLabel('Other singer volume')).toHaveValue('25');
    console.log('voice diagnostics:', await status(host).innerText(), await status(guest).innerText());
    await host.screenshot({ path: 'e2e/artifacts/duet-live-voice.png', mask: [host.locator('.sing-lyrics')] });
    for (const page of [host, guest]) await expect(page.locator('.battle-headline')).toContainText(/WINS|TIE/, { timeout: 40_000 });
    for (const page of [host, guest]) {
      expect(await schedules(page)).toHaveLength(1); // synthetic click backing, no installed guide
      expect(await page.evaluate(() => (window as any).__micOpens)).toBe(2);
      expect(await page.evaluate(() => (window as any).__voicePeers.every((p: RTCPeerConnection) => p.connectionState === 'closed'))).toBe(true);
    }
    const final = await (await host.request.get(`/api/matches/${match.id}`)).json();
    expectOwnedScores(final, song.phrases.map((p: any) => p.id));
    expect([...hostErrors, ...guestErrors]).toEqual([]);
  } finally { await browser.close(); }
});

test('live voice: mute survives shared restart, rejoin cannot replay, quit releases every peer', async ({ baseURL }) => {
  const browser = await chromium.launch({ args: ['--autoplay-policy=no-user-gesture-required'] });
  try {
    const { page: host, errors: hostErrors } = await duetPlayer(browser, baseURL!);
    const { page: guest, errors: guestErrors } = await duetPlayer(browser, baseURL!);
    for (const page of [host, guest]) await observeVoice(page);
    const { hostName } = await openOnlineDuet(host, guest, 'duet-demo');
    for (const page of [host, guest]) await expect(status(page)).toHaveAttribute('data-state', 'connected');
    await host.getByRole('button', { name: 'Mute my mic to opponent' }).click();
    await host.getByRole('button', { name: 'READY TO SING' }).click();
    const prepared = guest.waitForResponse((r) => r.url().endsWith('/duet/ready'));
    await guest.getByRole('button', { name: 'READY TO SING' }).click();
    const frozen = await (await prepared).json();
    await host.waitForFunction((at) => (performance.timeOrigin + performance.now()) / 1000 > at + 1, frozen.duet.start_at);
    await expect.poll(() => rms(guest)).toBeLessThan(0.001);
    await guest.reload();
    await joinListedRoom(guest, hostName);
    await guest.getByRole('button', { name: 'READY TO SING' }).click();
    await expect(guest.getByText('The shared start was missed. Restart the whole duet together.')).toBeVisible();
    expect(await schedules(guest)).toHaveLength(0);
    await guest.getByRole('button', { name: 'STOP DUET FOR RESTART', exact: true }).click();
    await host.getByRole('button', { name: 'RESTART TOGETHER', exact: true }).click();
    for (const page of [host, guest]) await expect(page.getByRole('button', { name: 'READY TO SING' })).toBeVisible();
    await expect(host.getByRole('button', { name: 'Mute my mic to opponent' })).toHaveAttribute('aria-pressed', 'true');
    for (const page of [host, guest]) await expect(status(page)).toHaveAttribute('data-state', 'connected');
    await host.getByRole('button', { name: /QUIT/ }).click();
    await expect(guest.getByRole('heading', { name: 'DUET STOPPED', exact: true })).toBeVisible();
    for (const page of [host, guest]) expect(await page.evaluate(() =>
      (window as any).__voicePeers.every((p: RTCPeerConnection) => p.connectionState === 'closed'))).toBe(true);
    expect([...hostErrors, ...guestErrors]).toEqual([]);
  } finally { await browser.close(); }
});

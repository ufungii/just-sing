import { chromium, expect, test } from '@playwright/test';
import { duetPlayer, expectOnePlayback, expectOwnedScores, openOnlineDuet, schedules, joinListedRoom } from './duetHarness';

/** Two contexts with deliberately different wall clocks, one server-scheduled continuous performance. */
test('online duet: loaded barrier, synchronized handoffs and independent assigned scores', async ({ baseURL }) => {
  const browser = await chromium.launch({ args: ['--autoplay-policy=no-user-gesture-required'] });
  try {
    const { page: host, errors: hostErrors } = await duetPlayer(browser, baseURL!);
    const { page: guest, errors: guestErrors } = await duetPlayer(browser, baseURL!, 3_600_000);
    const { song } = await openOnlineDuet(host, guest);
    const hostPrepared = host.waitForResponse((r) => r.url().endsWith('/duet/ready'));
    await host.getByRole('button', { name: 'READY TO SING' }).click();
    const waiting = await (await hostPrepared).json();
    expect(waiting.state).toBe('preparing'); expect(waiting.duet.start_at).toBeNull();
    expect(await schedules(host)).toHaveLength(0);
    const guestPrepared = guest.waitForResponse((r) => r.url().endsWith('/duet/ready'));
    await guest.getByRole('button', { name: 'READY TO SING' }).click();
    const frozen = await (await guestPrepared).json();
    expect(frozen.state).toBe('active');
    expect(frozen.attempts.every((a: any) => a.state === 'started')).toBe(true);
    for (const page of [host, guest]) await expectOnePlayback(page, frozen.duet.start_at, 0, song.duration);
    expect(Math.abs((await schedules(host))[0].scheduledEpoch - (await schedules(guest))[0].scheduledEpoch)).toBeLessThan(0.15);
    // Both clients switch on the same clip timeline, without another click, mic open or audio start.
    await Promise.all([host, guest].map((p) => expect(p.getByTestId('duet-current')).toHaveAttribute('data-slot', '1', { timeout: 25_000 })));
    for (const page of [host, guest]) { expect(await schedules(page)).toHaveLength(2); await expect(page.getByTestId('duet-next')).toContainText('P1'); }
    await host.screenshot({ path: 'e2e/artifacts/duet-online-handoff.png', mask: [host.locator('.sing-lyrics')] });
    await Promise.all([host, guest].map((p) => expect(p.getByTestId('duet-current')).toHaveAttribute('data-slot', '0', { timeout: 20_000 })));
    for (const page of [host, guest]) await expect(page.locator('.battle-headline')).toContainText(/WINS|TIE/, { timeout: 20_000 });
    const final = await (await host.request.get(`/api/matches/${frozen.id}`)).json();
    expectOwnedScores(final, song.phrases.map((p: any) => p.id));
    expect(await host.locator('.battle-headline').innerText()).toBe(await guest.locator('.battle-headline').innerText());
    for (const [slot, page] of [host, guest].entries()) {
      const history = (await (await page.request.get('/api/history')).json())[0];
      expect(history.total).toBe(final.attempts.find((a: any) => a.slot === slot).score.total);
      expect(history.range).toBeNull(); expect(history.duet).toBe(true);
      expect(await schedules(page)).toHaveLength(2);
      expect(await page.evaluate(() => (window as any).__micOpens)).toBe(1); // reuse the successful lobby mic check
    }
    expect([...hostErrors, ...guestErrors]).toEqual([]);
  } finally { await browser.close(); }
});

test('online duet: reload after shared start never replays one player, explicit restart resets both', async ({ baseURL }) => {
  const browser = await chromium.launch({ args: ['--autoplay-policy=no-user-gesture-required'] });
  try {
    const { page: host, errors: hostErrors } = await duetPlayer(browser, baseURL!);
    const { page: guest, errors: guestErrors } = await duetPlayer(browser, baseURL!);
    const { hostName } = await openOnlineDuet(host, guest);
    await host.getByRole('button', { name: 'READY TO SING' }).click();
    const prepared = guest.waitForResponse((r) => r.url().endsWith('/duet/ready'));
    await guest.getByRole('button', { name: 'READY TO SING' }).click();
    const frozen = await (await prepared).json();
    await guest.waitForFunction((at) => (performance.timeOrigin + performance.now()) / 1000 > at + 0.2, frozen.duet.start_at);
    await guest.reload();
    await joinListedRoom(guest, hostName);
    await guest.getByRole('button', { name: 'READY TO SING' }).click();
    await expect(guest.getByText('The shared start was missed. Restart the whole duet together.')).toBeVisible();
    expect(await schedules(guest)).toHaveLength(0);
    await guest.getByRole('button', { name: 'STOP DUET FOR RESTART', exact: true }).click();
    await host.getByRole('button', { name: 'RESTART TOGETHER', exact: true }).click();
    for (const page of [host, guest]) await expect(page.getByRole('button', { name: 'READY TO SING' })).toBeVisible();
    // A fresh barrier exists, with no implicit playback after restarting.
    const reloaded = host.waitForResponse((r) => r.url().endsWith('/duet/ready'));
    await host.getByRole('button', { name: 'READY TO SING' }).click();
    const fresh = await (await reloaded).json();
    expect(fresh.id).not.toBe(frozen.id);
    expect(fresh.state).toBe('preparing'); expect(fresh.duet.start_at).toBeNull();
    expect(await schedules(guest)).toHaveLength(0);
    expect([...hostErrors, ...guestErrors]).toEqual([]);
  } finally { await browser.close(); }
});

test('online duet: remote score and original pitch frames arrive with different voice ranges', async ({ baseURL }) => {
  const browser = await chromium.launch({ args: ['--autoplay-policy=no-user-gesture-required'] });
  try {
    const { page: host, errors: hostErrors } = await duetPlayer(browser, baseURL!, 0, 110);
    const { page: guest, errors: guestErrors } = await duetPlayer(browser, baseURL!, 0, 440);
    for (const page of [host, guest]) await page.addInitScript(() => {
      (window as any).__duetSent = []; (window as any).__duetReceived = [];
      const originalSend = WebSocket.prototype.send;
      WebSocket.prototype.send = function (data: any) {
        if (typeof data === 'string') {
          const event = JSON.parse(data);
          if (event.type === 'progress' && event.data.match_id) (window as any).__duetSent.push(event.data);
        }
        return originalSend.call(this, data);
      };
      const OriginalSocket = WebSocket;
      (window as any).WebSocket = class extends OriginalSocket {
        constructor(url: string | URL, protocols?: string | string[]) {
          super(url, protocols);
          this.addEventListener('message', (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'turn_progress' && data.data.match_id) (window as any).__duetReceived.push(data);
          });
        }
      };
    });
    await openOnlineDuet(host, guest, 'duet-demo', { beforeMicChecks: async () => {
      await host.getByRole('button', { name: 'LOW', exact: true }).click();
      await guest.getByRole('button', { name: 'HIGH', exact: true }).click();
    } });
    await host.getByRole('button', { name: 'READY TO SING' }).click();
    const ready = guest.waitForResponse((r) => r.url().endsWith('/duet/ready'));
    await guest.getByRole('button', { name: 'READY TO SING' }).click();
    const match = await (await ready).json();
    expect(match.attempts.map((a: any) => a.register)).toEqual([-12, 12]);
    // Remote bars become scored during the performance, before either result is saved.
    await expect(guest.getByTestId('duet-score-0')).toHaveAttribute('data-scored', 'true', { timeout: 25_000 });
    await expect(host.getByTestId('duet-score-1')).toHaveAttribute('data-scored', 'true', { timeout: 25_000 });
    for (const [slot, source, receiver] of [[0, host, guest], [1, guest, host]] as const) {
      const sent = await source.evaluate(() => (window as any).__duetSent);
      const received = await receiver.evaluate(() => (window as any).__duetReceived);
      const voiced = sent.find((d: any) => d.pitch.hz.some((hz: number | null) => hz !== null));
      expect(voiced).toBeTruthy();
      expect(received.some((event: any) => event.slot === slot && JSON.stringify(event.data) === JSON.stringify(voiced))).toBe(true);
      const scored = received.filter((event: any) => event.slot === slot && event.data.running !== null);
      const latest = scored.at(-1).data.running;
      expect(latest).toBeGreaterThan(80);
      await expect(receiver.getByTestId(`duet-score-${slot}`)).toHaveAttribute('data-fill', String(Math.round(latest)));
    }
    expect([...hostErrors, ...guestErrors]).toEqual([]);
  } finally { await browser.close(); }
});

test('mic check: record a short local clip and hear the selected input boost', async ({ baseURL }) => {
  const browser = await chromium.launch({ args: ['--autoplay-policy=no-user-gesture-required'] });
  try {
    const { page: host, errors } = await duetPlayer(browser, baseURL!);
    const { page: guest } = await duetPlayer(browser, baseURL!);
    const { openOnlineLobby } = await import('./duetHarness');
    await openOnlineLobby(host, guest, 'duet-demo');
    const levels: number[] = [];
    for (const percent of [100, 300]) {
      const slider = host.getByRole('slider', { name: 'Microphone input volume', exact: true });
      await slider.fill(String(percent));
      await host.getByRole('button', { name: 'RECORD 3-SECOND TEST', exact: true }).click();
      await expect(host.getByText('Mic works!')).toBeVisible({ timeout: 10_000 });
      const clip = host.getByLabel('Microphone test recording');
      await expect(clip).toBeVisible();
      levels.push(await clip.evaluate(async (element: HTMLAudioElement) => {
        const ctx = new AudioContext();
        const buffer = await ctx.decodeAudioData(await (await fetch(element.src)).arrayBuffer());
        const data = buffer.getChannelData(0);
        let sum = 0; for (const sample of data) sum += sample * sample;
        await ctx.close();
        return Math.sqrt(sum / data.length);
      }));
      await clip.evaluate(async (element: HTMLAudioElement) => { await element.play(); });
      await expect.poll(() => clip.evaluate((element: HTMLAudioElement) => element.currentTime)).toBeGreaterThan(0);
      await clip.evaluate((element: HTMLAudioElement) => element.pause());
    }
    expect(levels[0]).toBeGreaterThan(0.02);
    expect(levels[1] / levels[0]).toBeGreaterThan(2.5);
    expect(levels[1] / levels[0]).toBeLessThan(3.5);
    expect(await host.evaluate(() => localStorage.getItem('just-sing.mic-gain'))).toBe('3');
    expect(errors).toEqual([]);
  } finally { await browser.close(); }
});

test('mic check: recording errors release capture and allow retry', async ({ baseURL }) => {
  const browser = await chromium.launch({ args: ['--autoplay-policy=no-user-gesture-required'] });
  try {
    const { page: host, errors } = await duetPlayer(browser, baseURL!);
    const { page: guest } = await duetPlayer(browser, baseURL!);
    await host.addInitScript(() => {
      const Recorder = MediaRecorder;
      window.MediaRecorder = class extends Recorder {
        start() { super.start(); queueMicrotask(() => this.dispatchEvent(new Event('error'))); }
      };
    });
    const { openOnlineLobby } = await import('./duetHarness');
    await openOnlineLobby(host, guest, 'duet-demo');
    const record = host.getByRole('button', { name: 'RECORD 3-SECOND TEST', exact: true });
    await record.click();
    await expect(host.getByText('Could not record a test clip. Try recording again or use TEST MIC.')).toBeVisible();
    await expect(record).toBeEnabled();
    await expect(host.getByLabel('Microphone test recording')).toHaveCount(0);
    await expect.poll(() => host.evaluate(() => (window as any).__micStreams.every((stream: MediaStream) => stream.getTracks().every((track) => track.readyState === 'ended')))).toBe(true);
    await host.getByRole('button', { name: 'TEST MIC', exact: true }).click();
    await expect(host.getByText('Mic works!')).toBeVisible();
    expect(errors).toEqual([]);
  } finally { await browser.close(); }
});

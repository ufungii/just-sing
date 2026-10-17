import { expect, type Browser, type Page } from '@playwright/test';

export const DUET_CLIP = 'russian-roulette';
/** Generated mic audio only; no recorded or copyrighted audio is added to the repository. */
export async function duetPlayer(browser: Browser, baseURL: string, wallClockSkew = 0) {
  const page = await (await browser.newContext({ baseURL })).newPage();
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.addInitScript((skew) => {
    const realNow = Date.now;
    Date.now = () => realNow() + skew;
    (window as any).__audioSchedules = [];
    (window as any).__micOpens = 0;
    const originalStart = AudioBufferSourceNode.prototype.start;
    AudioBufferSourceNode.prototype.start = function (when = 0, offset = 0, duration?: number) {
      (window as any).__audioSchedules.push({ when, offset, duration, contextNow: this.context.currentTime,
        scheduledEpoch: performance.timeOrigin / 1000 + performance.now() / 1000 + when - this.context.currentTime });
      if (duration === undefined) originalStart.call(this, when, offset);
      else originalStart.call(this, when, offset, duration);
    };
    navigator.mediaDevices.getUserMedia = async () => {
      (window as any).__micOpens++;
      const ctx = new AudioContext();
      await ctx.resume();
      const osc = ctx.createOscillator();
      osc.frequency.value = 220;
      const gain = ctx.createGain(); gain.gain.value = 0.15;
      const dest = ctx.createMediaStreamDestination();
      osc.connect(gain).connect(dest); osc.start();
      for (const track of dest.stream.getTracks()) {
        const stop = track.stop.bind(track);
        track.stop = () => { stop(); void ctx.close(); };
      }
      return dest.stream;
    };
  }, wallClockSkew);
  return { page, errors };
}

export async function manifest(page: Page) {
  const response = await page.request.get(`/api/clips/${DUET_CLIP}/manifest`);
  expect(response.status(), 'local russian-roulette assets are required').toBe(200);
  return response.json();
}
export async function mic(page: Page) {
  await page.getByRole('button', { name: 'TEST MIC', exact: true }).click();
  await expect(page.getByText('Mic works!')).toBeVisible({ timeout: 15_000 });
}
export const schedules = (page: Page) => page.evaluate(() => (window as any).__audioSchedules);
export async function expectOnePlayback(page: Page, startAt: number, start: number, end: number) {
  await expect.poll(async () => (await schedules(page)).length).toBe(2); // instrumental + guide, scheduled once each
  const sources = await schedules(page);
  for (const src of sources) {
    expect(src.offset).toBe(start);
    expect(src.duration).toBeCloseTo(end - start);
    expect(src.when).toBe(sources[0].when);
    expect(Math.abs(src.scheduledEpoch - startAt)).toBeLessThan(0.15);
  }
}
export const assigned = (match: any, slot: number) => match.duet.sections.filter((s: any) => s.slot === slot).flatMap((s: any) => s.phrase_ids);
export function expectOwnedScores(match: any, allIds: string[], range: any = null) {
  expect(match.state).toBe('finished');
  expect(match.attempts).toHaveLength(2);
  const savedIds: string[] = [];
  for (const attempt of match.attempts) {
    expect(attempt.state).toBe('accepted');
    expect(attempt.score.duet).toBe(true);
    expect(attempt.score.range).toEqual(range);
    const ids = attempt.score.phrases.map((p: any) => p.phrase_id);
    expect(ids).toEqual(assigned(match, attempt.slot));
    savedIds.push(...ids);
  }
  expect(new Set(savedIds).size).toBe(savedIds.length);
  expect(savedIds.sort()).toEqual([...allIds].sort());
}

export async function openOnlineDuet(host: Page, guest: Page) {
  await host.goto('/');
  const song = await manifest(host);
  await host.getByText('ONLINE', { exact: true }).first().click();
  await host.getByPlaceholder('e.g. Mina').fill('E2E-Bot-duet-online');
  await host.getByRole('button', { name: new RegExp(song.title, 'i') }).click();
  await host.getByRole('button', { name: /CREATE ROOM/ }).click();
  const code = await host.getByTestId('room-code').innerText();
  await guest.goto('/');
  await guest.getByText('ONLINE', { exact: true }).first().click();
  await guest.getByPlaceholder('e.g. Mina').fill('E2E-Rival-duet-online');
  await guest.getByLabel('Room code').fill(code.toLowerCase());
  await guest.getByRole('button', { name: 'JOIN', exact: true }).click();
  for (const page of [host, guest]) { await mic(page); await page.getByRole('button', { name: 'READY ✓', exact: true }).click(); }
  await host.getByRole('button', { name: 'START ♪', exact: true }).click();
  for (const page of [host, guest]) await expect(page.getByRole('button', { name: 'READY TO SING' })).toBeVisible();
  return { song, code };
}

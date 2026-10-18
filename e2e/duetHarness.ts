import { expect, type Browser, type Page } from '@playwright/test';

export const DUET_CLIP = 'russian-roulette';
/** Generated mic audio only; no recorded or copyrighted audio is added to the repository. */
export async function duetPlayer(browser: Browser, baseURL: string, wallClockSkew = 0) {
  const page = await (await browser.newContext({ baseURL })).newPage();
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.addInitScript((skew) => {
    localStorage.setItem('just-sing.showTestClips', '1');
    const realNow = Date.now;
    Date.now = () => realNow() + skew;
    (window as any).__audioSchedules = [];
    (window as any).__micOpens = 0;
    (window as any).__micStreams = [];
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
      (window as any).__micStreams.push(dest.stream);
      return dest.stream;
    };
  }, wallClockSkew);
  return { page, errors };
}

export async function manifest(page: Page, clipId = DUET_CLIP) {
  const response = await page.request.get(`/api/clips/${clipId}/manifest`);
  expect(response.status(), `clip ${clipId} must be installed`).toBe(200);
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

/** Create a new local player through the setup screen's player dropdown and select them for `seat`. */
export async function addPlayer(page: Page, seat: string, name: string) {
  await page.getByRole('combobox', { name: seat, exact: true }).click();
  await page.getByRole('option', { name: 'ADD PLAYER' }).click();
  await page.getByPlaceholder('e.g. Mina').fill(name);
  await page.getByRole('button', { name: 'ADD PLAYER', exact: true }).click();
  await expect(page.getByRole('combobox', { name: seat, exact: true })).toContainText(name);
}

/** A fresh browser has no player yet, so the online menu asks for one first (name + default avatar). */
export async function createFirstPlayer(page: Page, name: string) {
  await page.getByPlaceholder('e.g. Mina').fill(name);
  await page.getByRole('button', { name: 'ADD PLAYER', exact: true }).click();
}

/** Open the online room list from the home screen (the player already exists, e.g. after a reload). */
export async function openRoomList(page: Page) {
  await page.getByText('ONLINE', { exact: true }).first().click();
  await page.getByRole('button', { name: 'JOIN ROOM', exact: true }).click();
}

/** Join (or rejoin) a room by tapping its row in the list. Public rooms need no password. */
export async function joinListedRoom(page: Page, hostName: string) {
  await openRoomList(page);
  await page.getByTestId('room-list').getByRole('listitem').filter({ hasText: hostName }).getByRole('button').first().click();
}

export const ONLINE_HOST = 'E2E-Bot-duet-online';

export async function openOnlineLobby(host: Page, guest: Page, clipId = DUET_CLIP) {
  await host.goto('/');
  const song = await manifest(host, clipId);
  await host.getByText('ONLINE', { exact: true }).first().click();
  await createFirstPlayer(host, ONLINE_HOST);
  await host.getByRole('button', { name: 'CREATE ROOM', exact: true }).click();
  await host.getByRole('button', { name: /CREATE ROOM ♪/ }).click();
  // The song is chosen inside the room, by the host.
  await host.getByRole('button').filter({ has: host.getByText(song.title, { exact: true }) }).click();
  await guest.goto('/');
  await guest.getByText('ONLINE', { exact: true }).first().click();
  await createFirstPlayer(guest, 'E2E-Rival-duet-online');
  await guest.getByRole('button', { name: 'JOIN ROOM', exact: true }).click();
  await guest.getByTestId('room-list').getByRole('listitem').filter({ hasText: ONLINE_HOST }).getByRole('button').first().click();
  return { song, hostName: ONLINE_HOST };
}

export async function openOnlineDuet(host: Page, guest: Page, clipId = DUET_CLIP, lobby?: {
  beforeMicChecks?: () => Promise<void>;
  afterMicChecks?: () => Promise<void>;
}) {
  const { song, hostName } = await openOnlineLobby(host, guest, clipId);
  await lobby?.beforeMicChecks?.();
  for (const page of [host, guest]) await mic(page);
  await lobby?.afterMicChecks?.();
  for (const page of [host, guest]) await page.getByRole('button', { name: 'READY ✓', exact: true }).click();
  await host.getByRole('button', { name: 'START ♪', exact: true }).click();
  for (const page of [host, guest]) await expect(page.getByRole('button', { name: 'READY TO SING' })).toBeVisible();
  return { song, hostName };
}

/**
 * Online room end to end: two separate browser contexts (two guests, two cookie jars) on one server.
 * Host "E2E Bot" creates a room, "E2E Rival" joins by code, both pass the mic check and ready up, the host
 * starts, the host sings the good take, the rival the wrong-notes take. Fake mics work as in battle.spec.ts
 * (getUserMedia swapped per page, START clicked LEAD - COUNT_IN s after the stream opened).
 * Asserts both pages show the same winner (the host) and that the saved totals match the server.
 */
import { chromium, expect, test, type Page } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const CLIP = process.env.E2E_CLIP ?? 'synthetic-demo';
const LEAD = Number(process.env.E2E_LEAD ?? 6);
const COUNT_IN = 3.15;
const HOST = 'E2E Bot';
const GUEST = 'E2E Rival';

async function newPlayer(browser: Awaited<ReturnType<typeof chromium.launch>>, baseURL: string, take: 'good' | 'wrong', errors: string[]) {
  const page = await (await browser.newContext({ baseURL })).newPage();
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('console', (m) => m.type() === 'error' && !/status of (401|404)/.test(m.text()) && errors.push(m.text()));
  await page.route('**/__take/*.wav', (route) => {
    const file = path.basename(new URL(route.request().url()).pathname);
    return route.fulfill({ body: fs.readFileSync(path.resolve(__dirname, 'takes', CLIP, file)), contentType: 'audio/wav' });
  });
  await page.addInitScript((t) => {
    navigator.mediaDevices.getUserMedia = async () => {
      const ctx = new AudioContext();
      await ctx.resume();
      const buf = await ctx.decodeAudioData(await (await fetch(`/__take/${t}.wav`)).arrayBuffer());
      const src = ctx.createBufferSource();
      src.buffer = buf;
      const dest = ctx.createMediaStreamDestination();
      src.connect(dest);
      src.start();
      (window as any).__micOpen = performance.now();
      return dest.stream;
    };
  }, take);
  return page;
}

async function lobbyReady(page: Page) {
  await page.getByRole('button', { name: 'TEST MIC' }).click();
  await expect(page.getByText('Mic works!')).toBeVisible({ timeout: 15_000 });
  await page.getByRole('button', { name: 'READY ✓' }).click();
}

async function singTurn(page: Page) {
  await page.getByRole('button', { name: /SING ▶/ }).click();
  const start = page.getByRole('button', { name: '▶ START', exact: true });
  await expect(start).toBeVisible({ timeout: 20_000 });
  await page.waitForFunction((ms) => performance.now() - (window as any).__micOpen >= ms, (LEAD - COUNT_IN) * 1000);
  await start.click();
}

test('online room: good take beats wrong notes, both browsers agree', async ({ baseURL }) => {
  test.setTimeout(300_000);
  const browser = await chromium.launch({ args: ['--autoplay-policy=no-user-gesture-required'] });
  const errors: string[] = [];
  const a = await newPlayer(browser, baseURL!, 'good', errors);
  const b = await newPlayer(browser, baseURL!, 'wrong', errors);

  // Host creates the room.
  await a.goto('/');
  await a.getByText('ONLINE', { exact: true }).first().click();
  const clips = await (await a.request.get('/api/clips')).json();
  const title = clips.find((c: any) => c.id === CLIP).title;
  await a.getByPlaceholder('e.g. Mina').fill(HOST);
  await a.getByRole('button', { name: new RegExp(title.replace(/[()]/g, '.')) }).click();
  await a.getByRole('button', { name: /CREATE ROOM/ }).click();
  const code = (await a.getByTestId('room-code').innerText()).trim();
  expect(code).toMatch(/^[A-Z0-9]{5}$/);

  // A bad code gets a friendly error; the real one joins.
  await b.goto('/');
  await b.getByText('ONLINE', { exact: true }).first().click();
  await b.getByPlaceholder('e.g. Mina').fill(GUEST);
  await b.getByLabel('Room code').fill('ZZZZZ');
  await b.getByRole('button', { name: 'JOIN', exact: true }).click();
  await expect(b.getByText('No room with that code.')).toBeVisible();
  await b.getByLabel('Room code').fill(code.toLowerCase());
  await b.getByRole('button', { name: 'JOIN', exact: true }).click();
  await expect(b.getByTestId('room-code')).toHaveText(code);
  await expect(a.getByText(new RegExp(`${GUEST}.*not ready`))).toBeVisible(); // host sees the join live

  await lobbyReady(a);
  await lobbyReady(b);
  await expect(a.getByText(new RegExp(`${GUEST}.*READY`))).toBeVisible();
  await a.getByRole('button', { name: 'START ♪' }).click();

  // Host sings; the rival sees live progress and badges, then gets the turn.
  await singTurn(a);
  await expect(b.getByText(/WAITING FOR E2E BOT/)).toBeVisible();
  await expect(b.getByTestId('live-badges')).toContainText(/PERFECT|GREAT|OKAY|BAD|MISS/, { timeout: 60_000 });
  await singTurn(b);

  for (const p of [a, b]) await expect(p.locator('.battle-headline')).toContainText(/WINS|TIE/, { timeout: 120_000 });
  const heads = [await a.locator('.battle-headline').innerText(), await b.locator('.battle-headline').innerText()];
  await a.screenshot({ path: `artifacts/${CLIP}-online-results.png` });
  expect(heads[0]).toBe(heads[1]);
  expect(heads[0].toLowerCase()).toBe(`${HOST.toLowerCase()} wins!`);

  // The server agrees: each browser's own history total is its seat's saved total, and the host won.
  const [ha, hb] = [await (await a.request.get('/api/history')).json(), await (await b.request.get('/api/history')).json()];
  expect(ha).toHaveLength(1);
  expect(hb).toHaveLength(1);
  const match = await (await a.request.get(`/api/matches/${ha[0].match_id}`)).json();
  const total = (slot: number) => match.attempts.find((x: any) => x.slot === slot).score.total;
  console.log('online totals', ha[0].total, hb[0].total, 'winner_slot', match.winner_slot);
  expect(match.winner_slot).toBe(0);
  expect(ha[0].total).toBe(total(0));
  expect(hb[0].total).toBe(total(1));
  expect(total(0)).toBeGreaterThan(total(1) + 10);
  // Both pages display the server's saved totals (whole numbers), in seat order.
  const shown = [Math.round(total(0)), Math.round(total(1))].map((n) => `Total score ${n} out of 100`);
  for (const p of [a, b]) expect(await p.getByRole('img', { name: /^Total score/ }).evaluateAll((els) => els.map((e) => e.getAttribute('aria-label')))).toEqual(shown);
  expect(errors, 'console/page errors').toEqual([]);
  await browser.close();
});

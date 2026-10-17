/**
 * Local battle end to end: a good-take player vs a wrong-notes player on one browser.
 * The built-in fake mic file is fixed per browser, so this spec swaps getUserMedia for a stream
 * played from a WAV chosen per turn (served by page.route from e2e/takes/). Same alignment rule as
 * sing.spec.ts: the stream restarts at each open, so START is clicked LEAD - COUNT_IN s after it opened.
 * Asserts the good player wins and the winner shown equals the winner the server saved.
 */
import { chromium, expect, test } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const CLIP = process.env.E2E_CLIP ?? 'synthetic-demo';
const LEAD = Number(process.env.E2E_LEAD ?? 6);
const COUNT_IN = 3.15;
const GOOD = 'E2E Bot'; // first player = the guest creating the match, so cleanup_db.py removes it
const WRONG = 'E2E Rival';

test('battle: good take beats wrong notes', async ({ baseURL }) => {
  test.setTimeout(240_000);
  const browser = await chromium.launch({ args: ['--autoplay-policy=no-user-gesture-required'] });
  const page = await (await browser.newContext({ baseURL })).newPage();
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('console', (m) => m.type() === 'error' && !/status of (401|404)/.test(m.text()) && errors.push(m.text()));

  await page.route('**/__take/*.wav', (route) => {
    const take = path.basename(new URL(route.request().url()).pathname);
    return route.fulfill({ body: fs.readFileSync(path.resolve(__dirname, 'takes', CLIP, take)), contentType: 'audio/wav' });
  });
  await page.addInitScript(() => {
    (window as any).__take = 'good';
    navigator.mediaDevices.getUserMedia = async () => {
      const ctx = new AudioContext();
      await ctx.resume();
      const buf = await ctx.decodeAudioData(await (await fetch(`/__take/${(window as any).__take}.wav`)).arrayBuffer());
      const src = ctx.createBufferSource();
      src.buffer = buf;
      const dest = ctx.createMediaStreamDestination();
      src.connect(dest);
      src.start();
      (window as any).__micOpen = performance.now();
      return dest.stream;
    };
  });

  // Setup
  await page.goto('/');
  await page.getByText('1P VS 2P', { exact: true }).first().click();
  const clips = await (await page.request.get('/api/clips')).json();
  const title = clips.find((c: any) => c.id === CLIP).title;
  await page.getByRole('button', { name: new RegExp(title.replace(/[()]/g, '.')) }).click();
  await page.getByPlaceholder('e.g. Mina').fill(GOOD);
  await page.getByPlaceholder('e.g. Jisoo').fill(WRONG);
  await page.getByRole('button', { name: 'TEST MIC' }).click();
  await expect(page.getByText('Mic works!')).toBeVisible({ timeout: 15_000 });
  await page.getByRole('button', { name: /FIGHT/ }).click();

  const sing = async (take: 'good' | 'wrong') => {
    await page.evaluate((t) => ((window as any).__take = t), take);
    const start = page.getByRole('button', { name: '▶ START', exact: true });
    await expect(start).toBeVisible({ timeout: 20_000 });
    await page.waitForFunction((ms) => performance.now() - (window as any).__micOpen >= ms, (LEAD - COUNT_IN) * 1000);
    await start.click();
  };

  await sing('good'); // __take is read when the Sing screen opens its stream; set before that for the wrong take below
  await expect(page.getByText(/Pass the headphones/)).toBeVisible({ timeout: 90_000 });
  // The Sing screen for player 2 opens its stream right after READY: switch the take first.
  await page.evaluate(() => ((window as any).__take = 'wrong'));
  await page.getByRole('button', { name: /READY/ }).click();
  await sing('wrong');

  await expect(page.locator('.battle-headline')).toContainText(/WINS|TIE/, { timeout: 90_000 });
  const headline = await page.locator('.battle-headline').innerText();
  await page.screenshot({ path: `artifacts/${CLIP}-battle-results.png` });

  const history = await (await page.request.get('/api/history')).json();
  expect(history).toHaveLength(1);
  const match = await (await page.request.get(`/api/matches/${history[0].match_id}`)).json();
  const totals = Object.fromEntries(history[0].players.map((p: any) => [p.display_name, p.total]));
  console.log('battle totals', JSON.stringify(totals), 'winner_slot', match.winner_slot);
  expect(match.winner_slot).toBe(0);
  expect(totals[GOOD]).toBeGreaterThan(totals[WRONG] + 10);
  expect(headline.toLowerCase()).toBe(`${GOOD.toLowerCase()} wins!`);
  expect(errors, 'console/page errors').toEqual([]);
  await browser.close();
});

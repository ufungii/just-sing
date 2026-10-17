/**
 * Solo play end to end in real Chromium with a fake microphone (see README.md).
 * Home -> Solo setup -> Sing -> Results -> History, three times: good, wrong-notes and silent take.
 * Asserts RELATIVE outcomes (good > wrong, silence ~ 0): the fake device's timing is only approximate.
 */
import { chromium, expect, test } from '@playwright/test';
import path from 'node:path';

const CLIP = process.env.E2E_CLIP ?? 'synthetic-demo';
const LEAD = Number(process.env.E2E_LEAD ?? 6); // seconds of prefix in the WAVs (make_takes.py)
const COUNT_IN = 3.15; // engine.ts: clip t=0 is this long after START is handled
const GOOD_FLOOR = Number(process.env.E2E_GOOD_FLOOR ?? 60);
const NAME = 'E2E Bot';
const totals: Record<string, number> = {};

for (const take of ['good', 'wrong', 'silence'] as const) {
  test(`solo ${take} take`, async ({ baseURL }) => {
    const wav = path.resolve(__dirname, 'takes', CLIP, `${take}.wav`);
    const browser = await chromium.launch({
      args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream', `--use-file-for-fake-audio-capture=${wav}`, '--autoplay-policy=no-user-gesture-required'],
    });
    const page = await (await browser.newContext({ baseURL })).newPage();
    const errors: string[] = [];
    page.on('pageerror', (e) => errors.push(String(e)));
    if (process.env.E2E_DEBUG) page.on('console', (m) => console.log('[page]', m.type(), m.text()));
    // Expected noise: 401 = guest bootstrap before the cookie exists, 404 = no instrumental -> click track.
    page.on('console', (m) => m.type() === 'error' && !/status of (401|404)/.test(m.text()) && errors.push(m.text()));
    // The fake file restarts at each stream open: remember when the Sing screen's stream opened.
    await page.addInitScript(() => {
      const gum = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
      navigator.mediaDevices.getUserMedia = async (c) => {
        const s = await gum(c);
        (window as any).__micOpen = performance.now();
        return s;
      };
    });

    // Home (guest) -> Solo setup
    await page.goto('/');
    await page.getByText('SOLO SING', { exact: true }).first().click();
    const clips = await (await page.request.get('/api/clips')).json();
    const title = clips.find((c: any) => c.id === CLIP).title;
    await page.getByRole('button', { name: new RegExp(title.replace(/[()]/g, '.')) }).click();
    await page.getByPlaceholder('e.g. Mina').fill(NAME);
    await page.getByRole('button', { name: 'TEST MIC' }).click();
    await expect(page.getByText('Mic works!')).toBeVisible({ timeout: 15_000 });
    await page.getByRole('button', { name: /START ♪/ }).click(); // timing check skipped (optional)

    // Sing: start so that clip t=0 meets the WAV's take start (stream time LEAD)
    const start = page.getByRole('button', { name: '▶ START', exact: true });
    await expect(start).toBeVisible({ timeout: 20_000 });
    await page.waitForFunction((ms) => performance.now() - (window as any).__micOpen >= ms, (LEAD - COUNT_IN) * 1000);
    await start.click();
    if (process.env.E2E_DEBUG) { await page.waitForTimeout(3000); await page.screenshot({ path: 'artifacts/dbg.png' }); }
    await page.waitForTimeout(16_000); // phrase region of the synthetic clip is ~12-16 s
    await page.screenshot({ path: `artifacts/${CLIP}-${take}-sing.png` });

    // Results
    await expect(page.getByText('saved to your history')).toBeVisible({ timeout: 90_000 });
    await expect(page.locator('.results-bubble')).not.toBeEmpty(); // blurb: Gemini text or the template fallback
    await expect(page.locator('.results-bubble')).not.toContainText('thinking', { timeout: 30_000 });
    await page.screenshot({ path: `artifacts/${CLIP}-${take}-results.png` });

    // Saved server-side, shown in History
    const history = await (await page.request.get('/api/history')).json();
    expect(history).toHaveLength(1);
    expect(history[0].clip_id).toBe(CLIP);
    totals[take] = history[0].total;
    console.log(`${take}: server total ${totals[take]}`);
    await page.getByRole('button', { name: /HISTORY/ }).click();
    await expect(page.locator('.history-row')).toHaveCount(1);
    await expect(page.locator('.history-row__total')).toHaveText(String(Math.round(totals[take])));

    expect(errors, 'console/page errors').toEqual([]);
    await browser.close();
  });
}

test.afterAll(() => {
  if (Object.keys(totals).length < 3) return; // a filtered run (-g): no cross-take comparison
  console.log('TOTALS', JSON.stringify(totals));
  expect(totals.good).toBeGreaterThan(GOOD_FLOOR);
  expect(totals.good).toBeGreaterThan(totals.wrong + 10);
  expect(totals.silence).toBeLessThan(5);
});

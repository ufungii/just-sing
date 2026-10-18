/**
 * The solo singing screen fits the window and holds still: at common 16:9 / 16:10 sizes the page never
 * scrolls, and the stage and lyrics boxes keep the same size while the song plays.
 * Needs the same setup as sing.spec.ts (see README.md); the take is only there to pass the mic check.
 */
import { chromium, expect, test } from '@playwright/test';
import path from 'node:path';
import { addPlayer } from './duetHarness';

const CLIP = process.env.E2E_CLIP ?? 'synthetic-demo';
const NAME = `E2E-Bot-${Date.now().toString(36).slice(-4)}`; // cleanup_db.py deletes names starting "E2E-"
const SIZES = [
  { width: 1280, height: 720 },
  { width: 1366, height: 768 },
  { width: 1280, height: 800 },
  { width: 1440, height: 900 },
  { width: 1920, height: 1080 },
];

for (const viewport of SIZES) {
  test(`singing screen fits and holds still at ${viewport.width}x${viewport.height}`, async ({ baseURL }) => {
    const wav = path.resolve(__dirname, 'takes', CLIP, 'good.wav');
    const browser = await chromium.launch({
      args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream', `--use-file-for-fake-audio-capture=${wav}`, '--autoplay-policy=no-user-gesture-required'],
    });
    const page = await (await browser.newContext({ baseURL, viewport })).newPage();
    await page.addInitScript(() => localStorage.setItem('just-sing.showTestClips', '1'));

    await page.goto('/');
    await page.getByText('LOCAL', { exact: true }).first().click();
    const clips = await (await page.request.get('/api/clips')).json();
    const title = clips.find((c: any) => c.id === CLIP).title;
    await page.getByRole('button', { name: new RegExp(title.replace(/[()]/g, '.')) }).click();
    await addPlayer(page, 'PLAYER', NAME);
    await page.getByRole('button', { name: 'TEST MIC' }).click();
    await expect(page.getByText('Mic works!')).toBeVisible({ timeout: 15_000 });
    await page.getByRole('button', { name: 'JUST SING!', exact: true }).click();
    await page.getByRole('button', { name: '▶ START', exact: true }).click();

    const measure = () => page.evaluate(() => ({
      overflow: document.documentElement.scrollHeight - window.innerHeight,
      stage: document.querySelector('.sing-stage')!.getBoundingClientRect().height,
      lyrics: document.querySelector('.sing-lyrics')!.getBoundingClientRect().height,
    }));
    const first = await measure();
    expect(first.overflow).toBeLessThanOrEqual(1); // no scrolling
    for (let i = 0; i < 12; i++) { // sample while the song plays: nothing may change size
      await page.waitForTimeout(1000);
      const now = await measure();
      expect(now.overflow).toBeLessThanOrEqual(1);
      expect(now.stage).toBeCloseTo(first.stage, 0);
      expect(now.lyrics).toBeCloseTo(first.lyrics, 0);
    }
    await page.screenshot({ path: `artifacts/layout-${viewport.width}x${viewport.height}.png` });
    await browser.close();
  });
}

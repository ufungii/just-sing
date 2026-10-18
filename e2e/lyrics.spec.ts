import { chromium, expect, test } from '@playwright/test';
import { addPlayer, duetPlayer, mic, openOnlineDuet } from './duetHarness';

// A synthetic microphone and the built-in duet fixture exercise recording/uploading without song assets.
test('local multiplayer uploads both singers and displays two independent lyrics bars', async ({ baseURL }) => {
  const browser = await chromium.launch({ args: ['--autoplay-policy=no-user-gesture-required'] });
  try {
    const { page, errors } = await duetPlayer(browser, baseURL!);
    await page.addInitScript(() => localStorage.setItem('just-sing.showTestClips', '1'));
    await page.goto('/');
    await page.getByText('LOCAL', { exact: true }).first().click();
    await page.getByRole('button', { name: '2 PLAYERS', exact: true }).click();
    await page.getByRole('button').filter({ has: page.getByText('Duet Demo (synthetic)', { exact: true }) }).click();
    await addPlayer(page, 'PLAYER 1', 'E2E-Bot-lyrics-local');
    await addPlayer(page, 'PLAYER 2', 'E2E-Rival-lyrics-local');
    await mic(page);
    const created = page.waitForResponse((r) => r.url().endsWith('/api/matches') && r.request().method() === 'POST' && r.status() === 200);
    await page.getByRole('button', { name: 'FIGHT ♪', exact: true }).click();
    const mid = (await (await created).json()).match_id;
    const uploads: number[] = [];
    page.on('response', (r) => { if (/\/turns\/[^/]+\/lyric-check$/.test(r.url())) uploads.push(r.status()); });
    await page.getByRole('button', { name: 'READY TO SING', exact: true }).click();
    await expect(page.locator('.battle-headline')).toBeVisible({ timeout: 45_000 });
    await expect.poll(() => uploads.filter((status) => status === 200).length).toBe(2);
    await expect(page.getByRole('meter', { name: 'LYRICS', exact: true })).toHaveCount(2);
    await expect(page.getByText('Checking this singer’s lyrics…', { exact: true })).toHaveCount(0, { timeout: 15_000 });
    const saved = await (await page.request.get(`/api/matches/${mid}`)).json();
    expect(saved.attempts.every((a: any) => a.score.lyrics && a.score.lyrics.status !== 'pending')).toBe(true);
    if (process.env.E2E_REQUIRE_LYRICS === '1') {
      expect(saved.attempts.map((a: any) => a.score.lyrics.status)).toEqual(['ok', 'ok']);
      await expect(page.getByText('4/6', { exact: true })).toBeVisible();
      await expect(page.getByText('1/3', { exact: true })).toBeVisible();
    }
    await page.screenshot({ path: 'e2e/artifacts/multiplayer-lyrics-local.png', fullPage: true });
    expect(errors).toEqual([]);
  } finally { await browser.close(); }
});

test('online multiplayer uploads each own recording and both clients receive both lyrics bars', async ({ baseURL }) => {
  const browser = await chromium.launch({ args: ['--autoplay-policy=no-user-gesture-required'] });
  try {
    const { page: host, errors: hostErrors } = await duetPlayer(browser, baseURL!);
    const { page: guest, errors: guestErrors } = await duetPlayer(browser, baseURL!);
    const uploads: number[][] = [[], []];
    for (const [slot, page] of [host, guest].entries()) {
      await page.addInitScript(() => localStorage.setItem('just-sing.showTestClips', '1'));
      page.on('response', (r) => { if (/\/turns\/[^/]+\/lyric-check$/.test(r.url())) uploads[slot].push(r.status()); });
    }
    await openOnlineDuet(host, guest, 'duet-demo');
    await host.getByRole('button', { name: 'READY TO SING', exact: true }).click();
    await guest.getByRole('button', { name: 'READY TO SING', exact: true }).click();
    for (const page of [host, guest]) {
      await expect(page.locator('.battle-headline')).toBeVisible({ timeout: 45_000 });
      await expect(page.getByRole('meter', { name: 'LYRICS', exact: true })).toHaveCount(2);
      await expect(page.getByText('Checking this singer’s lyrics…', { exact: true })).toHaveCount(0, { timeout: 15_000 });
      if (process.env.E2E_REQUIRE_LYRICS === '1') {
        await expect(page.getByText('4/6', { exact: true })).toBeVisible();
        await expect(page.getByText('1/3', { exact: true })).toBeVisible();
      }
    }
    expect(uploads.map((responses) => responses.filter((s) => s === 200).length)).toEqual([1, 1]);
    await host.screenshot({ path: 'e2e/artifacts/multiplayer-lyrics-online.png', fullPage: true });
    expect([...hostErrors, ...guestErrors]).toEqual([]);
  } finally { await browser.close(); }
});

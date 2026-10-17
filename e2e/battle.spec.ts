import { chromium, expect, test } from '@playwright/test';
import { addPlayer, assigned, duetPlayer, expectOnePlayback, expectOwnedScores, manifest, mic, schedules } from './duetHarness';

/** One shared capture/playback, automatic P1→P2→P1 handoffs, two register-specific results. */
test('local duet: one song and microphone session, automatic handoffs, disjoint saved scores', async ({ baseURL }) => {
  const browser = await chromium.launch({ args: ['--autoplay-policy=no-user-gesture-required'] });
  try {
    const { page, errors } = await duetPlayer(browser, baseURL!);
    await page.goto('/');
    const song = await manifest(page);
    await page.getByText('1P VS 2P', { exact: true }).first().click();
    await page.getByRole('button', { name: new RegExp(song.title, 'i') }).click();
    await addPlayer(page, 'PLAYER 1', 'E2E-Bot-duet-local');
    await addPlayer(page, 'PLAYER 2', 'E2E-Rival-duet-local');
    await page.getByRole('group', { name: 'Player 2 voice range' }).getByRole('button', { name: 'HIGH', exact: true }).click();
    await mic(page);
    const created = page.waitForResponse((r) => r.url().endsWith('/api/matches') && r.request().method() === 'POST' && r.status() === 200);
    await page.getByRole('button', { name: 'FIGHT ♪', exact: true }).click();
    const mid = (await (await created).json()).match_id;
    // One transient save failure must retry the captured results, never replay the song.
    let failedUrl = '';
    const retriedKeys: string[] = [];
    await page.route('**/api/turns/*/result', async (route) => {
      const url = route.request().url();
      if (!failedUrl) {
        failedUrl = url;
        retriedKeys.push((await route.request().headerValue('Idempotency-Key'))!);
        return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { code: 'unavailable', message: 'Temporary save failure.', retryable: true } }) });
      }
      if (url === failedUrl) retriedKeys.push((await route.request().headerValue('Idempotency-Key'))!);
      return route.continue();
    });
    const ready = page.waitForResponse((r) => r.url().endsWith('/duet/ready'));
    await page.getByRole('button', { name: 'READY TO SING', exact: true }).click();
    const frozen = await (await ready).json();
    expect(frozen.attempts.map((a: any) => a.register)).toEqual([0, 12]);
    expect(frozen.duet.sections.map((s: any) => s.slot)).toEqual([0, 1, 0]);
    await expectOnePlayback(page, frozen.duet.start_at, 0, song.duration);
    await expect(page.getByTestId('duet-current')).toHaveAttribute('data-slot', '1', { timeout: 25_000 });
    await expect(page.getByTestId('duet-next')).toContainText('P1');
    expect(await schedules(page)).toHaveLength(2);
    await page.screenshot({ path: 'e2e/artifacts/duet-local-handoff.png', mask: [page.locator('.sing-lyrics')] });
    await expect(page.getByTestId('duet-current')).toHaveAttribute('data-slot', '0', { timeout: 20_000 });
    expect(await page.evaluate(() => (window as any).__micOpens)).toBe(2); // setup mic check + one shared singing stream
    await page.getByRole('button', { name: 'RETRY SAVE', exact: true }).click({ timeout: 20_000 });
    await expect.poll(() => retriedKeys.length).toBe(2);
    expect(new Set(retriedKeys).size).toBe(1);
    await expect(page.locator('.battle-headline')).toContainText(/WINS|TIE/, { timeout: 20_000 });
    const match = await (await page.request.get(`/api/matches/${mid}`)).json();
    expectOwnedScores(match, song.phrases.map((p: any) => p.id));
    expect(assigned(match, 0)).toHaveLength(4);
    expect(assigned(match, 1)).toHaveLength(3);
    expect(await schedules(page)).toHaveLength(2);
    const history = (await (await page.request.get('/api/history')).json())[0];
    expect(history.duet).toBe(true);
    expect(history.range).toBeNull();
    await expect(page.getByText(/Practice section/)).toHaveCount(0);
    expect(errors).toEqual([]);
  } finally { await browser.close(); }
});

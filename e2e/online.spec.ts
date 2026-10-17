import { chromium, expect, test } from '@playwright/test';
import { duetPlayer, expectOnePlayback, expectOwnedScores, openOnlineDuet, schedules } from './duetHarness';

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
      expect(await page.evaluate(() => (window as any).__micOpens)).toBe(2);
    }
    expect([...hostErrors, ...guestErrors]).toEqual([]);
  } finally { await browser.close(); }
});

test('online duet: reload after shared start never replays one player, explicit restart resets both', async ({ baseURL }) => {
  const browser = await chromium.launch({ args: ['--autoplay-policy=no-user-gesture-required'] });
  try {
    const { page: host, errors: hostErrors } = await duetPlayer(browser, baseURL!);
    const { page: guest, errors: guestErrors } = await duetPlayer(browser, baseURL!);
    const { code } = await openOnlineDuet(host, guest);
    await host.getByRole('button', { name: 'READY TO SING' }).click();
    const prepared = guest.waitForResponse((r) => r.url().endsWith('/duet/ready'));
    await guest.getByRole('button', { name: 'READY TO SING' }).click();
    const frozen = await (await prepared).json();
    await guest.waitForFunction((at) => (performance.timeOrigin + performance.now()) / 1000 > at + 0.2, frozen.duet.start_at);
    await guest.reload();
    await guest.getByText('ONLINE', { exact: true }).first().click();
    await guest.getByLabel('Room code').fill(code);
    await guest.getByRole('button', { name: 'JOIN', exact: true }).click();
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

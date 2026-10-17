import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.route('**/api/**', route => route.fulfill({ json: [] }));
  await page.addInitScript(() => localStorage.setItem('just-sing.players', JSON.stringify({
    players: [{ id: 'mina', name: 'Mina', avatar: 'bunny' }, { id: 'old-zibran', name: 'ZIBRAN', avatar: 'kitty' }],
    lastId: 'mina',
  })));
});

for (const edit of [false, true]) {
  for (const submit of [false, true]) {
    test(`${edit ? 'rename' : 'add'} player triggers on ${submit ? 'Enter' : 'blur'} without saving`, async ({ page }) => {
      await page.goto('/');
      await page.getByRole('button', { name: 'PLAYERS', exact: true }).click();
      await page.getByRole('button', { name: edit ? 'Edit Mina' : '+ ADD PLAYER', exact: true }).click();
      const input = page.getByRole('textbox', { name: 'NAME', exact: true });
      await input.fill('  ZiBrAn  ');
      await input.press(submit ? 'Enter' : 'Tab');
      await expect(page.getByText('ZIBRAN HAS BEEN BANNED.', { exact: true })).toBeVisible();
      const players = await page.evaluate(() => JSON.parse(localStorage.getItem('just-sing.players')!).players);
      expect(players.map((p: { name: string }) => p.name)).toEqual(['Mina', 'ZIBRAN']);
      await page.getByRole('button', { name: 'APPEAL BAN ♪', exact: true }).click();
      await expect(page.getByRole('button', { name: 'PLAYERS', exact: true })).toBeVisible();
    });
  }
}

test('selecting an existing Zibran profile also triggers the egg', async ({ page }) => {
  await page.goto('/#solo');
  await page.getByRole('combobox').click();
  await page.getByRole('option', { name: 'ZIBRAN' }).click();
  await expect(page.getByText('ZIBRAN HAS BEEN BANNED.', { exact: true })).toBeVisible();
});

test('a longer name containing zibran can still be added', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'PLAYERS', exact: true }).click();
  await page.getByRole('button', { name: '+ ADD PLAYER', exact: true }).click();
  await page.getByRole('textbox', { name: 'NAME', exact: true }).fill('zibran123');
  await page.getByRole('button', { name: 'ADD PLAYER', exact: true }).click();
  await expect(page.locator('.players-row__name', { hasText: 'zibran123' })).toBeVisible();
});

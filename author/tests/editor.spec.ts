import { test, expect } from '@playwright/test';

test('review lyrics, assign whole lines, drag, save and rebuild', async ({page}, testInfo) => {
  await page.goto('/');
  await page.getByLabel('Song', {exact:true}).selectOption('test-song');
  await expect(page.getByRole('status')).toContainText('Loaded.');
  await expect(page.getByRole('button', {name:'Play',exact:true})).toBeEnabled();
  // section without heading-based accessible role: use its explicit aria label.
  const lines = page.locator('section[aria-label="Lyric lines"] .lyric');
  await expect(lines.first()).toContainText('\uc548\ub155');
  await expect(lines.first()).toContainText('annyeong');
  await lines.first().click(); await lines.nth(1).click({modifiers:['Control']});
  await page.getByRole('button',{name:'Assign Player 2',exact:true}).click();
  await expect(lines.first()).toContainText('Player 2'); await expect(lines.nth(1)).toContainText('Player 2');
  await page.getByRole('button',{name:'Undo',exact:true}).click();
  await expect(lines.first()).toContainText('Player 1');
  await page.getByRole('button',{name:'Redo',exact:true}).click();
  await expect(lines.first()).toContainText('Player 2');
  const block = page.locator('.clip-timeline__line').first();
  await block.scrollIntoViewIfNeeded();
  const box = (await block.boundingBox())!;
  await page.mouse.move(box.x+10,box.y+20); await page.mouse.down();
  await page.mouse.move(box.x+26,box.y+20,{steps:5});
  await expect(block).toHaveAttribute('data-dragging','valid');
  await expect(page.locator('.clip-timeline__drag-readout')).toContainText('Release to place');
  await expect(page.getByLabel('Line start',{exact:true})).toHaveValue('1'); // only preview until release
  await page.mouse.up();
  await block.click();
  await expect(page.getByLabel('Line start',{exact:true})).not.toHaveValue('1');
  await page.screenshot({path:testInfo.outputPath('author.png'),fullPage:true});
  await page.getByRole('button',{name:'Save',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('Saved corrections');
  await page.getByRole('button',{name:'Rebuild',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('Rebuilt manifest');
  await page.reload(); await page.getByLabel('Song',{exact:true}).selectOption('test-song');
  await expect(page.getByRole('status')).toContainText('Loaded.');
  await expect(lines.first()).toContainText('Player 2');
  await expect(page.getByLabel('Line start',{exact:true})).not.toHaveValue('1');
});

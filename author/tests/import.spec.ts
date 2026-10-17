import { test, expect } from '@playwright/test';

test('add raw recording, recover progress after reload and open its new draft', async ({page}) => {
  await page.goto('/');
  await page.getByRole('button',{name:'Add song',exact:true}).click();
  await page.getByLabel('Song title',{exact:true}).fill('New synthetic recording');
  await page.getByLabel('Artist',{exact:true}).fill('Test singer');
  await page.getByLabel('Language',{exact:true}).selectOption('en');
  await page.getByLabel('Lyrics',{exact:true}).fill('Hello world\nHello again');
  await page.getByLabel('Audio file',{exact:true}).setInputFiles({name:'generated.wav',mimeType:'audio/wav',buffer:Buffer.from('fixture audio; inference mocked by disposable server')});
  const submitted=page.waitForResponse((r)=>r.url().endsWith('/api/imports')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Process song',exact:true}).click();
  expect((await submitted).status()).toBe(202);
  await page.reload();
  await expect(page.locator('.import-job [role=status]')).toContainText('Draft ready',{timeout:15000});
  await page.getByRole('button',{name:'Open draft',exact:true}).click();
  await expect(page.getByLabel('Song',{exact:true})).toHaveValue('new-synthetic-recording');
  await expect(page.getByRole('button',{name:'Play',exact:true})).toBeEnabled();
  await expect(page.locator('.lyric')).toHaveCount(2);
  const songs=await (await page.request.get('/api/songs')).json();
  expect(songs.map((s:{id:string})=>s.id)).toContain('test-song');
  expect(songs.map((s:{id:string})=>s.id)).toContain('new-synthetic-recording');
});

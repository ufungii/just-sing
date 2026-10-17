import { chromium, expect, test, type Browser, type Page } from '@playwright/test';

const CLIP = 'russian-roulette';
const NAME = `E2E-Bot-range-${Date.now().toString(36)}`;

async function player(browser: Browser, baseURL: string) {
  const page = await (await browser.newContext({ baseURL })).newPage();
  await page.addInitScript(() => {
    (window as any).__starts = [];
    (window as any).__sources = [];
    const start = AudioBufferSourceNode.prototype.start;
    AudioBufferSourceNode.prototype.start = function (when = 0, offset = 0, duration?: number) {
      (window as any).__starts.push({ when, offset, duration, now: this.context.currentTime });
      (window as any).__sources.push(this);
      if (duration === undefined) start.call(this, when, offset);
      else start.call(this, when, offset, duration);
    };
    navigator.mediaDevices.getUserMedia = async () => {
      const ctx = new AudioContext();
      await ctx.resume();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      gain.gain.value = 0.15;
      osc.frequency.value = 220;
      const dest = ctx.createMediaStreamDestination();
      osc.connect(gain).connect(dest);
      osc.start();
      for (const track of dest.stream.getTracks()) {
        const stop = track.stop.bind(track);
        track.stop = () => { stop(); void ctx.close(); };
      }
      return dest.stream;
    };
  });
  return page;
}

async function chooseSection(page: Page, song: any, readOnly = false, endPhrase = 1) {
  await page.bringToFront();
  const start = page.getByRole('slider', { name: 'Start of practice section' });
  const end = page.getByRole('slider', { name: 'End of practice section' });
  await expect(start).toBeVisible();
  if (readOnly) {
    await expect(start).toBeDisabled();
    await expect(end).toBeDisabled();
    return;
  }
  await expect(start).toBeEnabled();
  await start.scrollIntoViewIfNeeded();
  // Move the handles with a real pointer, aiming between phrase boundaries to exercise snapping.
  const track = await page.locator('.clip-timeline__track').boundingBox();
  const knob = await start.boundingBox();
  await page.mouse.move(knob!.x + knob!.width / 2, knob!.y + knob!.height / 2);
  await page.mouse.down();
  await page.mouse.move(track!.x + (song.phrases[1].start + 0.04) / song.duration * track!.width, knob!.y + 30, { steps: 5 });
  await page.mouse.up();
  await expect(start).toHaveAttribute('aria-valuenow', String(song.phrases[1].start));
  // Keyboard End/Home chooses a valid phrase boundary and keeps the handle within view.
  await expect(end).toBeEnabled();
  await end.focus();
  if (endPhrase === 1) await end.press('Home');
  else for (let i = song.phrases.length - 2; i >= endPhrase; i--) {
    await expect(end).toBeEnabled();
    await end.press('ArrowLeft');
    await expect(end).toHaveAttribute('aria-valuenow', String(song.phrases[i].end));
  }
  await expect(end).toHaveAttribute('aria-valuenow', String(song.phrases[endPhrase].end));
}

async function mic(page: Page) {
  await page.getByRole('button', { name: 'TEST MIC' }).click();
  await expect(page.getByText('Mic works!')).toBeVisible({ timeout: 15_000 });
}

async function sing(page: Page, range: { start: number; end: number }) {
  const button = page.getByRole('button', { name: '▶ START', exact: true });
  await expect(button).toBeVisible({ timeout: 20_000 });
  const begin = page.waitForRequest((r) => r.url().endsWith('/begin'));
  const result = page.waitForResponse((r) => /\/turns\/[^/]+\/result$/.test(r.url()) && r.request().method() === 'POST');
  await page.evaluate(() => { (window as any).__starts = []; });
  await button.click();
  expect((await begin).postDataJSON().range).toEqual(range);
  await expect.poll(() => page.evaluate(() => (window as any).__starts.length)).toBeGreaterThanOrEqual(2);
  const sources = await page.evaluate(() => (window as any).__starts);
  for (const src of sources) {
    expect(src.offset).toBe(range.start);
    expect(src.duration).toBeCloseTo(range.end - range.start);
    expect(src.when - src.now).toBeGreaterThan(3);
    expect(src.when - src.now).toBeLessThan(3.3);
  }
  const response = await result;
  expect(response.status()).toBe(200);
  const saved = await response.json();
  expect(saved.range).toEqual(range);
  return saved;
}

test('solo middle section: snapped handles, preview, offset audio, saved subset and history', async ({ baseURL }) => {
  const browser = await chromium.launch({ args: ['--autoplay-policy=no-user-gesture-required'] });
  try {
    const page = await player(browser, baseURL!);
    const errors: string[] = [];
    page.on('pageerror', (e) => errors.push(String(e)));
    await page.goto('/');
    await expect.poll(async () => {
      const response = await page.request.get('/api/ready', { timeout: 60_000 });
      return (await response.json()).database;
    }, { timeout: 90_000 }).toBe('ok');
    const manifest = await page.request.get(`/api/clips/${CLIP}/manifest`);
    expect(manifest.status(), 'local russian-roulette manifest is required').toBe(200);
    const song = await manifest.json();
    const range = { start: song.phrases[1].start, end: song.phrases[1].end };
    await page.getByText('SOLO SING', { exact: true }).first().click();
    await page.getByRole('button').filter({ has: page.getByText(song.title, { exact: true }) }).click();
    await chooseSection(page, song);
    await page.getByRole('button', { name: 'FULL CLIP', exact: true }).click();
    await expect(page.getByRole('slider', { name: 'Start of practice section' })).toHaveAttribute('aria-valuenow', '0');
    await chooseSection(page, song);
    // A missing optional vocal stem still permits instrumental preview.
    await page.route('**/api/clips/*/vocals', (route) => route.fulfill({ status: 404 }));
    await page.evaluate(() => { (window as any).__starts = []; (window as any).__sources = []; });
    await page.getByRole('button', { name: 'PLAY PREVIEW ▶' }).click();
    await expect(page.locator('.clip-timeline__playhead')).toBeVisible();
    expect(await page.evaluate(() => (window as any).__starts.length)).toBe(1);
    await page.getByRole('button', { name: 'STOP PREVIEW' }).click();
    await page.unroute('**/api/clips/*/vocals');
    await page.evaluate(() => { (window as any).__starts = []; });
    await page.getByRole('button', { name: 'PLAY PREVIEW ▶' }).click();
    await expect(page.locator('.clip-timeline__playhead')).toBeVisible();
    const previewSources = await page.evaluate(() => (window as any).__starts);
    expect(previewSources).toHaveLength(2);
    for (const src of previewSources) {
      expect(src.when).toBe(previewSources[0].when);
      expect(src.offset).toBe(range.start);
      expect(src.duration).toBeCloseTo(range.end - range.start);
    }
    // A vocal stem ending early must leave the instrumental preview running.
    await page.evaluate(() => (window as any).__sources.at(-1).dispatchEvent(new Event('ended')));
    await expect(page.getByRole('button', { name: 'STOP PREVIEW' })).toBeVisible();
    await page.getByRole('button', { name: 'STOP PREVIEW' }).click();
    // Keep screenshots lyric-free; the actual manifest is used for all selection/scoring assertions.
    await page.screenshot({ path: 'e2e/artifacts/range-solo-setup.png', mask: [page.locator('.clip-timeline__line')] });
    await page.getByPlaceholder('e.g. Mina').fill(NAME);
    await mic(page);
    await page.getByRole('button', { name: 'START ♪', exact: true }).click();
    const saved = await sing(page, range);
    expect(saved.phrases.map((p: any) => p.phrase_id)).toEqual([song.phrases[1].id]);
    await expect(page.getByText('saved to your history')).toBeVisible();
    await expect(page.getByText(/Practice section/)).toBeVisible();
    await expect(page.locator('.results-phrase')).toHaveCount(1);
    const history = await (await page.request.get('/api/history')).json();
    expect(history).toHaveLength(1);
    expect(history[0].range).toEqual(range);
    const match = await (await page.request.get(`/api/matches/${history[0].match_id}`)).json();
    expect(match.attempts[0].score.range).toEqual(range);
    await page.getByRole('button', { name: /HISTORY/ }).click();
    await expect(page.locator('.history-row')).toContainText('Practice section');
    expect(errors).toEqual([]);
  } finally { await browser.close(); }
});

test('full-screen practice workspace applies precise phrase-snapped boundaries and aligned preview', async ({baseURL})=>{
  const browser=await chromium.launch({args:['--autoplay-policy=no-user-gesture-required']});
  try{
    const page=await player(browser,baseURL!);
    await page.goto('/');
    const song=await (await page.request.get(`/api/clips/${CLIP}/manifest`)).json();
    await page.getByText('SOLO SING',{exact:true}).first().click();
    await page.getByRole('button').filter({has:page.getByText(song.title,{exact:true})}).click();
    await page.getByRole('button',{name:'OPEN SECTION EDITOR',exact:true}).click();
    const dialog=page.getByRole('dialog',{name:'Choose a practice section'});
    await expect(dialog).toBeVisible();
    const lyrics=dialog.getByRole('region',{name:'Song lyrics',exact:true});
    const scrubber=dialog.getByRole('slider',{name:'Song position',exact:true});
    expect((await lyrics.boundingBox())!.y).toBeLessThan((await scrubber.boundingBox())!.y);
    const scrubBox=(await scrubber.boundingBox())!;
    const seekTime=(song.lines[1].start+song.lines[1].end)/2;
    await page.mouse.click(scrubBox.x+scrubBox.width*seekTime/song.duration,scrubBox.y+scrubBox.height/2);
    await expect(lyrics.locator('[data-current=true]')).toHaveAttribute('data-line-index','1');
    // Dragging an endpoint updates the lyric selection before the pointer is released.
    const endHandle=dialog.getByRole('slider',{name:'End of practice section',exact:true});
    const endBox=(await endHandle.boundingBox())!;
    await page.mouse.move(endBox.x+endBox.width/2,endBox.y+endBox.height/2);await page.mouse.down();
    await page.mouse.move(scrubBox.x+scrubBox.width*song.phrases[3].end/song.duration,endBox.y+endBox.height/2,{steps:4});
    await expect(endHandle).toHaveAttribute('aria-valuenow',String(song.phrases[3].end));
    await expect(lyrics.locator('[data-in-selection=true]')).toHaveCount(4);
    await page.mouse.up();
    const range={start:song.phrases[1].start,end:song.phrases[1].end};
    await dialog.getByLabel('Section start',{exact:true}).fill(String(range.start+.03));
    await dialog.getByLabel('Section start',{exact:true}).press('Enter');
    await dialog.getByLabel('Section end',{exact:true}).fill(String(range.end-.03));
    await dialog.getByLabel('Section end',{exact:true}).press('Enter');
    await expect(dialog.getByRole('slider',{name:'Start of practice section'})).toHaveAttribute('aria-valuenow',String(range.start));
    await expect(dialog.getByRole('slider',{name:'End of practice section'})).toHaveAttribute('aria-valuenow',String(range.end));
    const selectedLine=song.phrases[1].line_index;
    await expect(lyrics.locator('[data-in-selection=true]')).toHaveCount(1);
    await expect(lyrics.locator(`[data-line-index="${selectedLine}"] [data-boundary=start]`)).toBeVisible();
    await expect(lyrics.locator(`[data-line-index="${selectedLine}"] [data-boundary=end]`)).toBeVisible();
    await dialog.getByRole('button',{name:'Fit selection',exact:true}).click();
    await page.setViewportSize({width:390,height:844});
    await expect(lyrics.locator('[data-current=true]')).toBeInViewport();
    expect(await dialog.evaluate(node=>node.scrollWidth)).toBeLessThanOrEqual(390);
    await page.setViewportSize({width:1280,height:720});
    await dialog.getByRole('button',{name:'Preview selection',exact:true}).click();
    await expect.poll(()=>page.evaluate(()=>(window as any).__starts.length)).toBe(2);
    for(const src of await page.evaluate(()=>(window as any).__starts)){
      expect(src.offset).toBe(range.start);expect(src.duration).toBeCloseTo(range.end-range.start);
    }
    await expect.poll(async()=>Number(await scrubber.inputValue())).toBeGreaterThan(range.start+.1);
    await dialog.getByRole('button',{name:'Stop preview',exact:true}).click();
    expect(Number(await scrubber.inputValue())).toBeGreaterThan(range.start+.1);
    await dialog.getByRole('button',{name:'Use this practice section',exact:true}).click();
    await expect(dialog).toHaveCount(0);
    await expect(page.getByRole('slider',{name:'Start of practice section'})).toHaveAttribute('aria-valuenow',String(range.start));
    await expect(page.getByRole('slider',{name:'End of practice section'})).toHaveAttribute('aria-valuenow',String(range.end));
  }finally{await browser.close();}
});

test('online host section: guest read-only, readiness reset, shared range with disjoint assigned phrases', async ({ baseURL }) => {
  const browser = await chromium.launch({ args: ['--autoplay-policy=no-user-gesture-required'] });
  try {
    const host = await player(browser, baseURL!);
    const guest = await player(browser, baseURL!);
    await host.goto('/');
    const song = await (await host.request.get(`/api/clips/${CLIP}/manifest`)).json();
    const range = { start: song.phrases[1].start, end: song.phrases[3].end };
    await host.getByText('ONLINE', { exact: true }).first().click();
    await host.getByPlaceholder('e.g. Mina').fill(`${NAME}-host`);
    await host.getByRole('button').filter({ has: host.getByText(song.title, { exact: true }) }).click();
    await host.getByRole('button', { name: /CREATE ROOM/ }).click();
    const code = await host.getByTestId('room-code').innerText();
    await guest.goto('/');
    await guest.getByText('ONLINE', { exact: true }).first().click();
    await guest.getByPlaceholder('e.g. Mina').fill(`${NAME}-guest`);
    await guest.getByLabel('Room code').fill(code);
    await guest.getByRole('button', { name: 'JOIN', exact: true }).click();
    await chooseSection(guest, song, true);
    // A failed host edit restores the durable full-clip selection.
    await host.route('**/api/rooms/*/range', (route) => route.fulfill({ status: 503, contentType: 'application/json',
      body: JSON.stringify({ error: { code: 'unavailable', message: 'Range save unavailable.', retryable: true } }) }));
    const hostStart = host.getByRole('slider', { name: 'Start of practice section' });
    await hostStart.press('ArrowRight');
    await expect(host.getByText('Range save unavailable.')).toBeVisible();
    await expect(hostStart).toHaveAttribute('aria-valuenow', '0');
    await host.unroute('**/api/rooms/*/range');
    for (const page of [host, guest]) { await mic(page); await page.getByRole('button', { name: 'READY ✓', exact: true }).click(); }
    await chooseSection(host, song, false, 3);
    await expect(guest.getByRole('slider', { name: 'Start of practice section' })).toHaveAttribute('aria-valuenow', String(range.start));
    await expect(guest.getByRole('slider', { name: 'End of practice section' })).toHaveAttribute('aria-valuenow', String(range.end));
    await guest.getByRole('button',{name:'OPEN SECTION EDITOR',exact:true}).click();
    const guestWorkspace=guest.getByRole('dialog',{name:'View practice section'});
    await expect(guestWorkspace.getByLabel('Section start',{exact:true})).toBeDisabled();
    await expect(guestWorkspace.getByLabel('Section end',{exact:true})).toBeDisabled();
    await expect(guestWorkspace.getByRole('button',{name:'Use this practice section',exact:true})).toHaveCount(0);
    await guestWorkspace.getByRole('button',{name:'Close / back',exact:true}).click();
    await expect(host.getByRole('button', { name: 'START (BOTH MUST BE READY)' })).toBeDisabled();
    // A full reload recovers the host selection from the server (join again with the same cookie).
    await guest.reload();
    await guest.getByText('ONLINE', { exact: true }).first().click();
    await guest.getByLabel('Room code').fill(code);
    await guest.getByRole('button', { name: 'JOIN', exact: true }).click();
    await expect(guest.getByRole('slider', { name: 'Start of practice section' })).toHaveAttribute('aria-valuenow', String(range.start));
    await mic(guest);
    for (const page of [host, guest]) await page.getByRole('button', { name: 'READY ✓', exact: true }).click();
    await host.getByRole('button', { name: 'START ♪', exact: true }).click();
    for (const page of [host, guest]) await expect(page.getByRole('button', { name: 'READY TO SING' })).toBeVisible();
    const frozenResponse = guest.waitForResponse((r) => r.url().endsWith('/duet/ready'));
    await host.getByRole('button', { name: 'READY TO SING' }).click();
    await guest.getByRole('button', { name: 'READY TO SING' }).click();
    const frozen = await (await frozenResponse).json();
    expect(frozen.duet.range).toEqual(range);
    for (const page of [host, guest]) {
      await expect.poll(() => page.evaluate(() => (window as any).__starts.length)).toBe(2);
      for (const src of await page.evaluate(() => (window as any).__starts)) {
        expect(src.offset).toBe(range.start);
        expect(src.duration).toBeCloseTo(range.end - range.start);
      }
    }
    for (const page of [host, guest]) await expect(page.locator('.battle-headline')).toBeVisible({ timeout: 30_000 });
    const finished = await (await host.request.get(`/api/matches/${frozen.id}`)).json();
    expect(finished.attempts).toHaveLength(2);
    const expected = [[song.phrases[1].id, song.phrases[2].id], [song.phrases[3].id]];
    for (const attempt of finished.attempts) {
      expect(attempt.score.range).toEqual(range);
      expect(attempt.score.phrases.map((p: any) => p.phrase_id)).toEqual(expected[attempt.slot]);
    }
    for (const page of [host, guest]) {
      await expect(page.locator('.battle-headline')).toBeVisible();
      await expect(page.getByText(/Practice section/)).toHaveCount(2);
      expect((await (await page.request.get('/api/history')).json())[0].range).toEqual(range);
    }
  } finally { await browser.close(); }
});

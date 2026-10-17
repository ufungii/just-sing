import { scorePhrase, aggregate } from "./scoring.js";
import { CaptureWindow } from "./capture-worklet.js";
import { PitchDetector } from "./vendor/pitchy.mjs";
import { createPlayback } from "./playback.js";
import { lyricDisplay } from "./lyric_display.js";
import { apiUrl } from "./urls.js";

Deno.test("API URLs retain the mounted karaoke prefix and standalone origin", () => {
  for (const [moduleUrl, expected] of [
    ["http://localhost:8000/live/urls.js", "http://localhost:8000/api/songs"],
    ["http://localhost:8000/karaoke/live/urls.js", "http://localhost:8000/karaoke/api/songs"],
    ["https://demo.example/karaoke/live/urls.js", "https://demo.example/karaoke/api/songs"],
  ]) {
    if (apiUrl("/api/songs", moduleUrl) !== expected) throw new Error("Playback API escaped its mount");
    if (apiUrl(expected, moduleUrl) !== expected) throw new Error("Already resolved URL changed");
  }
});

Deno.test("guide vocals share the playback clock through toggle, pause and seek", () => {
  const sources = [], gains = [];
  const node = () => ({ connect(target) { return target; }, disconnect() { this.disconnected = true; } });
  const context = { currentTime: 8, destination: {},
    createBufferSource() { const result = { ...node(), starts: [], stopCount: 0,
      start(...args) { this.starts.push(args); }, stop() { this.stopCount++; } }; sources.push(result); return result; },
    createGain() { const result = { ...node(), gain: { value: 1, setTargetAtTime(value) { this.value = value; } } }; gains.push(result); return result; },
  };
  let ended = 0;
  const playback = createPlayback(context, {}, {}, 8.06, 32.5, () => ended++);
  if (JSON.stringify(sources.map((s) => s.starts)) !== JSON.stringify([[[8.06, 32.5]], [[8.06, 32.5]]])) throw new Error("Stems not synchronized");
  playback.setVocals(true);
  if (gains[0].gain.value !== 0.5 || gains[1].gain.value !== 0.5) throw new Error("Default vocal volume incorrect");
  playback.setVocals(true, 1);
  if (Math.abs(gains[0].gain.value - 1 / 3) > 1e-9 || Math.abs(gains[1].gain.value - 2 / 3) > 1e-9) throw new Error("Full vocal volume incorrect or lacks headroom");
  playback.setVocals(true, 0);
  if (gains[0].gain.value !== 1 || gains[1].gain.value !== 0) throw new Error("Zero vocal volume is not muted");
  playback.setVocals(false);
  if (gains[0].gain.value !== 1 || gains[1].gain.value !== 0 || sources[0].starts.length !== 1) throw new Error("Toggle restarted playback");
  playback.stop(); playback.stop();
  if (ended || sources.some((s) => s.stopCount !== 1) || sources[0].onended !== null) throw new Error("Pause failed to stop both stems safely");
  const resumed = createPlayback(context, {}, {}, 9, 45, () => ended++);
  sources[2].onended();
  if (ended !== 1 || sources[3].stopCount !== 1) throw new Error("End did not clean up guide");
  resumed.stop();
});

Deno.test("romanized display reuses word intervals and falls back safely", () => {
  const line = { text: "original text", romanized: "romanized words", words: [
    { text: "original", start: 1, end: 2 }, { text: "text", start: 2.1, end: 3 }] };
  const display = lyricDisplay(line, true);
  if (display.words[1].text !== "words" || display.words[1].start !== 2.1 || display.words[1].end !== 3) throw new Error("Romanization changed timestamps");
  if (lyricDisplay(line, false).words !== line.words || line.words[0].text !== "original") throw new Error("Original text changed");
  if (lyricDisplay({ ...line, romanized: "different spacing here" }, true).words.length) throw new Error("Guessed word timings");
  if (lyricDisplay({ ...line, romanized: "" }, true).text !== line.text) throw new Error("Missing romanization lost original");
});

const fixtures = JSON.parse(await Deno.readTextFile(new URL("../../contracts/fixtures/live_scoring.json", import.meta.url)));
for (const c of fixtures.cases) Deno.test(`shared score: ${c.name}`, () => {
  const result = scorePhrase(c.reference, c.observations, c.start, c.end, c.register, c.latency_seconds, fixtures.config);
  for (const [key, expected] of Object.entries(c.expected)) {
    if (typeof expected === "number" ? Math.abs(result[key] - expected) > 1e-6 : result[key] !== expected)
      throw new Error(`${key}: expected ${expected}, received ${result[key]}`);
  }
});

Deno.test("capture windows preserve sample order and timestamp their centers", () => {
  const capture = new CaptureWindow(8, 2), result = [];
  for (let i = 0; i < 10; i++) { const frame = capture.push(i, i, 8000); if (frame) result.push(frame); }
  if (JSON.stringify([...result[0].samples]) !== JSON.stringify([0,1,2,3,4,5,6,7])) throw new Error("Initial sample ordering");
  if (JSON.stringify([...result[1].samples]) !== JSON.stringify([2,3,4,5,6,7,8,9])) throw new Error("Ring ordering");
  if (result[0].contextTime !== 4 / 8000 || result[1].contextTime !== 6 / 8000) throw new Error("Capture center timestamp");
});

Deno.test("locally bundled Pitchy detects a known tone and rejects silence", () => {
  const detector = PitchDetector.forFloat32Array(4096);
  const tone = Float32Array.from({length:4096}, (_, i) => 0.2 * Math.sin(2 * Math.PI * 220 * i / 48000));
  const [hz, clarity] = detector.findPitch(tone, 48000);
  if (Math.abs(1200 * Math.log2(hz / 220)) > 5 || clarity < 0.8) throw new Error("Tone detection");
  const [, silentClarity] = detector.findPitch(new Float32Array(4096), 48000);
  if (silentClarity > 0.1) throw new Error("Silence detection");
});

Deno.test("final aggregation uses the displayed phrase totals", () => {
  const result = aggregate([
    {status:"provisional", total:100, pitch:100, timing:100, scoreable_seconds:1},
    {status:"provisional", total:0, pitch:0, timing:0, scoreable_seconds:3},
  ]);
  if (result.total !== 25 || result.pitch !== 25 || result.timing !== 25) throw new Error("Duration-weighted aggregation");
});

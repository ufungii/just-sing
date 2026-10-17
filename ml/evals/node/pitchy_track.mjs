// Run the REAL Pitchy over a mono float32 file and write one pitch per 20 ms frame.
//
//   node pitchy_track.mjs --in audio.f32 --sr 48000 --window 4096 --clarity 0.8 --gate 0.008 \
//        [--hop 0.02] [--min-hz 65] [--max-hz 1000] [--pitchy /path/to/pitchy.mjs]
//
// Framing matches the live game and the scoring spec: frame i is centered at t = i * hop, its
// window covers t +/- window / (2 * sr) and is zero-padded at the edges. A frame is unvoiced
// (null) when the window RMS is under --gate, clarity is under --clarity, or the pitch is
// outside [min-hz, max-hz]. Pitchy is imported from --pitchy (a file), $PITCHY_PATH, or the
// installed `pitchy` package, so the same script works with a vendored copy or `npm i pitchy`.
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const argv = process.argv.slice(2);
const opt = (name, fallback) => { const i = argv.indexOf(`--${name}`); return i >= 0 ? argv[i + 1] : fallback; };

const sr = Number(opt("sr", 48000)), N = Number(opt("window", 4096)), hop = Number(opt("hop", 0.02));
const clarityMin = Number(opt("clarity", 0.8)), gate = Number(opt("gate", 0.008));
const minHz = Number(opt("min-hz", 65)), maxHz = Number(opt("max-hz", 1000));
const source = opt("pitchy", process.env.PITCHY_PATH ?? "pitchy");
const { PitchDetector } = await import(source.startsWith("/") ? pathToFileURL(source).href : source);

const raw = readFileSync(opt("in"));
const x = new Float32Array(raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength));
const detector = PitchDetector.forFloat32Array(N), window = new Float32Array(N);
const frames = 1 + Math.floor(x.length / sr / hop + 1e-9);
const hz = new Array(frames);

for (let i = 0; i < frames; i++) {
  const start = Math.round(i * hop * sr) - (N >> 1);
  let energy = 0;
  for (let k = 0; k < N; k++) {
    const j = start + k, v = j >= 0 && j < x.length ? x[j] : 0;
    window[k] = v; energy += v * v;
  }
  const rms = Math.sqrt(energy / N);
  const [pitch, clarity] = detector.findPitch(window, sr);
  hz[i] = rms >= gate && clarity >= clarityMin && pitch >= minHz && pitch <= maxHz ? Number(pitch.toFixed(3)) : null;
}
process.stdout.write(JSON.stringify({ hop_seconds: hop, sample_rate: sr, window: N, clarity: clarityMin, gate, hz }));

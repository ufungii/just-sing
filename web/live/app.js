import { PitchDetector } from "./vendor/pitchy.mjs";
import { activeIndices } from "./clock.js";
import { scorePhrase, aggregate } from "./scoring.js";
import { createPlayback } from "./playback.js";
import { lyricDisplay } from "./lyric_display.js";
import { apiUrl } from "./urls.js";

const $ = (id) => document.getElementById(id);
let song = new URLSearchParams(location.search).get("song"), endpoint;
let track, reference, settings, buffer, vocalBuffer, context, source;
let phrases = [];
let playing = false, position = 0, epoch = 0, scheduledAt = 0;
let stream, micSource, capture, silentGain, microphone = false;
let generation = 0, latestCapture = -1, lastScorePaint = -1, previousLine = -2;
let run = { register: 0, latency: 0 };
const observations = new Map(), completed = new Map();
const detector = PitchDetector.forFloat32Array(4096);
let currentMicHz = null;
let seeking = false, disposed = false;

function format(t) {
  return `${Math.floor(Math.max(0, t) / 60)}:${(Math.max(0, t) % 60).toFixed(2).padStart(5, "0")}`;
}
function clock() {
  return playing ? Math.max(position, Math.min(buffer.duration, context.currentTime - epoch)) : position;
}
async function json(url, options) {
  const response = await fetch(apiUrl(url), options);
  if (!response.ok) {
    let error;
    try { error = (await response.json()).error?.message; } catch {}
    throw new Error(error || `Request failed (${response.status})`);
  }
  return response.json();
}
async function audioContext() {
  context ??= new AudioContext();
  await context.resume();
  return context;
}
function controls() {
  $("play").textContent = playing ? "Pause" : "Play";
  $("register").disabled = playing;
  $("latency").disabled = playing;
  $("mic").disabled = playing && !microphone;
}
function pause() {
  if (!playing) return;
  position = clock(); playing = false;
  source.stop(); source = null;
  controls();
}
function clearAttempt() {
  generation++; observations.clear(); completed.clear(); latestCapture = -1;
  lastScorePaint = -1;
  run = { register: Number($("register").value), latency: Number($("latency").value) / 1000 };
  for (const key of ["total", "pitch", "timing"]) $(key).textContent = "—";
  $("badge").textContent = microphone ? "Ready" : "Mic off";
}
function reset() { pause(); position = 0; clearAttempt(); }
async function play() {
  if (playing) { pause(); return; }
  try {
    await audioContext();
    if (!buffer) throw new Error("Audio is not loaded yet.");
    if (position >= buffer.duration) reset();
    if (position === 0) clearAttempt();
    scheduledAt = context.currentTime + 0.06;
    epoch = scheduledAt - position;
    capture?.port.postMessage({ type: "reset" });
    source = createPlayback(context, buffer, vocalBuffer, scheduledAt, position, async () => {
      position = buffer.duration; playing = false;
      source = null; controls();
      if (microphone && observations.size && reference) await finish();
    });
    updateVocalVolume(); playing = true; controls();
  } catch (error) { $("status").textContent = error.message; }
}
function seek(t) {
  const resume = playing;
  pause(); position = Math.max(0, Math.min(buffer.duration, t));
  clearAttempt();
  $("feedback").textContent = "New practice attempt from this position. Missed earlier phrases receive no credit in a full-song total.";
  if (resume) play();
}
async function toggleMicrophone() {
  if (microphone) { stopMicrophone(); return; }
  try {
    if (!navigator.mediaDevices?.getUserMedia) throw new Error("Microphone capture needs localhost or HTTPS.");
    await audioContext();
    stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false } });
    if (disposed) { stream.getTracks().forEach((track) => track.stop()); return; }
    await context.audioWorklet.addModule("./capture-worklet.js");
    micSource = context.createMediaStreamSource(stream);
    capture = new AudioWorkletNode(context, "karaoke-capture");
    silentGain = context.createGain(); silentGain.gain.value = 0;
    micSource.connect(capture).connect(silentGain).connect(context.destination);
    capture.port.onmessage = ({ data }) => {
      const { samples, contextTime } = data;
      let energy = 0, peak = 0;
      for (const value of samples) { energy += value * value; peak = Math.max(peak, Math.abs(value)); }
      const rms = Math.sqrt(energy / samples.length);
      const [hz, clarity] = detector.findPitch(samples, context.sampleRate);
      currentMicHz = rms >= 0.008 && clarity >= 0.8 && hz >= 65 && hz <= 1000 ? hz : null;
      $("micStatus").textContent = peak >= 0.98 ? "Microphone is clipping—reduce input level."
        : `${currentMicHz ? `${currentMicHz.toFixed(1)} Hz` : "No confident singing pitch"} · correction ${run.latency * 1000} ms (manual, uncalibrated)`;
      if (!playing || contextTime < scheduledAt) return;
      const time = contextTime - epoch;
      if (time < 0 || time > buffer.duration) return;
      observations.set(Math.floor(time / 0.02 + 0.5), { time, hz: currentMicHz });
      latestCapture = Math.max(latestCapture, time - run.latency);
    };
    microphone = true; reset();
    $("mic").textContent = "Disable microphone";
    $("micStatus").textContent = "Microphone ready. Use wired headphones; timing correction is not calibrated.";
    const actual = stream.getAudioTracks()[0].getSettings();
    $("micStatus").title = `Browser capture settings: ${JSON.stringify(actual)}`;
    stream.getAudioTracks()[0].addEventListener("ended", () => {
      stopMicrophone(); $("badge").textContent = "Input error";
      $("feedback").textContent = "Microphone disconnected. Reconnect it and reset the attempt; this is not a singing score.";
    });
  } catch (error) { stopMicrophone(); $("micStatus").textContent = `Microphone unavailable: ${error.message}`; }
}
function stopMicrophone() {
  pause();
  capture?.disconnect(); micSource?.disconnect(); silentGain?.disconnect();
  if (capture) capture.port.onmessage = null;
  stream?.getTracks().forEach((t) => t.stop());
  stream = capture = micSource = silentGain = null; microphone = false; currentMicHz = null;
  $("mic").textContent = "Enable microphone"; $("micStatus").textContent = "Microphone off.";
  controls();
}
function grade(line, frames, end = line.end) {
  return scorePhrase(reference, frames, line.start, end, run.register, run.latency, settings.config);
}
function paintScore(t) {
  if (!microphone || !reference || latestCapture < 0 || t - lastScorePaint < 0.1 && t >= lastScorePaint) return;
  lastScorePaint = t;
  const frames = [...observations.values()];
  phrases.forEach((phrase) => {
    if (!completed.has(phrase.id) && latestCapture >= phrase.end + settings.config.timing_window_seconds) {
      const score = grade(phrase, frames); completed.set(phrase.id, score);
      $("badge").textContent = score.rating || "Not scoreable";
      $("feedback").textContent = `Line ${phrase.line_index + 1}: ${score.rating || "unavailable"} · sung coverage ${(100 * score.coverage).toFixed(0)}%. Provisional targets and thresholds.`;
    }
  });
  const scores = [...completed.values()];
  const active = phrases.find((phrase) => phrase.start <= t && t < phrase.end);
  if (active && !completed.has(active.id) && latestCapture > active.start) {
    scores.push(grade(active, frames, Math.min(active.end, latestCapture)));
  }
  showAggregate(aggregate(scores));
}
function showAggregate(score) {
  for (const key of ["total", "pitch", "timing"]) $(key).textContent = score[key] == null ? "—" : score[key].toFixed(1);
}
async function finish() {
  const attempt = generation, frames = [...observations.values()];
  const scores = phrases.map((phrase) => grade(phrase, frames));
  scores.forEach((score, i) => completed.set(phrases[i].id, score));
  const client = aggregate(scores); showAggregate(client);
  try {
    const server = await json(`${endpoint}/score-preview`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scoring_version: settings.version, register: run.register, latency_seconds: run.latency, observations: frames }) });
    if (attempt !== generation) return;
    if (client.total !== null && Math.abs(client.total - server.total) > 1e-6) throw new Error("Browser/backend score mismatch—keep this session for debugging.");
    $("feedback").textContent = "Turn complete. Browser and backend totals agree. Scores are provisional; lyric/note review and device calibration are still required.";
  } catch (error) { $("feedback").textContent = `Local result retained. Backend check unavailable: ${error.message}`; }
}
function draw(t) {
  const canvas = $("lane"), width = canvas.clientWidth, height = 220, ratio = devicePixelRatio || 1;
  if (canvas.width !== Math.round(width * ratio)) { canvas.width = width * ratio; canvas.height = height * ratio; }
  const ctx = canvas.getContext("2d"); ctx.setTransform(ratio, 0, 0, ratio, 0, 0); ctx.clearRect(0, 0, width, height);
  const x = (seconds) => (seconds - t + 5) / 8 * width;
  const y = (hz) => height - ((69 + 12 * Math.log2(hz / 440) - 36) / 60) * height;
  ctx.strokeStyle = "#292f49"; ctx.lineWidth = 1;
  for (let i = 0; i < 7; i++) { ctx.beginPath(); ctx.moveTo(0, i * height / 6); ctx.lineTo(width, i * height / 6); ctx.stroke(); }
  ctx.strokeStyle = "#818baa"; ctx.beginPath(); ctx.moveTo(x(t), 0); ctx.lineTo(x(t), height); ctx.stroke();
  if (reference) {
    ctx.strokeStyle = "#a8e6ff"; ctx.lineWidth = 4;
    const first = Math.max(0, Math.floor((t - 5) / reference.hop_seconds)), last = Math.min(reference.hz.length, Math.ceil((t + 3) / reference.hop_seconds));
    let connected = false; ctx.beginPath();
    for (let i = first; i < last; i++) {
      const hz = reference.hz[i];
      if (!hz || reference.excluded.some((r) => r.start <= i * reference.hop_seconds && i * reference.hop_seconds < r.end)) { connected = false; continue; }
      const px = x(i * reference.hop_seconds), py = y(hz * 2 ** (run.register / 12));
      if (connected) ctx.lineTo(px, py); else ctx.moveTo(px, py); connected = true;
    }
    ctx.stroke();
  }
  ctx.strokeStyle = "#ffbe77"; ctx.lineWidth = 2; ctx.beginPath();
  let connected = false;
  for (const frame of observations.values()) {
    const time = frame.time - run.latency;
    if (time < t - 5 || time > t + 3) continue;
    if (!frame.hz) { connected = false; continue; }
    if (connected) ctx.lineTo(x(time), y(frame.hz)); else ctx.moveTo(x(time), y(frame.hz)); connected = true;
  }
  ctx.stroke();
}
function render() {
  if (track && buffer) {
    const t = clock(), { lineIndex, wordIndex } = activeIndices(track.lines, t);
    $("clock").textContent = format(t); if (!seeking) $("seek").value = t;
    if (lineIndex !== previousLine) {
      previousLine = lineIndex; $("line").replaceChildren();
      if (lineIndex === null) $("line").textContent = "♫⋆｡♪ ₊˚♬ﾟ.";
      else {
        const display = lyricDisplay(track.lines[lineIndex], $("romanized").checked);
        if (!display.words.length) $("line").textContent = display.text;
        else display.words.forEach((word, i) => {
          if (i) $("line").append(" ");
          const span = document.createElement("span"); span.textContent = word.text; span.className = "word"; span.dataset.word = i; $("line").append(span);
        });
      }
      document.querySelectorAll("#sheet li").forEach((li, i) => li.classList.toggle("current", i === lineIndex));
    }
    $("line").querySelectorAll(".word").forEach((span) => {
      const i = Number(span.dataset.word); span.classList.toggle("active", i === wordIndex);
      span.classList.toggle("done", track.lines[lineIndex].words[i].end <= t);
    });
    const next = track.lines.find((line) => line.start > t);
    $("next").textContent = next ? `Next · ${lyricDisplay(next, $("romanized").checked).text}` : "";
    paintScore(t); draw(t);
  }
  requestAnimationFrame(render);
}
async function load() {
  try {
    const health = await json("/api/health");
    if (!health.local_demo_audio_enabled) {
      $("title").textContent = "Karaoke unavailable";
      throw new Error("Song playback is not enabled on this server.");
    }
    const catalog = await json("/api/songs");
    if (!catalog.songs.length) {
      $("title").textContent = "No songs available";
      throw new Error("No prepared songs are available on this server yet.");
    }
    song ||= catalog.songs.find((item) => item.id.endsWith("-demo"))?.id || catalog.songs[0]?.id;
    endpoint = apiUrl(`/api/songs/${encodeURIComponent(song)}`);
    catalog.songs.forEach((item) => {
      const option = document.createElement("option"); option.value = item.id;
      option.textContent = `${item.artist} · ${item.title}`; $("song").append(option);
    });
    $("song").value = song;
    const [lyrics, config] = await Promise.all([json(`${endpoint}/lyrics/preview`), json("/api/scoring-config")]);
    const metadata = catalog.songs.find((s) => s.id === song);
    if (!metadata) throw new Error("Song is not prepared.");
    if (!lyrics.lines?.length) throw new Error("Lyric alignment is not prepared yet.");
    track = lyrics; settings = config;
    phrases = track.phrases ?? track.lines.map((line, i) => ({ id: `p${i+1}`, line_index: i, start: line.start, end: line.end }));
    $("title").textContent = `${metadata.artist} · ${metadata.title}`;
    reference = await json(`${endpoint}/reference`).catch(() => null);
    context ??= new AudioContext(); // Decode while suspended; Play resumes on a user gesture.
    const response = await fetch(`${endpoint}/audio/instrumental`);
    if (!response.ok) throw new Error("Instrumental unavailable. Start the local backend with demo audio enabled.");
    buffer = await context.decodeAudioData(await response.arrayBuffer());
    try {
      const vocals = await fetch(`${endpoint}/audio/vocals`);
      if (!vocals.ok) throw new Error("Vocal guide unavailable");
      vocalBuffer = await context.decodeAudioData(await vocals.arrayBuffer());
      if (Math.abs(vocalBuffer.duration - buffer.duration) > 1 / context.sampleRate)
        throw new Error("Vocal guide duration differs from instrumental");
      $("vocals").disabled = false;
      $("vocalVolume").disabled = false;
    } catch (error) {
      vocalBuffer = null; $("vocals").checked = false;
      $("vocalStatus").textContent = error.message;
    }
    $("duration").textContent = format(buffer.duration); $("seek").max = buffer.duration;
    refreshLyrics();
    $("status").textContent = `${track.lines.length} timed lines · ${track.lines.reduce((n,l) => n + l.words.length, 0)} timed words · ${track.status === "ready" ? "reviewed lyrics" : "automatic alignment draft"}${reference ? " · reference pitch loaded" : " · reference pitch unavailable; scoring disabled"}`;
    $("play").disabled = false;
  } catch (error) { $("status").textContent = error.message; }
}
function refreshLyrics() {
  previousLine = -2;
  $("sheet").replaceChildren();
  if (!track) return;
  track.lines.forEach((line, index) => {
    const li = document.createElement("li"), time = document.createElement("time");
    if (index && track.section_starts?.includes(index)) li.classList.add("section-start");
    time.textContent = `${format(line.start)}–${format(line.end)}`;
    li.append(time, document.createTextNode(lyricDisplay(line, $("romanized").checked).text));
    li.onclick = () => { if (buffer) seek(line.start); }; $("sheet").append(li);
  });
}
$("play").onclick = play; $("reset").onclick = reset; $("mic").onclick = toggleMicrophone;
function updateVocalVolume() {
  const volume = Number($("vocalVolume").value);
  $("vocalVolumeValue").textContent = `${volume}%`;
  source?.setVocals($("vocals").checked, volume / 100);
}
$("vocals").onchange = updateVocalVolume;
$("vocalVolume").oninput = updateVocalVolume;
$("romanized").onchange = refreshLyrics;
$("song").onchange = () => {
  pause(); stopMicrophone();
  const url = new URL(location.href); url.searchParams.set("song", $("song").value); location.assign(url);
};
$("seek").oninput = () => { seeking = true; };
$("seek").onchange = (event) => { seeking = false; if (buffer) seek(Number(event.target.value)); };
$("register").onchange = reset; $("latency").onchange = reset;
window.addEventListener("pagehide", () => { disposed = true; stopMicrophone(); context?.close(); });
requestAnimationFrame(render); load();

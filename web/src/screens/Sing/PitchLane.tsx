/**
 * The pitch highway: target notes scroll right-to-left toward the "now" line, the singer's live pitch
 * is a glowing pink trace ending in a pixel heart, and excluded regions are hatched out. Vertical axis
 * is log-frequency (semitones); targets are already shifted by the chosen register for the whole turn.
 *
 * Drawn on a canvas in its own requestAnimationFrame loop that reads the master clock through
 * `getTime`, so React never re-renders per frame for it.
 */
import { useEffect, useMemo, useRef } from 'react';
import type { Note, PhraseScore, Song } from '../../lib/types';
import { centsBetween, SCORING_CONFIG, type TargetTrack } from '../../scoring';

/** A display note; `slot` (duet only) is the owning player, 0 = P1, 1 = P2. */
export type LaneNote = Note & { slot?: number };

interface Props {
  song: Song;
  /** Display notes in Hz, already register-shifted. */
  notes: LaneNote[];
  /** Duet ownership timeline (sorted by start); tints notes and colours the now line and trace head. */
  sections?: { start: number; slot: number }[];
  target: TargetTrack;
  /** Clip time in seconds on the master clock. */
  getTime: () => number;
  /** Live user pitch per clip frame (null = unvoiced). */
  userHz: (number | null)[];
  /** Phrase results so far, to badge rated phrases. */
  ratings: Map<string, PhraseScore>;
}

const AHEAD = 4; // seconds of upcoming notes visible right of the now line
const NOW_AT = 0.24; // now line position as a fraction of width
const HEIGHT = 380;

// Palette from styles/tokens.css (canvas cannot read CSS variables directly).
const C = {
  ink: '#3b2340',
  paper: '#fff6fb',
  row: '#ffeef7',
  rowLine: '#f6cfe3',
  octLine: '#e7a9c9',
  hot: '#ff4f9a',
  hotLight: '#ff9cc8',
  pink: '#ff8cc0',
  sky: '#8fd3ff',
  skyLight: '#d4eeff',
  skyDark: '#4fa3da',
  pinkLight: '#ffc8e1',
  lav: '#c9b6ff',
  lavLight: '#ece4ff',
  butter: '#ffd84d',
  mint: '#7eefcf',
  white: '#ffffff',
};

/** Per-player colours (P1 pink / P2 sky, as in the player pickers). `trace` is the line, `glow` its halo, `head` the heart. */
const SLOT_COLORS = [
  { note: C.pink, noteBevel: C.pinkLight, line: C.hot, glow: C.hotLight, head: C.pink, headOn: C.hot },
  { note: C.sky, noteBevel: C.skyLight, line: C.skyDark, glow: C.sky, head: C.sky, headOn: C.skyDark },
];

const RATING_COLOR: Record<string, string> = { perfect: C.butter, great: C.mint, okay: C.sky, bad: C.lav, miss: C.lavLight };

const HEART = ['.##.##.', '#######', '#######', '.#####.', '..###..', '...#...'];

const midiOf = (hz: number) => 69 + 12 * Math.log2(hz / 440);

/** Note bar height for a lane with `rows` semitone rows: 30% taller than the original sizing. */
const pillFor = (rows: number) => Math.min(34, 1.3 * Math.max(14, Math.min(26, 0.9 * (HEIGHT / rows))));

/**
 * Semitone range that fits every target with some headroom. If the taller note bars would touch
 * their neighbouring semitone rows, the window is trimmed (never below the notes plus one row each side).
 */
function laneRange(notes: Note[], target: TargetTrack): [number, number] {
  const hz = [...notes.map((n) => n.hz), ...(target.source === 'hz' ? (target.hz.filter((h) => h !== null) as number[]) : [])];
  if (!hz.length) return [52, 72];
  const min = Math.floor(Math.min(...hz.map(midiOf)));
  const max = Math.ceil(Math.max(...hz.map(midiOf)));
  let lo = min - 4;
  let hi = max + 4;
  const missing = 16 - (hi - lo);
  if (missing > 0) {
    lo -= Math.floor(missing / 2);
    hi += Math.ceil(missing / 2);
  }
  const rows = Math.max(Math.floor(HEIGHT / pillFor(hi - lo)), max - min + 2);
  const extra = hi - lo - rows;
  if (extra > 0) {
    // trim equally from both sides but never cut into the notes
    const trimLo = Math.min(Math.floor(extra / 2), min - 1 - lo);
    lo += Math.max(0, trimLo);
    hi -= Math.max(0, Math.min(extra - Math.max(0, trimLo), hi - (max + 1)));
  }
  return [lo, hi];
}

/** A pill with stepped (pixel) corners. */
function pixelPill(g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, step: number) {
  const s = Math.min(step, w / 3, h / 3);
  g.beginPath();
  g.moveTo(x + 2 * s, y);
  g.lineTo(x + w - 2 * s, y);
  g.lineTo(x + w - 2 * s, y + s);
  g.lineTo(x + w - s, y + s);
  g.lineTo(x + w - s, y + 2 * s);
  g.lineTo(x + w, y + 2 * s);
  g.lineTo(x + w, y + h - 2 * s);
  g.lineTo(x + w - s, y + h - 2 * s);
  g.lineTo(x + w - s, y + h - s);
  g.lineTo(x + w - 2 * s, y + h - s);
  g.lineTo(x + w - 2 * s, y + h);
  g.lineTo(x + 2 * s, y + h);
  g.lineTo(x + 2 * s, y + h - s);
  g.lineTo(x + s, y + h - s);
  g.lineTo(x + s, y + h - 2 * s);
  g.lineTo(x, y + h - 2 * s);
  g.lineTo(x, y + 2 * s);
  g.lineTo(x + s, y + 2 * s);
  g.lineTo(x + s, y + s);
  g.lineTo(x + 2 * s, y + s);
  g.closePath();
}

function drawHeart(g: CanvasRenderingContext2D, cx: number, cy: number, px: number, color: string) {
  const x0 = Math.round(cx - 3.5 * px);
  const y0 = Math.round(cy - 3 * px);
  // ink outline: the same sprite offset by one pixel in each direction
  g.fillStyle = C.ink;
  for (const [dx, dy] of [[-1, 0], [1, 0], [0, -1], [0, 1]])
    HEART.forEach((row, r) => [...row].forEach((ch, c) => ch === '#' && g.fillRect(x0 + (c + dx) * px, y0 + (r + dy) * px, px, px)));
  g.fillStyle = color;
  HEART.forEach((row, r) => [...row].forEach((ch, c) => ch === '#' && g.fillRect(x0 + c * px, y0 + r * px, px, px)));
  g.fillStyle = C.white;
  g.fillRect(x0 + px, y0 + px, px, px); // shine
}

function drawSparkle(g: CanvasRenderingContext2D, x: number, y: number, px: number) {
  g.fillStyle = C.butter;
  g.fillRect(x - px / 2, y - 2.5 * px, px, 5 * px);
  g.fillRect(x - 2.5 * px, y - px / 2, 5 * px, px);
}

export function PitchLane({ song, notes, sections, target, getTime, userHz, ratings }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  // Latest props for the draw loop without restarting it.
  const range = useMemo(() => laneRange(notes, target), [notes, target]);
  const live = useRef({ song, notes, sections, target, getTime, userHz, ratings, range });
  useEffect(() => {
    live.current = { song, notes, sections, target, getTime, userHz, ratings, range };
  });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const g = canvas.getContext('2d');
    if (!g) return;
    let frame = 0;
    let width = 0;

    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      width = canvas.clientWidth;
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(HEIGHT * dpr);
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.imageSmoothingEnabled = false;
    };
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);
    resize();

    const draw = () => {
      frame = requestAnimationFrame(draw);
      const { song, notes, sections, target, getTime, userHz, ratings, range } = live.current;
      const t = getTime();
      const W = width;
      const H = HEIGHT;
      const nowX = Math.round(W * NOW_AT);
      const pps = (W - nowX) / AHEAD;
      const xOf = (time: number) => nowX + (time - t) * pps;
      const [lo, hi] = range;
      const rowH = H / (hi - lo);
      const yOf = (midi: number) => H - (midi - lo) * rowH;
      const hop = target.hop;
      // duet: the singer who owns the current section colours the now line and the trace
      let activeSlot = 0;
      for (const sec of sections ?? []) if (sec.start <= t) activeSlot = sec.slot;
      const sc = SLOT_COLORS[activeSlot] ?? SLOT_COLORS[0];

      // ground: semitone rows, a stronger line at every C with its name
      g.fillStyle = C.paper;
      g.fillRect(0, 0, W, H);
      for (let m = lo; m < hi; m++) {
        const y = Math.round(yOf(m + 1));
        if ([1, 3, 6, 8, 10].includes(((m % 12) + 12) % 12)) {
          g.fillStyle = C.row;
          g.fillRect(0, y, W, Math.ceil(rowH));
        }
        g.fillStyle = m % 12 === 0 ? C.octLine : C.rowLine;
        g.fillRect(0, Math.round(yOf(m)), W, m % 12 === 0 ? 2 : 1);
        if (m % 12 === 0) {
          g.fillStyle = C.octLine;
          g.font = '700 11px Silkscreen, monospace';
          g.fillText(`C${m / 12 - 1}`, 6, Math.round(yOf(m)) - 4);
        }
      }

      // excluded regions: hatched, never scored
      for (const ex of song.reference.excluded) {
        const x1 = Math.max(0, xOf(ex.start));
        const x2 = Math.min(W, xOf(ex.end));
        if (x2 <= 0 || x1 >= W) continue;
        g.fillStyle = C.lavLight;
        g.fillRect(x1, 0, x2 - x1, H);
        g.save();
        g.beginPath();
        g.rect(x1, 0, x2 - x1, H);
        g.clip();
        g.fillStyle = C.lav;
        for (let d = -H; d < x2 - x1 + H; d += 16) {
          g.beginPath();
          g.moveTo(x1 + d, H);
          g.lineTo(x1 + d + 6, H);
          g.lineTo(x1 + d + 6 + H, 0);
          g.lineTo(x1 + d + H, 0);
          g.fill();
        }
        g.restore();
        g.fillStyle = C.ink;
        g.font = '700 12px Silkscreen, monospace';
        g.fillText('SKIP', x1 + 8, 18);
      }

      // rating badges above each rated phrase
      for (const p of song.phrases) {
        const r = ratings.get(p.id);
        if (!r) continue;
        const x = xOf(p.end);
        if (x < -80 || x > W) continue;
        g.font = '700 12px Silkscreen, monospace';
        const label = r.rating.toUpperCase();
        const w = g.measureText(label).width + 12;
        g.fillStyle = C.ink;
        g.fillRect(x - w + 2, 8, w, 20);
        g.fillStyle = RATING_COLOR[r.rating];
        g.fillRect(x - w, 6, w, 20);
        g.fillStyle = C.ink;
        g.fillText(label, x - w + 6, 21);
      }

      // target notes: pixel pills with dot eyes
      const pillH = Math.min(pillFor(hi - lo), rowH * 0.95);
      for (const n of notes) {
        const x1 = xOf(n.start);
        const x2 = xOf(n.end);
        if (x2 < 0 || x1 > W) continue;
        const y = Math.round(yOf(midiOf(n.hz)) - pillH / 2);
        const w = Math.max(10, x2 - x1);
        const active = t >= n.start && t < n.end;
        const past = t >= n.end;
        const own = n.slot === undefined ? undefined : SLOT_COLORS[n.slot];
        const face = active ? C.butter : past ? C.lav : own ? own.note : C.sky;
        const bevel = active ? C.white : past ? C.lavLight : own ? own.noteBevel : C.skyLight;
        g.fillStyle = C.ink;
        pixelPill(g, x1 + 3, y + 4, w, pillH, 3);
        g.fill(); // hard shadow
        pixelPill(g, x1, y, w, pillH, 3);
        g.fill();
        g.fillStyle = face;
        pixelPill(g, x1 + 3, y + 3, w - 6, pillH - 6, 2);
        g.fill();
        g.fillStyle = bevel;
        g.fillRect(x1 + 7, y + 5, Math.max(0, w - 18), 3);
        if (w > 28) {
          const ey = y + pillH / 2 - 1;
          g.fillStyle = C.ink;
          g.fillRect(x1 + 9, ey, 3, 4);
          g.fillRect(x1 + 17, ey, 3, 4);
          g.fillStyle = C.pink;
          g.fillRect(x1 + 6, ey + 5, 3, 2);
          g.fillRect(x1 + 20, ey + 5, 3, 2);
        }
      }

      // now line
      g.fillStyle = C.ink;
      g.fillRect(nowX - 3, 0, 6, H);
      g.fillStyle = sc.line;
      g.fillRect(nowX - 1, 0, 2, H);
      g.fillStyle = C.ink;
      g.beginPath();
      g.moveTo(nowX - 9, 0);
      g.lineTo(nowX + 9, 0);
      g.lineTo(nowX, 10);
      g.fill();
      g.beginPath();
      g.moveTo(nowX - 9, H);
      g.lineTo(nowX + 9, H);
      g.lineTo(nowX, H - 10);
      g.fill();

      // live trace: the last ~1.2 s of user frames, glowing pink, broken at unvoiced frames
      const kEnd = Math.min(userHz.length, Math.floor(t / hop) + 1);
      const kStart = Math.max(0, Math.floor((t - (nowX / pps)) / hop));
      const clampY = (hz: number) => Math.max(4, Math.min(H - 4, yOf(midiOf(hz))));
      // Collect voiced runs and ease them for drawing only: a 5-point moving average on y, then a curve
      // through the midpoints. The scored/tracked pitch is untouched.
      const runs: { x: number; y: number; k: number }[][] = [];
      let run: { x: number; y: number; k: number }[] | null = null;
      for (let k = kStart; k < kEnd; k++) {
        const h = userHz[k];
        if (h === null || h === undefined) {
          run = null;
          continue;
        }
        if (!run) runs.push((run = []));
        run.push({ x: xOf(k * hop), y: clampY(h), k });
      }
      for (const r of runs) {
        const ys = r.map((p) => p.y);
        r.forEach((p, i) => {
          const from = Math.max(0, i - 2);
          const to = Math.min(r.length - 1, i + 2);
          let sum = 0;
          for (let j = from; j <= to; j++) sum += ys[j];
          p.y = sum / (to - from + 1);
        });
      }
      const strokeTrace = () => {
        g.beginPath();
        for (const r of runs) {
          if (!r.length) continue;
          g.moveTo(r[0].x, r[0].y);
          for (let i = 1; i < r.length - 1; i++) g.quadraticCurveTo(r[i].x, r[i].y, (r[i].x + r[i + 1].x) / 2, (r[i].y + r[i + 1].y) / 2);
          if (r.length > 1) g.lineTo(r[r.length - 1].x, r[r.length - 1].y);
        }
        g.stroke();
      };
      g.lineJoin = 'round';
      g.lineCap = 'round';
      g.save();
      g.shadowColor = sc.line;
      g.shadowBlur = 16;
      g.strokeStyle = sc.glow;
      g.lineWidth = 12;
      strokeTrace();
      g.restore();
      g.strokeStyle = sc.line;
      g.lineWidth = 5.5;
      strokeTrace();
      g.strokeStyle = C.white;
      g.lineWidth = 2;
      strokeTrace();

      // trace head: a heart at the newest voiced frame; sparkles when it is on pitch
      const last = runs.length ? runs[runs.length - 1] : null;
      const headPt = last && last[last.length - 1].k >= kEnd - 8 ? last[last.length - 1] : null;
      if (headPt) {
        const { x, y, k: head } = headPt;
        const hz = userHz[head] as number;
        const want = target.hz[head];
        const onPitch = want !== null && want !== undefined && !target.excluded[head] && Math.abs(centsBetween(hz, want)) <= SCORING_CONFIG.pitchFullCents;
        if (onPitch) {
          const phase = Math.floor(performance.now() / 120) % 2;
          drawSparkle(g, x - 22 - phase * 3, y - 20, 2);
          drawSparkle(g, x + 20 + phase * 2, y - 16 + phase * 3, 2);
          drawSparkle(g, x + 4, y + 26 - phase * 2, 2);
        }
        drawHeart(g, x, y, 4, onPitch ? sc.headOn : sc.head);
      }

      // lane border
      g.strokeStyle = C.ink;
      g.lineWidth = 4;
      g.strokeRect(2, 2, W - 4, H - 4);
    };
    frame = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(frame);
      ro.disconnect();
    };
  }, []);

  return <canvas ref={canvasRef} className="sing-lane" style={{ height: HEIGHT }} aria-label="Pitch lane: target notes and your live pitch" role="img" />;
}

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

interface Props {
  song: Song;
  /** Display notes in Hz, already register-shifted. */
  notes: Note[];
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
  lav: '#c9b6ff',
  lavLight: '#ece4ff',
  butter: '#ffd84d',
  mint: '#7eefcf',
  white: '#ffffff',
};

const RATING_COLOR: Record<string, string> = { perfect: C.butter, great: C.mint, okay: C.sky, bad: C.lav, miss: C.lavLight };

const HEART = ['.##.##.', '#######', '#######', '.#####.', '..###..', '...#...'];

const midiOf = (hz: number) => 69 + 12 * Math.log2(hz / 440);

/** Semitone range that fits every target with some headroom (at least 16 semitones tall). */
function laneRange(notes: Note[], target: TargetTrack): [number, number] {
  const hz = [...notes.map((n) => n.hz), ...(target.source === 'hz' ? (target.hz.filter((h) => h !== null) as number[]) : [])];
  if (!hz.length) return [52, 72];
  let lo = Math.floor(Math.min(...hz.map(midiOf))) - 4;
  let hi = Math.ceil(Math.max(...hz.map(midiOf))) + 4;
  const missing = 16 - (hi - lo);
  if (missing > 0) {
    lo -= Math.floor(missing / 2);
    hi += Math.ceil(missing / 2);
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

export function PitchLane({ song, notes, target, getTime, userHz, ratings }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  // Latest props for the draw loop without restarting it.
  const range = useMemo(() => laneRange(notes, target), [notes, target]);
  const live = useRef({ song, notes, target, getTime, userHz, ratings, range });
  useEffect(() => {
    live.current = { song, notes, target, getTime, userHz, ratings, range };
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
      const { song, notes, target, getTime, userHz, ratings, range } = live.current;
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
      const pillH = Math.max(14, Math.min(26, rowH * 0.9));
      for (const n of notes) {
        const x1 = xOf(n.start);
        const x2 = xOf(n.end);
        if (x2 < 0 || x1 > W) continue;
        const y = Math.round(yOf(midiOf(n.hz)) - pillH / 2);
        const w = Math.max(10, x2 - x1);
        const active = t >= n.start && t < n.end;
        const past = t >= n.end;
        const face = active ? C.butter : past ? C.lav : C.sky;
        const bevel = active ? C.white : past ? C.lavLight : C.skyLight;
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
      g.fillStyle = C.hot;
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
      const strokeTrace = () => {
        g.beginPath();
        let open = false;
        for (let k = kStart; k < kEnd; k++) {
          const h = userHz[k];
          if (h === null || h === undefined) {
            open = false;
            continue;
          }
          const x = xOf(k * hop);
          const y = clampY(h);
          if (open) g.lineTo(x, y);
          else g.moveTo(x, y);
          open = true;
        }
        g.stroke();
      };
      g.lineJoin = 'round';
      g.lineCap = 'round';
      g.save();
      g.shadowColor = C.hot;
      g.shadowBlur = 14;
      g.strokeStyle = C.hotLight;
      g.lineWidth = 9;
      strokeTrace();
      g.restore();
      g.strokeStyle = C.hot;
      g.lineWidth = 4;
      strokeTrace();
      g.strokeStyle = C.white;
      g.lineWidth = 1.5;
      strokeTrace();

      // trace head: a heart at the newest voiced frame; sparkles when it is on pitch
      let head = -1;
      for (let k = kEnd - 1; k >= Math.max(kStart, kEnd - 8); k--)
        if (userHz[k] !== null && userHz[k] !== undefined) {
          head = k;
          break;
        }
      if (head >= 0) {
        const hz = userHz[head] as number;
        const x = xOf(head * hop);
        const y = clampY(hz);
        const want = target.hz[head];
        const onPitch = want !== null && want !== undefined && !target.excluded[head] && Math.abs(centsBetween(hz, want)) <= SCORING_CONFIG.pitchFullCents;
        if (onPitch) {
          const phase = Math.floor(performance.now() / 120) % 2;
          drawSparkle(g, x - 18 - phase * 3, y - 16, 2);
          drawSparkle(g, x + 16 + phase * 2, y - 12 + phase * 3, 2);
          drawSparkle(g, x + 4, y + 20 - phase * 2, 2);
        }
        drawHeart(g, x, y, 3, onPitch ? C.hot : C.pink);
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

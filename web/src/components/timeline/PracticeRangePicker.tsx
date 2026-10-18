import { useEffect, useRef, useState } from 'react';
import { loadBacking, loadVocals } from '../../audio/sources';
import { getManifest } from '../../lib/api';
import type { Song, TimeRange } from '../../lib/types';
import { Notice, PixelButton } from '../../ui';
import { ClipRangeBar } from './ClipRangeBar';
import { CropWorkspace } from './CropWorkspace';
import { normalizeRange } from './range';

type RangeChange = (range: TimeRange | null) => void | Promise<boolean>;

export function PracticeRangePicker(props: { clipId: string; range: TimeRange | null; onChange?: RangeChange; disabled?: boolean }) {
  return <Picker key={props.clipId} {...props} />;
}

function Picker({ clipId, range: savedRange, onChange, disabled }: { clipId: string; range: TimeRange | null; onChange?: RangeChange; disabled?: boolean }) {
  const [range, setRange] = useState(savedRange);
  useEffect(() => { setRange(savedRange); }, [savedRange?.start, savedRange?.end]);
  const [song, setSong] = useState<Song | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [playhead, setPlayhead] = useState<number | null>(null);
  const [workspace, setWorkspace] = useState(false);
  const preview = useRef<{ ctx: AudioContext; raf: number } | null>(null);
  function stop() {
    const p = preview.current;
    preview.current = null;
    if (p) { cancelAnimationFrame(p.raf); void p.ctx.close(); }
    setPlaying(false);
    setPlayhead(null);
  }
  useEffect(() => {
    let live = true;
    setError(null);
    getManifest(clipId).then((s) => live && setSong(s), () => live && setError('Could not load the timeline.'));
    return () => { live = false; };
  }, [clipId, retry]);
  useEffect(() => { stop(); return stop; }, [range?.start, range?.end]);

  async function play(from?: number, previewRange: TimeRange | null = range) {
    stop();
    if (!song) return;
    const ctx = new AudioContext();
    const p = { ctx, raf: 0 };
    preview.current = p;
    setPlaying(true);
    setError(null);
    try {
      await ctx.resume();
      const [backing, vocals] = await Promise.all([
        loadBacking(ctx, clipId, song.duration), loadVocals(ctx, clipId),
      ]);
      if (preview.current !== p) return;
      const start = Math.max(previewRange?.start ?? 0, from ?? previewRange?.start ?? 0);
      const end = previewRange?.end ?? song.duration;
      if (start >= end) return stop();
      const t0 = ctx.currentTime;
      for (const [index, buffer] of [backing.buffer, ...(vocals ? [vocals] : [])].entries()) {
        const src = ctx.createBufferSource();
        src.buffer = buffer;
        src.connect(ctx.destination);
        src.start(t0, start, end - start);
        if (index === 0) src.onended = () => { if (preview.current === p) stop(); };
      }
      const tick = () => { setPlayhead(start + ctx.currentTime - t0); p.raf = requestAnimationFrame(tick); };
      tick();
    } catch {
      if (preview.current === p) { stop(); setError('Preview could not play. Please try again.'); }
    }
  }
  if (!song) return <Notice action={<PixelButton size="sm" onClick={() => setRetry((n) => n + 1)}>RETRY TIMELINE</PixelButton>}>{error ?? 'Loading timeline…'}</Notice>;
  async function commit(next: TimeRange | null) {
    const normalized = normalizeRange(song!.phrases, next);
    setRange(normalized);
    try {
      if (await onChange?.(normalized) === false) { setRange(savedRange); return false; }
      return true;
    } catch {
      setRange(savedRange);
      setError('Could not save the section. The previous selection is restored.');
      return false;
    }
  }
  return (
    <section className="range-picker" aria-label="Practice section">
      <p className="range-picker__title">
        {range ? 'SINGING A SECTION' : 'SINGING THE WHOLE SONG'}
        {onChange && <span> · drag the yellow handles, or slide the pink part, to choose what you sing</span>}
      </p>
      <ClipRangeBar duration={song.duration} phrases={song.phrases} lines={song.lines} range={range}
        onChange={onChange ? setRange : undefined} onCommit={(r) => void commit(r)} disabled={disabled} playhead={playhead} />
      <div className="range-picker__actions">
        <PixelButton size="sm" tone="sky" onClick={() => playing ? stop() : void play()}>{playing ? 'STOP PREVIEW' : 'PLAY SECTION ▶'}</PixelButton>
        {onChange && <PixelButton size="sm" tone="paper" disabled={disabled || !range} onClick={() => commit(null)}>WHOLE SONG</PixelButton>}
        <PixelButton size="sm" tone="paper" className="range-picker__editor" onClick={() => { stop(); setWorkspace(true); }}>ADVANCED EDITOR</PixelButton>
      </div>
      {range && <p className="solo-hint">Only whole phrases inside this section count.</p>}
      {error && <Notice tone="error">{error}</Notice>}
      {workspace && <CropWorkspace song={song} range={range} readOnly={!onChange || disabled}
        onClose={() => { stop(); setWorkspace(false); }} onApply={onChange && !disabled ? commit : undefined}
        onPreview={(selected,from) => void play(from,selected)} onStop={stop} playing={playing} playhead={playhead}
        waveformUrls={[`/api/clips/${clipId}/vocals`,`/api/clips/${clipId}/audio`]}/>}
    </section>
  );
}

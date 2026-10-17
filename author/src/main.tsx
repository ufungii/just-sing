import { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ClipTimeline } from '../../web/src/components/timeline/ClipTimeline';
import type { Song, Line, DuetSection } from '../../web/src/lib/types';
import './style.css';
import { AddSong } from './AddSong';
import { CropWorkspace, TimelineWaveform } from '../../web/src/components/timeline/CropWorkspace';
import type { TimeRange } from '../../web/src/lib/types';

type Loaded = { song: Song; revision: string; review: { reviewed?: boolean; author_pending_rebuild?: boolean } };
async function api(path: string, body?: unknown) {
  const response = await fetch('/api/songs' + path, body ? {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  } : undefined);
  const result = await response.json();
  if (!response.ok) throw Error(result.error || 'Request failed');
  return result;
}

function App() {
  const [catalog, setCatalog] = useState<{id: string; title: string; artist: string}[]>([]);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [song, setSong] = useState<Song | null>(null);
  const [past, setPast] = useState<Song[]>([]), [future, setFuture] = useState<Song[]>([]);
  const [selected, setSelected] = useState<number[]>([0]);
  const [error, setError] = useState(''), [status, setStatus] = useState('Choose a prepared song.');
  const [busy, setBusy] = useState(false), [dirty, setDirty] = useState(false);
  const [time, setTime] = useState(0), [playing, setPlaying] = useState(false);
  const [mode, setMode] = useState('vocals'), [snap, setSnap] = useState(true), [tap, setTap] = useState(false);
  const [peaks, setPeaks] = useState<number[]>([]);
  const [workspace,setWorkspace]=useState(false);
  const playback = useRef<{ctx: AudioContext; start: number; offset: number; end:number; raf: number} | null>(null);
  const buffers = useRef<{vocals: AudioBuffer; instrumental: AudioBuffer} | null>(null);
  const generation = useRef(0);
  const tapIndex = useRef(0);
  const songRef = useRef(song); songRef.current = song;
  const dirtyRef = useRef(dirty); dirtyRef.current = dirty;

  useEffect(() => { api('').then(setCatalog).catch((e) => setError(e.message)); }, []);
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => { if (dirtyRef.current) { e.preventDefault(); e.returnValue = ''; } };
    window.addEventListener('beforeunload', warn);
    return () => { window.removeEventListener('beforeunload', warn); stop(); };
  }, []);
  function clock() { const p = playback.current; return p ? p.offset + p.ctx.currentTime - p.start : time; }
  function stop() {
    const p = playback.current; playback.current = null;
    if (p) { setTime(Math.min(songRef.current?.duration ?? 0, p.offset + p.ctx.currentTime - p.start)); cancelAnimationFrame(p.raf); void p.ctx.close(); }
    setPlaying(false);
  }
  async function load(id: string) {
    if (dirty && !confirm('Discard unsaved edits and load another song?')) return;
    const token = ++generation.current; stop(); setBusy(true); setError(''); buffers.current = null; setPeaks([]);
    try {
      const result: Loaded = await api('/' + id);
      if (token !== generation.current) return;
      setLoaded(result); setSong(result.song); setPast([]); setFuture([]); setSelected([0]); setTime(0); setDirty(false); setTap(false);
      const ctx = new AudioContext();
      try {
        const audio = await Promise.all(['vocals', 'instrumental'].map(async (role) => {
          const r = await fetch(`/api/songs/${id}/audio/${role}`); if (!r.ok) throw Error(`${role} unavailable`);
          return ctx.decodeAudioData(await r.arrayBuffer());
        }));
        if (token !== generation.current) return;
        if (Math.abs(audio[0].duration - audio[1].duration) > 0.03) throw Error('Stem durations differ');
        buffers.current = { vocals: audio[0], instrumental: audio[1] };
        const data = audio[0].getChannelData(0), bins = 1800, step = Math.max(1, Math.ceil(data.length / bins));
        const points: number[] = [];
        for (let i = 0; i < data.length; i += step) {
          let maximum = 0; for (let j = i; j < Math.min(i + step, data.length); j++) maximum = Math.max(maximum, Math.abs(data[j]));
          points.push(maximum);
        }
        setPeaks(points); setStatus('Loaded. Edits stay in memory until Save.');
      } finally { await ctx.close(); }
    } catch (e) { setError(String(e)); } finally { if (token === generation.current) setBusy(false); }
  }
  function edit(next: Song) {
    if (!songRef.current) return;
    const previous = songRef.current;
    setPast((items) => [...items.slice(-99), previous]); setFuture([]); setSong(next); songRef.current = next; setDirty(true);
  }
  function history(redo: boolean) {
    const stack = redo ? future : past, target = stack.at(-1); if (!target || !song) return;
    if (redo) { setFuture(future.slice(0,-1)); setPast([...past, song]); }
    else { setPast(past.slice(0,-1)); setFuture([...future, song]); }
    setSong(target); setDirty(true);
  }
  async function play(from = time, end = song?.duration ?? 0) {
    stop(); if (!song || !buffers.current) return;
    try {
      const ctx = new AudioContext(); await ctx.resume();
      const offset = Math.min(from, song.duration - 0.001);
      const p = {ctx, offset, end:Math.min(end,song.duration), start: ctx.currentTime + 0.04, raf: 0}; playback.current = p;
      for (const role of (mode === 'both' ? ['vocals','instrumental'] : [mode]) as ('vocals'|'instrumental')[]) {
        const source = ctx.createBufferSource(), gain = ctx.createGain(); source.buffer = buffers.current[role];
        gain.gain.value = mode === 'both' ? 0.5 : 1; source.connect(gain).connect(ctx.destination); source.start(p.start, offset,p.end-offset);
      }
      setPlaying(true);
      const tick = () => {
        if (playback.current !== p) return;
        const current = Math.max(offset, p.offset + ctx.currentTime - p.start); setTime(current);
        if (current >= p.end) stop(); else p.raf = requestAnimationFrame(tick);
      }; tick();
    } catch (e) { stop(); setError(String(e)); }
  }
  function seek(t: number) { if (playing) void play(t); else setTime(t); }
  function linePlacement(index: number, start: number, entranceOnly = false) {
    const current = songRef.current!;
    const old = current.lines[index];
    let value = start;
    if (snap) {
      const {hz, hop_seconds: hop} = current.reference;
      const onsets = hz.flatMap((v, i) => v != null && (i === 0 || hz[i-1] == null) ? [i*hop] : []);
      const nearest = onsets.reduce((best, t) => Math.abs(t-value) < Math.abs(best-value) ? t : best, value + 1);
      if (Math.abs(nearest-value) <= 0.15) value = nearest;
    }
    const min = current.lines[index-1]?.end ?? 0, maxEnd = current.lines[index+1]?.start ?? current.duration;
    const end = entranceOnly ? old.end : value + old.end - old.start;
    return {start:value, end, valid:value>=min && end<=maxEnd && value<end};
  }
  function moveLine(index: number, start: number, entranceOnly = false) {
    const current = songRef.current; if (!current) return;
    const placement = linePlacement(index,start,entranceOnly);
    if (!placement.valid) { setError('Line would overlap a neighbor or exceed the clip. Edit its end first.'); return; }
    const next = structuredClone(current), line = next.lines[index], old = {...line};
    const value=placement.start, end=placement.end;
    line.start = value; line.end = end;
    const ratio = (end-value)/(old.end-old.start);
    line.words = line.words.map((w) => ({...w, start:value+(w.start-old.start)*ratio, end:value+(w.end-old.start)*ratio}));
    next.phrases.filter((p) => p.line_index === index).forEach((p) => {
      p.start = value + (p.start-old.start)*ratio; p.end = value + (p.end-old.start)*ratio;
    });
    setError(''); edit(next); return true;
  }
  useEffect(() => {
    if (!tap) return;
    const key = (e: KeyboardEvent) => {
      if (e.code !== 'Space' || e.repeat || /INPUT|TEXTAREA|SELECT/.test((e.target as HTMLElement).tagName)) return;
      e.preventDefault(); if (!playback.current) return;
      const index = tapIndex.current;
      if (index < (songRef.current?.lines.length ?? 0) && moveLine(index, clock(), true)) { setSelected([index]); tapIndex.current++; }
    };
    window.addEventListener('keydown', key); return () => window.removeEventListener('keydown', key);
  }, [tap, snap]);
  async function action(name: 'save'|'rebuild'|'review') {
    if (!loaded || !song) return;
    if (name === 'review' && !confirm('Have you listened to and checked ALL lyrics, word/phrase boundaries, pitch, exclusions, translations, and singer transitions? Mark this manifest reviewed?')) return;
    setBusy(true); setError(''); stop();
    try {
      const result: Loaded = await api(`/${song.id}/${name}`, {revision:loaded.revision, song});
      setLoaded(result); setSong(result.song); setDirty(false); setPast([]); setFuture([]);
      setStatus(name === 'save' ? 'Saved corrections with backups. Rebuild to publish them.' : name === 'rebuild' ? 'Rebuilt manifest. Listening review still required.' : 'Marked reviewed by you.');
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  async function saveClip(id:string,title:string,range:TimeRange){
    if(!loaded||!song)return;
    const result:Loaded=await api(`/${song.id}/crop`,{id,title,start:range.start,end:range.end,revision:loaded.revision});
    setWorkspace(false);setCatalog(await api(''));await load(result.song.id);
    setStatus('New short clip created as a draft. Review it before marking reviewed.');
  }
  function assign(slot: 0|1) {
    if (!song) return;
    const next = structuredClone(song), owners = new Map<string, number>();
    song.duet_sections?.forEach((s) => s.phrase_ids.forEach((id) => owners.set(id, s.slot)));
    const scored = [...new Set(song.phrases.map((p) => p.line_index))];
    scored.forEach((line, index) => song.phrases.filter((p) => p.line_index === line).forEach((p) => {
      if (!owners.has(p.id)) owners.set(p.id, Math.floor(index/3)%2);
      if (selected.includes(line)) owners.set(p.id, slot);
    }));
    const sections: DuetSection[] = [];
    [...song.phrases].sort((a,b) => a.start-b.start).forEach((p) => {
      const owner = owners.get(p.id)! as 0|1, last = sections.at(-1);
      if (last && last.slot === owner) last.phrase_ids.push(p.id);
      else sections.push({id:`section-${sections.length+1}`,slot:owner,phrase_ids:[p.id]});
    }); next.duet_sections = sections; edit(next);
  }
  function updateLine(index: number, patch: Partial<Line>) {
    if (!song) return;
    const next = structuredClone(song); Object.assign(next.lines[index],patch);
    if (patch.text !== undefined && patch.text !== song.lines[index].text) {
      next.lines[index].words=[]; next.lines[index].romanized='(regenerated on Save)';
    }
    edit(next);
  }
  const ownerFor = (index: number) => {
    if (!song) return '';
    const phrases = song.phrases.filter((p) => p.line_index === index);
    if (!phrases.length) return 'Display only';
    if (song.duet_sections) {
      const slots = new Set(song.duet_sections.filter((s) => s.phrase_ids.some((id) => phrases.some((p) => p.id === id))).map((s) => s.slot));
      return slots.size === 1 ? `Player ${[...slots][0]+1}` : 'Missing/conflicting assignment';
    }
    const lines = [...new Set(song.phrases.map((p) => p.line_index))]; return `Player ${Math.floor(lines.indexOf(index)/3)%2+1} (default)`;
  };
  const lineIndex = selected.at(-1) ?? 0, line = song?.lines[lineIndex];
  return <main>
    <h1>Song author · local review</h1>
    <p>Listen, correct, Save, then Rebuild. Review is a separate human decision. No autosave.</p>
    <AddSong disabled={busy || dirty} onOpen={async (id) => { setCatalog(await api('')); await load(id); }}/>
    <label>Song <select aria-label="Song" disabled={busy} value={song?.id ?? ''} onChange={(e) => void load(e.target.value)}>
      <option value="" disabled>Choose a song</option>{catalog.map((s) => <option key={s.id} value={s.id}>{s.artist} · {s.title}</option>)}
    </select></label>
    <div className="toolbar">
      <button disabled={!past.length || busy} onClick={() => history(false)}>Undo</button><button disabled={!future.length || busy} onClick={() => history(true)}>Redo</button>
      <button disabled={!song || busy} onClick={() => void action('save')}>Save</button>
      <button disabled={!song || busy || dirty} onClick={() => void action('rebuild')}>Rebuild</button>
      <button disabled={!song || busy || dirty || loaded?.review.author_pending_rebuild} onClick={() => void action('review')}>Mark reviewed</button>
      <button disabled={!song||busy} onClick={()=>{stop();setWorkspace(true);}}>Open timing / crop workspace</button>
      <span>{dirty ? 'Unsaved edits' : loaded?.review.reviewed ? 'Reviewed' : 'Draft'}</span>
    </div>
    <p role="status">{status}</p>{error && <p role="alert">{error}</p>}
    {song && <>
      <div className="toolbar"><select aria-label="Playback mix" value={mode} onChange={(e) => {stop(); setMode(e.target.value);}}>
        <option value="vocals">Vocals</option><option value="instrumental">Instrumental</option><option value="both">Both</option></select>
        <button disabled={busy || !buffers.current} onClick={() => playing ? stop() : void play()}>{playing ? 'Pause' : 'Play'}</button>
        <button onClick={() => {stop(); setTime(0);}}>Reset</button><span>{time.toFixed(2)} / {song.duration.toFixed(2)} s</span>
        <label><input type="checkbox" checked={snap} onChange={(e) => setSnap(e.target.checked)}/> Snap to voiced onsets (150 ms)</label>
        <button aria-pressed={tap} onClick={() => {tapIndex.current=lineIndex; setTap(!tap);}}>Tap-to-sync {tap ? 'ON · Space at each entrance' : 'OFF'}</button>
      </div>
      <ClipTimeline duration={song.duration} phrases={song.phrases} lines={song.lines} range={null} playhead={time}
        selectedLines={selected} lineLabels={song.lines.map((_,i) => ownerFor(i))} onSeek={seek}
        onLineSelect={(i, additive) => setSelected(additive ? selected.includes(i) ? selected.filter((n) => n!==i) : [...selected,i] : [i])}
        onLineMove={moveLine} onLineMovePreview={linePlacement}
        overlay={<TimelineWaveform peaks={peaks} reference={song.reference} duration={song.duration}/>}/>
      <p>Click a line to seek/select. Ctrl/Shift-click selects several. Drag a lyric block to move it. Pink line: reference pitch (65–1000 Hz, logarithmic).</p>
      <div className="toolbar"><button className="p1" onClick={() => assign(0)}>Assign Player 1</button><button className="p2" onClick={() => assign(1)}>Assign Player 2</button>
        <button onClick={() => {const next=structuredClone(song); delete next.duet_sections; edit(next);}}>Use default distribution</button></div>
      <div className="columns"><section aria-label="Lyric lines"><h2>Lyrics and distribution</h2>
        {song.lines.map((l,i) => <button key={i} className={`lyric ${ownerFor(i).includes('Player 2')?'p2':'p1'} ${selected.includes(i)?'selected':''}`}
          aria-pressed={selected.includes(i)} onClick={(e) => {setSelected(e.ctrlKey || e.shiftKey ? [...new Set([...selected,i])] : [i]); seek(l.start);}}>
          <strong>{i+1} · {ownerFor(i)} · {l.start.toFixed(2)}–{l.end.toFixed(2)}</strong><span>{l.text}</span><span>{l.romanized}</span>
        </button>)}
      </section><section><h2>Selected line {lineIndex+1}</h2>{line && <>
        <label>Original text<textarea aria-label="Original text" value={line.text} onChange={(e) => updateLine(lineIndex,{text:e.target.value})}/></label>
        <p lang="ko-Latn">{line.romanized}</p>
        <label>Translation<textarea value={line.translation} onChange={(e) => updateLine(lineIndex,{translation:e.target.value})}/></label>
        <label>Line start<input aria-label="Line start" type="number" step="0.01" value={line.start} onChange={(e) => moveLine(lineIndex,Number(e.target.value),true)}/></label>
        <label>Line end<input type="number" step="0.01" value={line.end} onChange={(e) => {
          const end=Number(e.target.value), next=structuredClone(song); next.lines[lineIndex].end=end;
          next.lines[lineIndex].words=next.lines[lineIndex].words.filter((w) => w.end<=end); edit(next);
        }}/></label>
        <h3>Scored phrases · include held notes</h3>{song.phrases.filter((p) => p.line_index===lineIndex).map((p) => <div key={p.id}>{p.id}{(['start','end'] as const).map((edge) => <label key={edge}>{edge}<input type="number" step="0.01" value={p[edge]} onChange={(e) => {
          const next=structuredClone(song); next.phrases.find((v) => v.id===p.id)![edge]=Number(e.target.value); edit(next);
        }}/></label>)}</div>)}
      </>}
      <h2>Excluded regions</h2>{song.reference.excluded.map((r,i) => <div key={i} className="region">{(['start','end','reason'] as const).map((key) => <label key={key}>{key}<input type={key==='reason'?'text':'number'} step="0.01" value={r[key]} onChange={(e) => {
        const next=structuredClone(song); next.reference.excluded[i]={...r,[key]:key==='reason'?e.target.value:Number(e.target.value)}; edit(next);
      }}/></label>)}<button onClick={() => {const next=structuredClone(song);next.reference.excluded.splice(i,1);edit(next);}}>Remove</button></div>)}
      <button onClick={() => {const next=structuredClone(song); next.reference.excluded.push({start:Math.min(time,song.duration-0.1),end:Math.min(song.duration,time+1),reason:'Listening review'});edit(next);}}>Add exclusion at playhead</button>
      </section></div>
      {workspace&&<CropWorkspace song={song} range={null} author readOnly={busy} onClose={()=>{stop();setWorkspace(false);}}
        onSaveClip={saveClip} saveDisabled={busy||dirty||!!loaded?.review.author_pending_rebuild}
        onPreview={(range,from)=>void play(from??range.start,range.end)} onStop={stop} playing={playing} playhead={time}
        peaks={peaks} selectedLines={selected} lineLabels={song.lines.map((_,i)=>ownerFor(i))}
        onLineSelect={(i,additive)=>setSelected(additive?selected.includes(i)?selected.filter(n=>n!==i):[...selected,i]:[i])}
        onLineMove={moveLine} onLineMovePreview={linePlacement}
        editor={<>
          <div className="toolbar"><label>Preview mix<select aria-label="Workspace playback mix" value={mode} onChange={e=>{stop();setMode(e.target.value);}}>
            <option value="vocals">Vocals</option><option value="instrumental">Instrumental</option><option value="both">Both</option></select></label>
            <label><input type="checkbox" checked={snap} onChange={e=>setSnap(e.target.checked)}/> Snap moves to voiced onsets (150 ms)</label>
            <button disabled={!past.length||busy} onClick={()=>history(false)}>Undo edit</button><button disabled={!future.length||busy} onClick={()=>history(true)}>Redo edit</button></div>
          <div className="toolbar"><button disabled={busy} onClick={()=>void action('save')}>Save lyric edits</button><button disabled={busy||dirty} onClick={()=>void action('rebuild')}>Rebuild saved edits</button>
            <button onClick={()=>assign(0)}>Assign Player 1</button><button onClick={()=>assign(1)}>Assign Player 2</button></div>
          <p>{dirty?'Unsaved lyric/timing edits':loaded?.review.author_pending_rebuild?'Saved; rebuild before creating a clip':'Lyric/timing edits saved'}</p>
          {error&&<p role="alert">{error}</p>}
          {line&&<><h3>Selected line {lineIndex+1}</h3>
            <label>Original text<textarea aria-label="Workspace original text" value={line.text} onChange={e=>updateLine(lineIndex,{text:e.target.value})}/></label><p>{line.romanized}</p>
            <label>Line start<input aria-label="Workspace line start" type="number" step=".01" value={line.start} onChange={e=>moveLine(lineIndex,Number(e.target.value),true)}/></label>
            <label>Line end<input aria-label="Workspace line end" type="number" step=".01" value={line.end} onChange={e=>{const next=structuredClone(song);next.lines[lineIndex].end=Number(e.target.value);edit(next);}}/></label>
            <h4>Scored phrases · include held endings</h4>{song.phrases.filter(p=>p.line_index===lineIndex).map(p=><div key={p.id}>{p.id}{(['start','end'] as const).map(edge=><label key={edge}>{edge}<input aria-label={`Workspace phrase ${p.id} ${edge}`} type="number" step=".01" value={p[edge]} onChange={e=>{const next=structuredClone(song);next.phrases.find(v=>v.id===p.id)![edge]=Number(e.target.value);edit(next);}}/></label>)}</div>)}
          </>}
        </>}/>}
    </>}
  </main>;
}
createRoot(document.getElementById('root')!).render(<App/>);

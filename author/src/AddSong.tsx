import { useEffect, useState, type FormEvent } from 'react';

type Job = {
  id: string; song_id: string; title: string;
  status: 'queued' | 'processing' | 'ready' | 'failed' | 'canceled';
  stage: string; message: string; cancel_requested: boolean;
};
const stages = [
  ['separating', 'Separate stems'], ['encoding', 'Prepare audio'], ['aligning', 'Align lyrics'],
  ['pitch', 'Extract pitch'], ['manifest', 'Build draft'],
];
async function request(path: string, options?: RequestInit) {
  const response = await fetch('/api/imports' + path, options);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Could not prepare this song.');
  return result;
}

export function AddSong({ disabled, onOpen }: { disabled: boolean; onOpen: (id: string) => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [available, setAvailable] = useState(false), [availability, setAvailability] = useState('Checking audio processing…');
  const [title, setTitle] = useState(''), [artist, setArtist] = useState(''), [songId, setSongId] = useState('');
  const [manualId, setManualId] = useState(false), [language, setLanguage] = useState('ko');
  const [lyrics, setLyrics] = useState(''), [audio, setAudio] = useState<File | null>(null);
  const [job, setJob] = useState<Job | null>(null), [error, setError] = useState(''), [sending, setSending] = useState(false);
  const running = job?.status === 'queued' || job?.status === 'processing';

  useEffect(() => {
    let live = true;
    request('').then((result) => {
      if (!live) return;
      setAvailable(result.available); setAvailability(result.message);
      setJob(result.jobs[0] ?? null);
    }).catch((e) => live && setError(e.message));
    return () => { live = false; };
  }, []);
  useEffect(() => {
    if (!job || !running) return;
    let live = true;
    const tick = async () => {
      try {
        const next = await request('/' + job.id);
        if (live) { setJob(next); setError(''); }
      } catch { if (live) setError('Could not refresh processing status. Retrying…'); }
    };
    const timer = window.setInterval(() => void tick(), 1000);
    return () => { live = false; clearInterval(timer); };
  }, [job?.id, running]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!audio) return;
    setSending(true); setError('');
    try {
      const form = new FormData();
      for (const [key, value] of Object.entries({song_id: songId, title, artist, language, lyrics})) form.set(key, value);
      form.set('audio', audio);
      setJob(await request('', {method: 'POST', body: form}));
      setOpen(false);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setSending(false); }
  }
  async function action(name: 'cancel' | 'retry') {
    if (!job) return;
    setSending(true); setError('');
    try { setJob(await request(`/${job.id}/${name}`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'})); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setSending(false); }
  }
  const current = stages.findIndex(([key]) => key === job?.stage);
  return <section className="add-song" aria-label="Add a song">
    <button type="button" disabled={disabled || sending || running} onClick={() => setOpen(!open)} aria-expanded={open}>
      {open ? 'Close add song' : 'Add song'}
    </button>
    {open && <form onSubmit={(event) => void submit(event)}>
      <h2>Add a recording</h2>
      <p>Choose audio with lead vocals and paste its lyrics, one sung line per line. Processing creates a draft with stems, timed lyrics and reference pitch. Full songs can take several minutes.</p>
      {!available && <p role="status">{availability}</p>}
      <fieldset disabled={disabled || sending || running || !available}>
        <div className="import-fields">
          <label>Song title<input required maxLength={200} value={title} onChange={(event) => {
            const value = event.target.value; setTitle(value);
            if (!manualId) setSongId(value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0,80));
          }}/></label>
          <label>Artist<input required maxLength={200} value={artist} onChange={(event) => setArtist(event.target.value)}/></label>
          <label>Song ID (unique)<input required pattern="[A-Za-z0-9][A-Za-z0-9_-]{0,79}" value={songId} onChange={(event) => { setSongId(event.target.value); setManualId(true); }}/></label>
          <label>Language<select aria-label="Language" value={language} onChange={(event) => setLanguage(event.target.value)}><option value="ko">Korean</option><option value="en">English</option></select></label>
        </div>
        <label>Audio file<input type="file" required accept=".mp3,.wav,.flac,.m4a,.ogg,.aac" onChange={(event) => setAudio(event.target.files?.[0] ?? null)}/></label>
        <p>MP3, WAV, FLAC, M4A, OGG or AAC; up to 250 MB. Use a new song ID to keep existing songs.</p>
        <label>Lyrics<textarea required maxLength={100000} value={lyrics} onChange={(event) => setLyrics(event.target.value)} placeholder="One sung line per line"/></label>
        <button type="submit">{sending ? 'Uploading…' : 'Process song'}</button>
      </fieldset>
    </form>}
    {job && <div className="import-job" aria-label="Song preparation">
      <h3>{job.title}</h3><p role="status">{job.message}</p>
      {running && <ol className="import-stages" aria-label="Preparation progress">{stages.map(([key, label], index) =>
        <li key={key} aria-current={index === current ? 'step' : undefined} className={index < current ? 'complete' : ''}>{label}</li>)}</ol>}
      <div className="toolbar">
        {running && <button disabled={sending || job.cancel_requested} onClick={() => void action('cancel')}>Cancel processing</button>}
        {(job.status === 'failed' || job.status === 'canceled') && <button disabled={sending || !available} onClick={() => void action('retry')}>Retry processing</button>}
        {job.status === 'ready' && <button disabled={disabled} onClick={() => void onOpen(job.song_id)}>Open draft</button>}
        <a href={`/api/imports/${job.id}/log`} target="_blank" rel="noreferrer">View processing log</a>
      </div>
    </div>}
    {error && <p role="alert">{error}</p>}
  </section>;
}

import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from 'react';
import { PixelButton } from '../../ui';
import type { Song, TimeRange } from '../../lib/types';
import { ClipTimeline, type LineMovePreview } from './ClipTimeline';
import { boundaries, includedPhrases, snapBoundary } from './range';
import { PracticeSectionView } from './PracticeSectionView';
import './CropWorkspace.css';
import './PracticeSectionView.css';

export const clockLabel = (time: number) => {
  const ticks=Math.max(0,Math.round(time*100));
  return `${Math.floor(ticks/6000)}:${((ticks%6000)/100).toFixed(2).padStart(5,'0')}`;
};
function seconds(text: string) {
  const value = text.trim();
  if (/^\d+(?:\.\d+)?$/.test(value)) return Number(value);
  const match = /^(\d+):([0-5]?\d(?:\.\d+)?)$/.exec(value);
  return match ? Number(match[1]) * 60 + Number(match[2]) : NaN;
}
function TimeField({label,value,onCommit,disabled}: {label:string;value:number;onCommit:(time:number)=>void;disabled:boolean}) {
  const [draft,setDraft]=useState(clockLabel(value));
  useEffect(()=>setDraft(clockLabel(value)),[value]);
  const valid=Number.isFinite(seconds(draft));
  function commit(){ if(valid)onCommit(seconds(draft));else setDraft(clockLabel(value)); }
  return <label>{label}<input aria-label={label} value={draft} inputMode="decimal" disabled={disabled}
    aria-invalid={!valid} onChange={e=>setDraft(e.target.value)} onBlur={commit}
    onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();commit();}}}/></label>;
}

/** Decode one stem only for its compact waveform; the decoded audio is released afterward. */
async function waveform(urls: string[], signal: AbortSignal) {
  for(const url of urls){
    try{
      const response=await fetch(url,{signal});if(!response.ok)continue;
      const bytes=await response.arrayBuffer();
      const ctx=new AudioContext();
      try{
        const audio=await ctx.decodeAudioData(bytes), data=audio.getChannelData(0);
        const step=Math.max(1,Math.ceil(data.length/1800)), peaks:number[]=[];
        for(let i=0;i<data.length;i+=step){let max=0;for(let j=i;j<Math.min(data.length,i+step);j++)max=Math.max(max,Math.abs(data[j]));peaks.push(max);}
        return peaks;
      }finally{await ctx.close();}
    }catch(error){if(signal.aborted)throw error;}
  }
  return [];
}

function Waveform({peaks,reference,duration}: {peaks:number[];reference?:Song['reference'];duration:number}){
  const wave=useMemo(()=>peaks.map((peak,i)=>`M${i/peaks.length*1000},${55-peak*48}v${peak*96}`).join(''),[peaks]);
  const pitch=useMemo(()=>{
    if(!reference)return '';
    const every=Math.max(1,Math.ceil(reference.hz.length/5000));let connected=false,path='';
    for(let i=0;i<reference.hz.length;i+=every){const hz=reference.hz[i];if(!hz){connected=false;continue;}
      const y=100-Math.max(0,Math.min(1,Math.log2(hz/65)/Math.log2(1000/65)))*90;
      path+=`${connected?'L':'M'}${i*reference.hop_seconds/duration*1000},${y}`;connected=true;}
    return path;
  },[reference,duration]);
  return <svg className="crop-waveform" viewBox="0 0 1000 110" preserveAspectRatio="none" aria-label={reference?'Waveform and reference pitch':'Song waveform'}>
    <path d={wave} stroke="#4a8093" strokeWidth=".8" fill="none"/>{pitch&&<path d={pitch} stroke="#b52660" strokeWidth="1" vectorEffect="non-scaling-stroke" fill="none"/>}
  </svg>;
}
export { Waveform as TimelineWaveform };

type Props={
  song:Song; range:TimeRange|null; onClose:()=>void;
  onApply?:(range:TimeRange)=>Promise<boolean|void>|boolean|void;
  onSaveClip?:(id:string,title:string,range:TimeRange)=>Promise<void>;
  onPreview:(range:TimeRange,from?:number)=>void; onStop:()=>void; playing:boolean; playhead:number|null;
  peaks?:number[]; waveformUrls?:string[]; readOnly?:boolean; author?:boolean; saveDisabled?:boolean;
  selectedLines?:number[]; lineLabels?:string[]; onLineSelect?:(index:number,additive:boolean)=>void;
  onLineMove?:(index:number,start:number)=>void; onLineMovePreview?:(index:number,start:number)=>LineMovePreview;
  editor?:ReactNode;
};

export function CropWorkspace({song,range,onClose,onApply,onSaveClip,onPreview,onStop,playing,playhead,
  peaks:providedPeaks,waveformUrls,readOnly=false,author=false,saveDisabled=false,
  selectedLines,lineLabels,onLineSelect,onLineMove,onLineMovePreview,editor}:Props){
  const dialog=useRef<HTMLDialogElement>(null), detail=useRef<HTMLDivElement>(null), titleId=useId();
  const [selection,setSelection]=useState<TimeRange>(range??{start:0,end:song.duration});
  const [cursor,setCursor]=useState(selection.start),[focus,setFocus]=useState({time:selection.start,token:0});
  const [width,setWidth]=useState(900),[scale,setScale]=useState(900/Math.min(30,song.duration));
  const [viewport,setViewport]=useState({start:0,end:Math.min(30,song.duration)});
  const [query,setQuery]=useState(''),[peaks,setPeaks]=useState(providedPeaks??[]),[loading,setLoading]=useState(false);
  const [error,setError]=useState(''),[saving,setSaving]=useState(false);
  const [clipId,setClipId]=useState(`${song.id.slice(0,60)}-clip`),[clipTitle,setClipTitle]=useState(`${song.title} (Short clip)`);
  const position=playing&&playhead!==null?Math.max(0,Math.min(song.duration,playhead)):cursor;
  const controlsDisabled=readOnly||saving;
  const fullScale=width/song.duration;
  useEffect(()=>{if(playing&&playhead!==null)setCursor(Math.max(0,Math.min(song.duration,playhead)));},[playing,playhead,song.duration]);
  useEffect(()=>{const node=dialog.current!;node.showModal();return()=>{if(node.open)node.close();};},[]);
  useEffect(()=>{
    const observer=new ResizeObserver(entries=>setWidth(Math.max(400,entries[0].contentRect.width-44)));
    if(detail.current)observer.observe(detail.current);return()=>observer.disconnect();
  },[]);
  useEffect(()=>{if(providedPeaks)setPeaks(providedPeaks);},[providedPeaks]);
  useEffect(()=>{if(readOnly)setSelection(range??{start:0,end:song.duration});},[readOnly,range?.start,range?.end,song.duration]);
  useEffect(()=>{
    if(providedPeaks||!waveformUrls?.length)return;
    const controller=new AbortController();setLoading(true);
    waveform(waveformUrls,controller.signal).then(value=>{if(!controller.signal.aborted)setPeaks(value);})
      .catch(()=>{}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return()=>controller.abort();
  },[]);
  function close(){if(saving)return;onStop();onClose();}
  function seek(time:number){onStop();const next=Math.max(0,Math.min(song.duration,time));setCursor(next);setFocus(old=>({time:next,token:old.token+1}));}
  function edge(which:'start'|'end',time:number,expand=false){
    if(controlsDisabled)return;
    if(!Number.isFinite(time)||time<0||time>song.duration){setError('Choose a time inside the song.');return;}
    let candidate={...selection};
    if(expand&&which==='start'&&time>=candidate.end)candidate.end=song.duration;
    if(expand&&which==='end'&&time<=candidate.start)candidate.start=0;
    if(which==='start'?time>=candidate.end:time<=candidate.start){setError('The start must come before the end.');return;}
    if(!author){const values=boundaries(song.phrases,candidate,which);if(!values.length)return;time=snapBoundary(values,time);}
    candidate={...candidate,[which]:time};setError('');onStop();setSelection(candidate);seek(time);
  }
  function lineEdge(index:number,which:'start'|'end'){
    const line=song.lines[index],phrases=song.phrases.filter(p=>p.line_index===index);
    if(!author&&!phrases.length){setError('This line has no scored phrase. Choose another line.');return;}
    const time=which==='start'?(author?line.start:Math.min(...phrases.map(p=>p.start)))
      :Math.max(line.end,...phrases.map(p=>p.end));
    edge(which,time,true);
  }
  async function apply(){
    if(!onApply)return;setSaving(true);setError('');onStop();
    try{if(await onApply(selection)!==false)onClose();else setError('The section could not be saved. Try again.');}
    catch(error){setError(error instanceof Error?error.message:'Could not save the section.');}
    finally{setSaving(false);}
  }
  async function saveClip(){
    if(!onSaveClip)return;setSaving(true);setError('');onStop();
    try{await onSaveClip(clipId,clipTitle,selection);onClose();}
    catch(error){setError(error instanceof Error?error.message:'Could not create the short clip.');}
    finally{setSaving(false);}
  }
  const filtered=song.lines.map((line,index)=>({line,index})).filter(({line})=>
    `${line.text} ${line.romanized}`.toLocaleLowerCase().includes(query.toLocaleLowerCase()));
  return <dialog ref={dialog} className={`crop-workspace${author?'':' crop-workspace--practice'}`} aria-labelledby={titleId} onCancel={event=>{event.preventDefault();close();}}>
    <header><div><h2 id={titleId}>{author?'Song timing and cropping':readOnly?'View practice section':'Choose a practice section'}</h2><p>{song.title} · {song.artist}</p></div>
      {author?<button type="button" onClick={close} disabled={saving}>Close / back</button>
        :<PixelButton size="sm" tone="paper" onClick={close} disabled={saving}>Close / back</PixelButton>}</header>
    {!author ? <PracticeSectionView song={song} selection={selection} position={position} disabled={controlsDisabled}
      onSeek={seek} onEdge={edge} onLineEdge={lineEdge} waveform={<Waveform peaks={peaks} duration={song.duration}/>}>
      <div className="practice-section-controls">
        <PixelButton size="sm" tone="hot" disabled={saving} onClick={()=>playing?onStop():onPreview(selection,selection.start)}>{playing?'Stop preview':'Preview selection'}</PixelButton>
        <PixelButton size="sm" tone="sky" disabled={saving||position>=song.duration} onClick={()=>onPreview({start:position,end:song.duration},position)}>Listen from playhead</PixelButton>
        <div className="practice-set-edges"><PixelButton size="sm" tone="mint" disabled={controlsDisabled} onClick={()=>edge('start',position,true)}>Set start here</PixelButton>
          <PixelButton size="sm" tone="pink" disabled={controlsDisabled} onClick={()=>edge('end',position,true)}>Set end here</PixelButton></div>
        <TimeField label="Section start" value={selection.start} disabled={controlsDisabled} onCommit={time=>edge('start',time)}/>
        <TimeField label="Section end" value={selection.end} disabled={controlsDisabled} onCommit={time=>edge('end',time)}/>
        <PixelButton size="sm" tone="paper" disabled={controlsDisabled} onClick={()=>{onStop();setSelection({start:0,end:song.duration});seek(0);}}>Select full song</PixelButton>
      </div>
      <p className="practice-tip">{readOnly?'The host chooses the section. You can browse the lyrics and listen.':`${includedPhrases(song.phrases,selection).length} scored phrases · Boundaries snap to whole phrases`}{loading?' · Loading waveform…':''}</p>
    </PracticeSectionView> : <div className="crop-workspace__body">
      <section className="crop-workspace__main" ref={detail} aria-label="Crop timeline">
        <div className="crop-overview" role="slider" tabIndex={0} aria-label="Browse song overview" aria-valuemin={0} aria-valuemax={song.duration} aria-valuenow={position}
          onPointerDown={e=>{e.currentTarget.setPointerCapture(e.pointerId);const r=e.currentTarget.getBoundingClientRect();seek((e.clientX-r.left)/r.width*song.duration);}}
          onPointerMove={e=>{if(e.currentTarget.hasPointerCapture(e.pointerId)){const r=e.currentTarget.getBoundingClientRect();seek((e.clientX-r.left)/r.width*song.duration);}}}
          onPointerUp={e=>{if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);}}
          onKeyDown={e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();seek(e.key==='Home'?0:e.key==='End'?song.duration:position+(e.key==='ArrowRight'?5:-5));}}}>
          <Waveform peaks={peaks} duration={song.duration}/>
          <div className="crop-overview__selection" style={{left:`${selection.start/song.duration*100}%`,width:`${(selection.end-selection.start)/song.duration*100}%`}}/>
          <div className="crop-overview__viewport" style={{left:`${viewport.start/song.duration*100}%`,width:`${Math.max(0,viewport.end-viewport.start)/song.duration*100}%`}}/>
          <div className="crop-overview__cursor" style={{left:`${position/song.duration*100}%`}}/>
        </div>
        <p className="crop-hint">Whole-song overview · click or drag to jump · {clockLabel(song.duration)}{loading?' · Loading waveform…':''}</p>
        <div className="crop-controls">
          <button onClick={()=>setScale(value=>Math.max(fullScale,value/1.6))}>Zoom out</button>
          <button onClick={()=>setScale(value=>Math.min(240,value*1.6))}>Zoom in</button>
          <button onClick={()=>{setScale(fullScale);setFocus(old=>({time:0,token:old.token+1}));}}>Fit song</button>
          <button onClick={()=>{setScale(Math.min(240,width/Math.max(1,selection.end-selection.start)*.85));setFocus(old=>({time:(selection.start+selection.end)/2,token:old.token+1}));}}>Fit selection</button>
          <span>Playhead {clockLabel(position)}</span>
        </div>
        <ClipTimeline duration={song.duration} phrases={song.phrases} lines={song.lines} range={selection}
          onChange={controlsDisabled?undefined:next=>{onStop();setSelection(next);}} playhead={position} onSeek={seek}
          pixelsPerSecond={Math.max(fullScale,scale)} scrollToTime={focus} followPlayhead={playing} freeBoundaries={author}
          onViewportChange={setViewport} selectedLines={selectedLines} lineLabels={lineLabels}
          onLineSelect={onLineSelect} onLineMove={controlsDisabled?undefined:onLineMove} onLineMovePreview={onLineMovePreview}
          overlay={<Waveform peaks={peaks} reference={author?song.reference:undefined} duration={song.duration}/>}/>
        <div className="crop-controls crop-times">
          <TimeField label="Section start" value={selection.start} disabled={controlsDisabled} onCommit={time=>edge('start',time)}/>
          <TimeField label="Section end" value={selection.end} disabled={controlsDisabled} onCommit={time=>edge('end',time)}/>
          <button disabled={controlsDisabled} onClick={()=>edge('start',position,true)}>Set start here</button>
          <button disabled={controlsDisabled} onClick={()=>edge('end',position,true)}>Set end here</button>
          <button disabled={controlsDisabled} onClick={()=>{onStop();setSelection({start:0,end:song.duration});seek(0);}}>Select full song</button>
        </div>
        <p className="crop-hint">{clockLabel(selection.start)}–{clockLabel(selection.end)} · {(selection.end-selection.start).toFixed(2)} seconds · {includedPhrases(song.phrases,selection).length} whole scored phrases{author?'':' · Practice boundaries snap to whole phrases'}</p>
        <div className="crop-controls">
          <button disabled={saving} onClick={()=>playing?onStop():onPreview(selection,selection.start)}>{playing?'Stop preview':'Preview selection'}</button>
          <button disabled={saving||position>=song.duration} onClick={()=>onPreview({start:position,end:song.duration},position)}>Listen from playhead</button>
        </div>
        {editor&&<fieldset disabled={controlsDisabled} className="crop-author-fields" aria-label="Selected line timing">{editor}</fieldset>}
      </section>
      <aside className="crop-workspace__lyrics" aria-label="Lyric navigation">
        <label>Find lyrics<input aria-label="Find lyrics" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Original or romanized text"/></label>
        <div>{filtered.map(({line,index})=><article key={index} className={selectedLines?.includes(index)?'is-current':''}>
          <button className="crop-lyric" onClick={event=>{onLineSelect?.(index,event.ctrlKey||event.metaKey||event.shiftKey);seek(line.start);}}>
            <small>{index+1} · {clockLabel(line.start)} {lineLabels?.[index]}</small><span>{line.text}</span><span>{line.romanized}</span>
          </button>
          <div className="crop-controls"><button disabled={controlsDisabled} onClick={()=>lineEdge(index,'start')}>Start here</button><button disabled={controlsDisabled} onClick={()=>lineEdge(index,'end')}>End here</button></div>
        </article>)}{!filtered.length&&<p>No matching lyrics.</p>}</div>
      </aside>
    </div>}
    <footer>
      {error&&<p role="alert">{error}</p>}
      {onApply&&(author?<button disabled={controlsDisabled} onClick={()=>void apply()}>{saving?'Saving…':'Use this practice section'}</button>
        :<PixelButton tone="hot" disabled={controlsDisabled} onClick={()=>void apply()}>{saving?'Saving…':'Use this practice section'}</PixelButton>)}
      {onSaveClip&&<form className="crop-save" onSubmit={event=>{event.preventDefault();void saveClip();}}>
        <label>New clip ID<input aria-label="New clip ID" required pattern="[A-Za-z0-9][A-Za-z0-9_-]{0,79}" value={clipId} onChange={e=>setClipId(e.target.value)} disabled={saving}/></label>
        <label>New clip title<input aria-label="New clip title" required maxLength={200} value={clipTitle} onChange={e=>setClipTitle(e.target.value)} disabled={saving}/></label>
        <button disabled={saving||saveDisabled}>{saving?'Creating clip…':'Save as new short clip'}</button>
        {saveDisabled&&<span>Save your lyric/timing edits first.</span>}
      </form>}
    </footer>
  </dialog>;
}

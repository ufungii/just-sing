// Frontend adapter: read the real playback clock; never increment a lyric timer.
export function activeIndices(lines, seconds) {
  const find = (items) => {
    let low = 0, high = items.length;
    while (low < high) {
      const middle = Math.floor((low + high) / 2);
      if (items[middle].start <= seconds) low = middle + 1;
      else high = middle;
    }
    const index = low - 1;
    return index >= 0 && seconds < items[index].end ? index : null;
  };
  if (!Number.isFinite(seconds)) return { lineIndex: null, wordIndex: null };
  const lineIndex = find(lines);
  return { lineIndex, wordIndex: lineIndex === null ? null : find(lines[lineIndex].words ?? []) };
}

export async function loadLyrics(songId) {
  const response = await fetch(`/api/songs/${encodeURIComponent(songId)}/lyrics`, { cache: "no-store" });
  if (!response.ok) throw new Error(`Could not load lyrics (${response.status})`);
  return response.json();
}

export function followPlayback(track, getPlaybackSeconds, onChange) {
  // React can render each word as a span and highlight the returned word index.
  // getPlaybackSeconds must use the SAME AudioContext timeline as the music.
  if (track.status !== "ready") {
    onChange({ status: "unavailable", reason: track.reason, line: null, word: null });
    return () => {};
  }
  let frame;
  let previous;
  let stopped = false;
  const render = () => {
    if (stopped) return;
    const { lineIndex, wordIndex } = activeIndices(track.lines, getPlaybackSeconds());
    const key = `${lineIndex}:${wordIndex}`;
    if (key !== previous) {
      previous = key;
      const line = lineIndex === null ? null : track.lines[lineIndex];
      onChange({ status: "ready", lineIndex, wordIndex, line,
                 word: wordIndex === null ? null : line.words[wordIndex] });
    }
    frame = requestAnimationFrame(render);
  };
  render();
  return () => { stopped = true; cancelAnimationFrame(frame); };
}

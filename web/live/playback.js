// Both stems start at the same sample-clock time and seek offset.
export function createPlayback(context, instrumental, vocals, when, offset, onended) {
  const backing = context.createBufferSource(), backingGain = context.createGain();
  backing.buffer = instrumental; backing.connect(backingGain).connect(context.destination);
  let guide, guideGain;
  if (vocals) {
    guide = context.createBufferSource(); guideGain = context.createGain();
    guide.buffer = vocals; guide.connect(guideGain).connect(context.destination);
    guideGain.gain.value = 0;
  }
  let stopped = false;
  function stop() {
    if (stopped) return;
    stopped = true; backing.onended = null;
    for (const node of [backing, guide]) if (node) { node.stop(); node.disconnect(); }
    backingGain.disconnect(); guideGain?.disconnect();
  }
  backing.onended = () => { stop(); onended(); };
  backing.start(when, offset); guide?.start(when, offset);
  return {
    stop,
    setVocals(enabled, volume = 0.5) {
      // A stronger guide: 50% matches the backing, 100% is twice its level.
      const level = enabled && guide && Number.isFinite(volume) ? 2 * Math.max(0, Math.min(1, volume)) : 0;
      // Leave mixing headroom when combining independently mastered estimates.
      backingGain.gain.setTargetAtTime(1 / (1 + level), context.currentTime, 0.015);
      guideGain?.gain.setTargetAtTime(level / (1 + level), context.currentTime, 0.015);
    },
  };
}

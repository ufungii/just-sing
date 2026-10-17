/**
 * Mic capture on the audio thread. The processor batches input samples and posts each batch with the
 * frame number of its first sample. Frame / sampleRate is the same clock as AudioContext.currentTime,
 * so every captured sample has an exact time on the master clock (before the one device offset).
 *
 * The processor is plain JavaScript loaded from a Blob URL: it runs in AudioWorkletGlobalScope, which
 * has no DOM or module imports, and this keeps it out of the Vite bundle graph.
 */

export const CAPTURE_PROCESSOR = 'just-sing-capture';

/** Samples per posted batch: 4 render quanta (about 10.7 ms at 48 kHz). */
const BATCH = 512;

const SOURCE = `
class CaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buf = new Float32Array(${BATCH});
    this.fill = 0;
    this.startFrame = 0;
  }
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true; // no mic connected yet
    for (let i = 0; i < channel.length; i++) {
      if (this.fill === 0) this.startFrame = currentFrame + i;
      this.buf[this.fill++] = channel[i];
      if (this.fill === this.buf.length) {
        this.port.postMessage({ startFrame: this.startFrame, samples: this.buf }, [this.buf.buffer]);
        this.buf = new Float32Array(${BATCH});
        this.fill = 0;
      }
    }
    return true;
  }
}
registerProcessor('${CAPTURE_PROCESSOR}', CaptureProcessor);
`;

export interface CaptureBatch {
  /** AudioContext frame of samples[0]; time = startFrame / sampleRate on the currentTime clock. */
  startFrame: number;
  samples: Float32Array;
}

/** Register the capture processor with a context (once per context). */
export async function loadCaptureWorklet(ctx: AudioContext): Promise<void> {
  const url = URL.createObjectURL(new Blob([SOURCE], { type: 'application/javascript' }));
  try {
    await ctx.audioWorklet.addModule(url);
  } finally {
    URL.revokeObjectURL(url);
  }
}

// Capture timestamps come from sample frames on the playback AudioContext.
export class CaptureWindow {
  constructor(size = 4096, hop = 960) {
    this.size = size; this.hop = hop; this.ring = new Float32Array(size);
    this.cursor = 0; this.count = 0; this.since = 0;
  }
  push(value, frame, rate) {
    this.ring[this.cursor] = value; this.cursor = (this.cursor + 1) % this.size;
    this.count++; this.since++;
    if (this.count < this.size || this.since < this.hop) return null;
    this.since = 0;
    const samples = new Float32Array(this.size);
    for (let i = 0; i < this.size; i++) samples[i] = this.ring[(this.cursor + i) % this.size];
    return { samples, contextTime: (frame + 1 - this.size / 2) / rate };
  }
}

if (typeof AudioWorkletProcessor !== "undefined") {
  class CaptureProcessor extends AudioWorkletProcessor {
    constructor() {
      super(); this.window = new CaptureWindow(4096, Math.round(sampleRate * 0.02));
      this.port.onmessage = ({ data }) => { if (data.type === "reset") this.window = new CaptureWindow(4096, Math.round(sampleRate * 0.02)); };
    }
    process(inputs) {
      const channel = inputs[0]?.[0];
      if (channel) for (let i = 0; i < channel.length; i++) {
        const frame = this.window.push(channel[i], currentFrame + i, sampleRate);
        if (frame) this.port.postMessage(frame, [frame.samples.buffer]);
      }
      return true; // Outputs remain silent; never feed microphone back to speakers.
    }
  }
  registerProcessor("karaoke-capture", CaptureProcessor);
}

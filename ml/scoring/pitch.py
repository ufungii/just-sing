"""The shared reference pitch extractor; heavy libraries are loaded on demand."""

import math


def pitch_contour(audio, sample_rate=16000, *, backend="crepe", progress=None):
    import numpy as np
    from scipy.ndimage import median_filter

    signal = np.asarray(audio, dtype=np.float32)
    if signal.ndim != 1 or not len(signal) or not np.isfinite(signal).all():
        raise ValueError("Expected finite, nonempty mono audio")
    if sample_rate != 16000:
        import librosa
        signal = librosa.resample(signal, orig_sr=sample_rate, target_sr=16000)
    hop = 320
    if backend == "pyin":
        import librosa
        pitch, voiced, probability = librosa.pyin(signal, sr=16000, hop_length=hop, fmin=65, fmax=1000)
        confidence = np.asarray(probability)
        pitch = np.asarray(pitch)
        valid = np.asarray(voiced) & (confidence >= 0.5)
    elif backend == "crepe":
        import torch
        import torchcrepe
        torch.set_num_threads(4)
        frame_count = len(signal) // hop + 1
        pitch = np.full(frame_count, np.nan, dtype=np.float32)
        confidence = np.zeros(frame_count, dtype=np.float32)
        chunk_frames = 750  # 15s cores with 100ms context at the shared 20ms hop.
        for first in range(0, frame_count, chunk_frames):
            last = min(frame_count, first + chunk_frames)
            left_frame = max(0, first - 5)
            left = left_frame * hop
            right = min(len(signal), (last + 5) * hop)
            with torch.inference_mode():
                hz, periodicity = torchcrepe.predict(
                    torch.from_numpy(signal[left:right].copy()).unsqueeze(0),
                    16000, hop, 65, 1000, model="full", batch_size=256,
                    device="cpu", return_periodicity=True,
                )
            offset = first - left_frame
            count = min(last - first, hz.shape[1] - offset)
            pitch[first:first + count] = hz[0, offset:offset + count].cpu().numpy()
            confidence[first:first + count] = periodicity[0, offset:offset + count].cpu().numpy()
            if progress:
                progress(min(len(signal) / 16000, last * 0.02))
        confidence = median_filter(confidence, size=3, mode="nearest")
        valid = confidence >= 0.5
    else:
        raise ValueError("backend must be crepe or pyin")
    # RMS rejects silent windows even when the tracker emits a numerical pitch.
    padded = np.pad(signal, (512, 512))
    rms = np.array([np.sqrt(np.mean(padded[i * hop:i * hop + 1024] ** 2)) for i in range(len(pitch))])
    valid &= np.isfinite(pitch) & (rms >= 0.003) & (pitch >= 65) & (pitch <= 1000)
    smoothed = median_filter(np.nan_to_num(pitch, nan=0.0), size=3, mode="nearest")
    values = [float(value) if good and value > 0 and math.isfinite(float(value)) else None
              for value, good in zip(smoothed, valid)]
    return {"hop_seconds": 0.02, "hz": values,
            "periodicity": [float(value) if math.isfinite(float(value)) else 0.0 for value in confidence],
            "backend": backend, "settings": {"sample_rate_hz": 16000, "fmin": 65, "fmax": 1000,
                                               "periodicity_threshold": 0.5, "minimum_rms": 0.003}}

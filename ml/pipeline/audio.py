"""FFmpeg audio decoding shared by alignment, pitch extraction and crop checks."""
import subprocess


def decoded_frames(path):
    """Count decoded stereo frames on the 44.1 kHz playback timeline."""
    import imageio_ffmpeg

    result = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-i", str(path),
         "-ar", "44100", "-ac", "2", "-f", "s16le", "-"],
        check=True, capture_output=True,
    )
    return len(result.stdout) // 4


def decode_audio(path):
    """Return mono 16 kHz float samples for the offline speech/pitch models."""
    import imageio_ffmpeg
    import numpy as np
    import torch

    result = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-i", str(path),
         "-ar", "16000", "-ac", "1", "-f", "f32le", "-"],
        check=True, capture_output=True,
    )
    return torch.from_numpy(np.frombuffer(result.stdout, dtype="<f4").copy())

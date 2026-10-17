"""Download one video as MP3 into the project's local-only audio directory."""

import argparse
from pathlib import Path

import imageio_ffmpeg
from yt_dlp import YoutubeDL


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Video URL (playlists are disabled)")
    args = parser.parse_args()
    output = Path(__file__).resolve().parents[2] / "ml/data/downloads"
    output.mkdir(parents=True, exist_ok=True)
    with YoutubeDL({
        "format": "bestaudio/best",
        "noplaylist": True,
        "outtmpl": str(output / "%(id)s.%(ext)s"),
        "ffmpeg_location": imageio_ffmpeg.get_ffmpeg_exe(),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
    }) as downloader:
        downloader.download([args.url])


if __name__ == "__main__":
    main()

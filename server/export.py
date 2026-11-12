"""Export presets: turn a downloaded MP4 clip into a GIF, an MP3, a small MP4 or a 9:16 MP4.

Each preset is one ffmpeg command. Presets that re-encode the video are limited to short
clips, so they finish inside Vercel's time limit.
"""

import subprocess
from pathlib import Path

from .clipper import ClipError

MAX_SECONDS = 60  # longest clip a re-encoding preset accepts
SMALL_BYTES = 10 * 2**20  # "Small" targets Discord's and WhatsApp's 10 MB limits
AUDIO_KBPS = 96


def _gif(seconds: float) -> list[str]:
    # Two passes over the frames in one filter: build a 256-colour palette from the clip,
    # then map every frame onto it. That gives far cleaner colours than ffmpeg's default.
    return [
        "-an",
        "-vf",
        "fps=12,scale=480:-2:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse",
    ]


def _mp3(seconds: float) -> list[str]:
    return ["-vn", "-c:a", "libmp3lame", "-q:a", "2"]


def _small(seconds: float) -> list[str]:
    # Pick the video bitrate that makes the whole file land just under the target size.
    total_kbps = SMALL_BYTES * 8 / 1000 / seconds * 0.95  # 5% headroom for the container
    video_kbps = max(int(total_kbps - AUDIO_KBPS), 100)
    return [
        "-vf", "scale=-2:'min(720,ih)'",
        "-c:v", "libx264", "-preset", "veryfast",
        "-b:v", f"{video_kbps}k", "-maxrate", f"{video_kbps}k", "-bufsize", f"{video_kbps * 2}k",
        "-c:a", "aac", "-b:a", f"{AUDIO_KBPS}k", "-movflags", "+faststart",
    ]  # fmt: skip


def _vertical(seconds: float) -> list[str]:
    # Keep the centre of the frame at 9:16, the shape Reels, Shorts and TikTok use.
    return [
        "-vf", "crop='min(iw,ih*9/16)':ih,scale=-2:'min(1280,ih)'",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", f"{AUDIO_KBPS}k", "-movflags", "+faststart",
    ]  # fmt: skip


# name: (file extension, MIME type, ffmpeg arguments for a clip of that many seconds)
PRESETS = {
    "mp4": ("mp4", "video/mp4", None),  # the download as it is, no re-encoding
    "gif": ("gif", "image/gif", _gif),
    "mp3": ("mp3", "audio/mpeg", _mp3),
    "small": ("mp4", "video/mp4", _small),
    "vertical": ("mp4", "video/mp4", _vertical),
}


def export(clip: Path, preset: str, seconds: float) -> Path:
    """Convert the clip with a preset. Returns the new file, next to the original."""
    extension, _, arguments = PRESETS[preset]
    if arguments is None or (preset == "small" and clip.stat().st_size <= SMALL_BYTES):
        return clip  # plain MP4, or a clip that's already small enough
    if preset != "mp3" and seconds > MAX_SECONDS:
        raise ClipError(f"GIF, Small and Vertical work on clips up to {MAX_SECONDS} seconds.")
    output = clip.with_name(f"export.{extension}")
    command = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(clip), *arguments(seconds)]
    result = subprocess.run([*command, str(output)], capture_output=True, text=True)
    if result.returncode != 0:
        raise ClipError("Converting the clip failed. Try a shorter clip or plain MP4.", 500)
    return output

"""The clipper: look up a video link, then download it, trimmed to a time range."""

import os
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

import imageio_ffmpeg
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, sanitize_filename


def _ffmpeg_on_path():
    """Vercel has no ffmpeg installed, so use the copy bundled with the imageio-ffmpeg package.

    yt-dlp looks for a program named "ffmpeg" on PATH before it trims, so link it in under
    that name.
    """
    if shutil.which("ffmpeg"):
        return
    folder = Path(tempfile.gettempdir(), "clipgrab-bin")
    folder.mkdir(exist_ok=True)
    link = folder / "ffmpeg"
    if not link.exists():
        link.symlink_to(imageio_ffmpeg.get_ffmpeg_exe())
    os.environ["PATH"] = f"{folder}{os.pathsep}{os.environ.get('PATH', '')}"


_ffmpeg_on_path()

# The platforms ClipGrab supports, by domain. Others (YouTube, Instagram, Reddit, …)
# block or demand a login from cloud servers, so they're refused up front.
SITES = {"x.com": "X", "twitter.com": "X", "twitch.tv": "Twitch", "streamable.com": "Streamable"}

OPTIONS = {
    "quiet": True,
    "no_warnings": True,
    "noprogress": True,
    "noplaylist": True,
    "playlist_items": "1",  # a post with several videos: take the first
    "cachedir": False,  # Vercel's filesystem is read-only outside /tmp
    # Single-file MP4s over HTTPS (all three sites offer them). X's other formats are
    # separate HLS audio and video streams, which yt-dlp can't trim from a mid-point.
    "format": "b[protocol=https]/b",
    "merge_output_format": "mp4",
    "max_filesize": 450 * 2**20,  # Vercel functions get 512 MB of /tmp
}


class ClipError(Exception):
    """An error with a message for the user and the HTTP status to send it with."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message, self.status = message, status


def platform(url: str) -> str:
    """The supported platform a link belongs to, e.g. "X". Raises ClipError otherwise."""
    host = (urlsplit(url).hostname or "").lower()
    for domain, name in SITES.items():
        if host == domain or host.endswith("." + domain):
            return name
    raise ClipError("ClipGrab works with links from X, Twitch and Streamable.")


def probe(url: str) -> dict:
    """Title, uploader, thumbnail and length of the video at a link, without downloading it."""
    info = _first(_run(url, {}, download=False))
    return {
        "platform": platform(url),
        "title": info.get("title"),
        "uploader": info.get("uploader"),
        "thumbnail": info.get("thumbnail"),
        "duration": info.get("duration"),
    }


def fetch(url: str, start: float | None = None, end: float | None = None) -> tuple[Path, str]:
    """Download the video into a new temp folder, trimmed to start/end (in seconds).

    Returns the file and a filename for the user. The caller deletes the folder.
    """
    folder = Path(tempfile.mkdtemp(prefix="clipgrab-"))
    options = {"outtmpl": str(folder / "video.%(ext)s")}
    if start is not None or end is not None:
        options["download_ranges"] = lambda info, _: [_section(info, start, end)]
    try:
        info = _first(_run(url, options, download=True))
        file = next(folder.glob("video.*"), None)
        if not file:
            raise ClipError("No file came out of that. It may be over 450 MB.", 502)
        title = sanitize_filename(info.get("title") or "clip")[:80].strip(" .")
        return file, f"{title}.mp4"
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise


def _section(info: dict, start: float | None, end: float | None) -> dict:
    duration = info.get("duration") or float("inf")
    if start is not None and start >= duration:
        raise ClipError("The start time is past the end of the video.")
    return {"start_time": start or 0, "end_time": min(end or duration, duration)}


def _run(url: str, options: dict, download: bool) -> dict:
    platform(url)
    try:
        with YoutubeDL({**OPTIONS, **options}) as ydl:
            return ydl.extract_info(url, download=download)
    except DownloadError as error:
        raise _explain(str(error)) from None


def _first(info: dict) -> dict:
    """yt-dlp returns a playlist for posts with several videos; use the first one."""
    entries = [entry for entry in info.get("entries") or [] if entry]
    return entries[0] if entries else info


# (pattern in yt-dlp's error, message for the user, HTTP status), checked in order
ERRORS = [
    (r"no video could be found|no video formats", "There's no video in that post.", 404),
    (r"\b404\b|not found|unavailable|does not exist|removed|suspended",
     "That video doesn't exist anymore, or the account is private.", 404),
    (r"log ?in|sign in|cookies|private|protected",
     "That video is only visible to logged-in users.", 403),
]  # fmt: skip


def _explain(raw: str) -> ClipError:
    """Turn a raw yt-dlp error into a short message (yt-dlp already logs the full one)."""
    for pattern, message, status in ERRORS:
        if re.search(pattern, raw, re.I):
            return ClipError(message, status)
    return ClipError("Couldn't download that video. Check the link and try again.", 502)

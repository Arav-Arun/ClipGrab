"""yt-dlp engine: look up what a link holds, then download (and trim) one item of it."""

import ipaddress
import re
import shutil
import socket
import tempfile
from contextlib import contextmanager
from http.cookiejar import Cookie
from pathlib import Path
from urllib.parse import urlsplit

import imageio_ffmpeg
from yt_dlp import YoutubeDL
from yt_dlp.extractor.instagram import InstagramIE, InstagramStoryIE
from yt_dlp.postprocessor import FFmpegPostProcessor
from yt_dlp.utils import DownloadError, format_field, sanitize_filename, traverse_obj

OPTIONS = {
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "playlistend": 50,
    "cachedir": False,  # read-only filesystem on Vercel
    # Best quality up to 1080p, preferring H.264 + AAC so clips play everywhere.
    "format": "bv*+ba/b",
    "format_sort": ["res:1080", "vcodec:h264", "acodec:aac"],
    "merge_output_format": "mp4/mkv",
    "max_filesize": 450 * 2**20,  # Vercel's /tmp holds 512 MB
}
NAMES = {"youtube": "YouTube", "twitter": "X", "tiktok": "TikTok", "soundcloud": "SoundCloud"}
ERRORS = (  # (code, HTTP status, pattern in yt-dlp's message, message for the user)
    ("auth_required", 401, r"--cookies|log ?in|sign in|private|not a bot",
     "{site} only shows this to logged-in users."),
    ("auth_required", 401, r"\b429\b|too many requests",
     "{site} is rate-limiting ClipGrab's server. Your login usually gets past it."),
    ("unsupported", 422, r"unsupported url|no video", "No video or photo found at this link."),
    ("not_found", 404, r"\b404\b|unavailable|does not exist|removed", None),
)  # fmt: skip
NOISE = re.compile(  # yt-dlp's "ERROR: [site] id:" prefix and trailing hints
    r"^ERROR: (\[.+?\] )?([\w-]+: )?|\s*(Use --cookies|See https?:|please report|\(caused by).*",
    re.S,
)


class ClipError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


class _Photos:
    """yt-dlp skips Instagram photos (photo stories vanish), so expose each as a one-file format."""

    def _extract_product_media(self, media):
        info = super()._extract_product_media(media)
        photo = traverse_obj(media, ("image_versions2", "candidates", 0, "url"))
        if photo and not info.get("formats"):
            info["formats"] = [{"url": photo, "ext": "jpg", "format_id": "photo"}]
            info["title"] = format_field(
                media, [("user", "username")], "Photo by %s", default="Photo"
            )
        return info


class InstagramPhotosIE(_Photos, InstagramIE): ...


class InstagramStoryPhotosIE(_Photos, InstagramStoryIE): ...


def is_photo(info: dict) -> bool:
    return all(f.get("ext") == "jpg" for f in info.get("formats") or [info])


def probe(url: str, cookies=None) -> dict:
    """What a link holds: its title, platform and items (a story or carousel holds several)."""
    with _ytdlp(url, cookies, extract_flat="in_playlist") as ydl:
        info = ydl.extract_info(url, download=False)
    entries = info.get("entries") if "entries" in info else [info]
    items = [
        {
            "index": index,
            "kind": "image" if is_photo(entry) else "video",
            "thumbnail": entry.get("thumbnail") or traverse_obj(entry, ("thumbnails", -1, "url")),
            "duration": entry.get("duration"),
        }
        for index, entry in enumerate(entries, 1)
        if entry
    ]
    if not items:
        raise ClipError("no_media", "There's nothing to download here right now.", 404)
    return {
        "title": info.get("title"),
        "uploader": traverse_obj([info, *entries], (..., "uploader", {str}, any)),
        "platform": _platform(info.get("extractor"), url),
        "thumbnail": info.get("thumbnail") or items[0]["thumbnail"],
        "items": items,
    }


def fetch(url: str, item=1, start=None, end=None, cookies=None) -> tuple[Path, str]:
    """Download one item, trimmed to start/end, into a temp folder. Returns (file, nice name)."""
    folder = Path(tempfile.mkdtemp(prefix="clipgrab-"))
    options = {"playlist_items": str(item), "outtmpl": str(folder / "media.%(ext)s")}
    if start or end:
        options["download_ranges"] = lambda info, _: _section(info, start, end)
    try:
        with _ytdlp(url, cookies, **options) as ydl:
            info = ydl.extract_info(url, download=True)
        entry = next((e for e in info.get("entries") or [] if e), info)
        if not (file := next(folder.glob("media.*"), None)):
            raise ClipError("failed", "No file came out of that. It may be over 450 MB.", 502)
        return file, sanitize_filename(entry.get("title") or "clip")[:80].strip(" .") + file.suffix
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise


def _section(info, start, end):
    if is_photo(info):
        return [{}]  # photos are never trimmed
    if start and start >= (info.get("duration") or float("inf")):
        raise ClipError("bad_range", "The start time is past the end of the video.")
    return [{"start_time": start or 0, "end_time": end or float("inf")}]


@contextmanager
def _ytdlp(url, cookies, **options):
    _check_public(url)
    # yt-dlp checks for ffmpeg here (not via its options) before trimming; Vercel has none on PATH.
    FFmpegPostProcessor._ffmpeg_location.set(imageio_ffmpeg.get_ffmpeg_exe())
    ydl = YoutubeDL({**OPTIONS, **options}, auto_init=False)
    for extractor in (InstagramPhotosIE, InstagramStoryPhotosIE):  # first, so they win
        ydl.add_info_extractor(extractor())
    ydl.add_default_info_extractors()
    for c in cookies or []:  # the user's login, sent by the extension; kept in memory only
        dot = c.domain.startswith(".")
        ydl.cookiejar.set_cookie(Cookie(
            version=0, name=c.name, value=c.value, port=None, port_specified=False,
            domain=c.domain, domain_specified=dot, domain_initial_dot=dot, path=c.path,
            path_specified=True, secure=c.secure, expires=int(c.expirationDate) or None,
            discard=False, comment=None, comment_url=None, rest={},
        ))  # fmt: skip
    try:
        with ydl:
            yield ydl
    except DownloadError as error:
        raise _explain(str(error), url) from None


def _check_public(url):
    """Refuse links to private or internal addresses, so the server can't be turned on itself."""
    try:
        addresses = socket.getaddrinfo(urlsplit(url).hostname, None)
    except (socket.gaierror, UnicodeError):
        raise ClipError("invalid_url", "That link doesn't lead to a website.") from None
    if not all(ipaddress.ip_address(a[4][0].split("%")[0]).is_global for a in addresses):
        raise ClipError("invalid_url", "Links to private network addresses aren't allowed.")


def _platform(extractor, url):
    key = (extractor or "generic").split(":")[0].lower()
    if key == "generic":
        return urlsplit(url).hostname.removeprefix("www.")
    return NAMES.get(key, key.capitalize())


def _explain(raw, url):
    """Turn a raw yt-dlp error into a short message and a code clients can act on."""
    code, status, _, message = next(
        (kind for kind in ERRORS if re.search(kind[2], raw, re.I)), ("failed", 502, "", None)
    )
    if message:
        tag = re.search(r"\[([^\]]+)\]", raw)
        return ClipError(code, message.format(site=_platform(tag and tag[1], url)), status)
    detail = NOISE.sub("", raw).strip(" ;,.")
    return ClipError(code, f"{detail}.", status)

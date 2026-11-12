import subprocess
from pathlib import Path
from zipfile import ZipFile

import imageio_ffmpeg
import pytest
from fastapi.testclient import TestClient

from server import engine, main
from server.engine import ClipError

client = TestClient(main.app)


def test_request_parsing():
    clip = main.Clip(url=" x.com/nasa/status/1 ", start="1:30", end="0:01:45.5")
    assert (clip.url, clip.start, clip.end) == ("https://x.com/nasa/status/1", 90, 105.5)
    for bad, error in [
        ({"url": "ftp://x.com/a"}, "Paste a full link"),
        ({"url": "x.com/a", "start": "soon"}, "isn't a time"),
        ({"url": "x.com/a", "start": "1:00", "end": "30"}, "End time must be after"),
    ]:
        assert error in client.post("/api/download", json=bad).json()["error"]


@pytest.mark.parametrize(
    ("url", "name"),
    [
        ("https://x.com/nasa/status/1", "X"),
        ("https://mobile.twitter.com/nasa/status/1", "X"),
        ("https://clips.twitch.tv/SomeClip", "Twitch"),
        ("https://www.twitch.tv/user/clip/SomeClip", "Twitch"),
        ("https://streamable.com/dnd1", "Streamable"),
    ],
)
def test_supported_platforms(url, name):
    assert engine.platform(url) == name


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://notx.com/status/1",  # ends in "x.com" but isn't X
        "https://x.com.evil.example/status/1",
        "http://127.0.0.1:8000/",
    ],
)
def test_other_sites_are_refused(url):
    with pytest.raises(ClipError, match="works with links from X, Twitch and Streamable"):
        engine.platform(url)
    assert client.post("/api/info", json={"url": url}).status_code == 400


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("ERROR: [twitter] 1598765421226651648: No video could be found in this tweet",
         "There's no video in that post."),
        ("ERROR: [twitter] 852138619213144067: Suspended",
         "That video doesn't exist anymore, or the account is private."),
        ("ERROR: [Streamable] abc: Unable to download JSON metadata: HTTP Error 404: Not Found",
         "That video doesn't exist anymore, or the account is private."),
        ("ERROR: [twitter] 1: NSFW tweet requires authentication. Use --cookies",
         "That video is only visible to logged-in users."),
        ("ERROR: [twitch:clips] x: Unexpected response",
         "Couldn't download that video. Check the link and try again."),
    ],
)  # fmt: skip
def test_errors_are_explained(raw, message):
    assert engine._explain(raw).message == message


def test_download_streams_the_file_then_cleans_up(monkeypatch, tmp_path):
    def fake_fetch(url, start, end):
        assert (url, start, end) == ("https://x.com/a/status/1", 5, 20)
        (tmp_path / "video.mp4").write_bytes(b"video")
        return tmp_path / "video.mp4", "Café clip.mp4"

    monkeypatch.setattr(main, "fetch", fake_fetch)
    response = client.post(
        "/api/download", json={"url": "https://x.com/a/status/1", "start": "0:05", "end": 20}
    )
    assert response.content == b"video" and response.headers["content-type"] == "video/mp4"
    assert "filename*=utf-8''Caf%C3%A9%20clip.mp4" in response.headers["content-disposition"]
    assert not tmp_path.exists()


def test_engine_errors_become_json(monkeypatch):
    def fake_probe(url):
        raise ClipError("There's no video in that post.", 404)

    monkeypatch.setattr(main, "probe", fake_probe)
    response = client.post("/api/info", json={"url": "https://x.com/a/status/1"})
    assert response.status_code == 404
    assert response.json() == {"error": "There's no video in that post."}


def test_extension_zip_matches_its_source():
    root = Path(__file__).parents[1]
    with ZipFile(root / "public/extension/clipgrab-extension.zip") as archive:
        assert sorted(archive.namelist()) == sorted(
            f.relative_to(root / "extension").as_posix()
            for f in (root / "extension").rglob("*")
            if f.is_file() and not f.name.startswith(".")
        ), "Rebuild the zip: files were added or removed"
        for name in archive.namelist():
            assert archive.read(name) == (root / "extension" / name).read_bytes(), (
                f"Rebuild the zip: {name} changed"
            )


# Real downloads from each platform. They need the internet, so they're skipped unless
# you run `uv run pytest -m live`.
LIVE = {
    "X": "https://twitter.com/i/web/status/910031516746514432",  # 47 s
    "Twitch": "https://clips.twitch.tv/FaintLightGullWholeWheat",  # 32 s
    "Streamable": "https://streamable.com/dnd1",  # 61 s
}


def _duration(path: Path) -> float:
    """The length of a video file in seconds, read from ffmpeg's output."""
    output = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-i", str(path)], capture_output=True, text=True
    ).stderr
    hours, minutes, seconds = output.split("Duration: ")[1].split(",")[0].split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


@pytest.mark.live
@pytest.mark.parametrize("name", LIVE)
def test_live_clip_has_the_requested_length(name):
    path, filename = engine.fetch(LIVE[name], start=5, end=15)  # starts mid-video on purpose
    try:
        assert filename.endswith(".mp4")
        assert _duration(path) == pytest.approx(10, abs=0.5)
    finally:
        path.unlink()
        path.parent.rmdir()

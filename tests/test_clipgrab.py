from pathlib import Path
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from yt_dlp.downloader.external import FFmpegFD

from server import engine, main
from server.engine import ClipError

client = TestClient(main.app)


def test_request_parsing():
    clip = main.Clip(url=" instagram.com/stories/nasa/ ", start="1:30", end="0:01:45.5")
    assert (clip.url, clip.start, clip.end) == ("https://instagram.com/stories/nasa/", 90, 105.5)
    for bad, error in [
        ({"url": "ftp://x.com/a"}, "Paste a full link"),
        ({"url": "x.com/a", "start": "soon"}, "isn't a time"),
        ({"url": "x.com/a", "start": "1:00", "end": "30"}, "End time must be after"),
    ]:
        assert error in client.post("/api/info", json=bad).json()["error"]


@pytest.mark.parametrize(
    ("raw", "code", "message"),
    [
        ("ERROR: [instagram:story] This content is unreachable. Use --cookies-from-browser or "
         "--cookies for the authentication. See https://github.com/yt-dlp/yt-dlp/wiki/FAQ",
         "auth_required", "Instagram only shows this to logged-in users."),
        ("ERROR: [youtube] dQw4w9WgXcQ: Sign in to confirm you're not a bot",
         "auth_required", "YouTube only shows this to logged-in users."),
        ("ERROR: [instagram:story] kjsce_codecell: Unable to download webpage: HTTP Error 429: "
         "Too Many Requests (caused by <HTTPError 429: Too Many Requests>)", "auth_required",
         "Instagram is rate-limiting ClipGrab's server. Your login usually gets past it."),
        ("ERROR: [generic] Unsupported URL: https://example.com/",
         "unsupported", "No video or photo found at this link."),
        ("ERROR: [youtube] abc: Video unavailable. This video has been removed by the uploader",
         "not_found", "Video unavailable. This video has been removed by the uploader."),
        ("ERROR: [TikTok] 671: Unexpected response {x}; please report this issue on https://...",
         "failed", "Unexpected response {x}."),
    ],
)  # fmt: skip
def test_errors_are_explained(raw, code, message):
    error = engine._explain(raw, "https://www.instagram.com/stories/kjsce_codecell/")
    assert (error.code, error.message) == (code, message)


def test_instagram_photos_become_downloadable():
    photo = {
        "pk": "3700000000000000001",
        "user": {"username": "kjsce_codecell"},
        "image_versions2": {"candidates": [{"url": "https://cdn.example/big.jpg", "width": 1080}]},
    }
    info = engine.InstagramStoryPhotosIE()._extract_product(photo)
    assert info["formats"] == [
        {"url": "https://cdn.example/big.jpg", "ext": "jpg", "format_id": "photo"}
    ]
    assert info["title"] == "Photo by kjsce_codecell" and engine.is_photo(info)


def test_private_addresses_are_refused():
    for url in ["http://127.0.0.1:8000/", "http://169.254.169.254/latest", "http://[::1]/"]:
        with pytest.raises(ClipError, match="private network"):
            engine._check_public(url)


def test_login_cookies_are_used_for_the_site(monkeypatch):
    monkeypatch.setattr(engine, "_check_public", lambda url: None)
    cookies = [main.Cookie(name="sessionid", value="s3cret", domain=".instagram.com", secure=True)]
    with engine._ytdlp("https://www.instagram.com/stories/nasa/", cookies) as ydl:
        assert (
            ydl.cookiejar.get_cookie_header("https://www.instagram.com/api/v1/")
            == "sessionid=s3cret"
        )
        assert not ydl.cookiejar.get_cookie_header("https://example.com/")


def test_download_streams_the_file_then_cleans_up(monkeypatch, tmp_path):
    def fake_fetch(url, item, start, end, cookies):
        assert (url, item, start, end) == ("https://x.com/a/status/1", 2, 5, 20)
        (tmp_path / "media.mp4").write_bytes(b"video")
        return tmp_path / "media.mp4", "Café clip.mp4"

    monkeypatch.setattr(main, "fetch", fake_fetch)
    response = client.post(
        "/api/download",
        json={"url": "https://x.com/a/status/1", "item": 2, "start": "0:05", "end": 20},
    )
    assert response.content == b"video" and response.headers["content-type"] == "video/mp4"
    assert "filename*=utf-8''Caf%C3%A9%20clip.mp4" in response.headers["content-disposition"]
    assert not tmp_path.exists()


def test_extension_zip_matches_its_source():
    root = Path(__file__).parents[1]
    with ZipFile(root / "public/extension/clipgrab-extension.zip") as archive:
        for file in (root / "extension").rglob("[!.]*.*"):
            name = file.relative_to(root / "extension").as_posix()
            assert archive.read(name) == file.read_bytes(), f"Rebuild the zip, {name} changed"


def test_trimming_works_without_a_system_ffmpeg(monkeypatch):  # like on Vercel
    monkeypatch.setenv("PATH", "")
    monkeypatch.setattr(engine, "_check_public", lambda url: None)
    with engine._ytdlp("https://example.com/", None):
        assert FFmpegFD.available()


def test_engine_errors_become_json(monkeypatch):
    def fake_probe(url, cookies):
        raise ClipError("auth_required", "Instagram only shows this to logged-in users.", 401)

    monkeypatch.setattr(main, "probe", fake_probe)
    response = client.post("/api/info", json={"url": "https://instagram.com/stories/x/"})
    assert response.status_code == 401 and response.json()["code"] == "auth_required"

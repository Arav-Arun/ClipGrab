"""ClipGrab API. Vercel runs this as one function and serves public/ from its CDN."""

import re
import shutil
from typing import Annotated

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import AfterValidator, BaseModel, BeforeValidator, model_validator
from starlette.background import BackgroundTask
from yt_dlp.utils import parse_duration

from .engine import ClipError, fetch, probe

app = FastAPI(
    title="ClipGrab API", docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json"
)
# The Chrome extension calls the API from its own origin, so allow cross-origin requests.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _link(value: str) -> str:
    value = value.strip()
    if "://" not in value:
        value = f"https://{value}"
    if not re.match(r"^https?://[^\s/]+\S*$", value):
        raise ValueError("Paste a full link, like https://x.com/user/status/123")
    return value


def _seconds(value) -> float | None:
    """Accepts 90, "90", "1:30" or "0:01:30". Empty means no limit."""
    if value is None or str(value).strip() == "":
        return None
    seconds = parse_duration(str(value))
    if seconds is None:
        raise ValueError(f"“{value}” isn't a time. Use seconds or m:ss, like 1:30.")
    return seconds


class Link(BaseModel):
    url: Annotated[str, AfterValidator(_link)]


class Clip(Link):
    start: Annotated[float | None, BeforeValidator(_seconds)] = None
    end: Annotated[float | None, BeforeValidator(_seconds)] = None

    @model_validator(mode="after")
    def _start_before_end(self):
        if self.start is not None and self.end is not None and self.end <= self.start:
            raise ValueError("End time must be after the start time.")
        return self


@app.exception_handler(ClipError)
async def _clip_error(_, error: ClipError):
    return JSONResponse({"error": error.message}, error.status)


@app.exception_handler(RequestValidationError)
async def _invalid_request(_, error: RequestValidationError):
    message = error.errors()[0]["msg"].removeprefix("Value error, ")
    return JSONResponse({"error": message}, 422)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/info")
def info(link: Link):
    """Look a link up: platform, title, uploader, thumbnail and duration."""
    return probe(link.url)


@app.post("/api/download")
def download(clip: Clip):
    """Download the video, trimmed to start/end if given, then delete its temp folder."""
    path, name = fetch(clip.url, clip.start, clip.end)
    cleanup = BackgroundTask(shutil.rmtree, path.parent, ignore_errors=True)
    return FileResponse(path, media_type="video/mp4", filename=name, background=cleanup)

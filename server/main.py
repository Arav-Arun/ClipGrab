"""ClipGrab API. Vercel runs this as a single function; its CDN serves public/."""

import re
import shutil
from typing import Annotated

import yt_dlp
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import AfterValidator, BaseModel, BeforeValidator, Field, model_validator
from starlette.background import BackgroundTask
from yt_dlp.utils import parse_duration

from .engine import ClipError, fetch, probe

app = FastAPI(
    title="ClipGrab API", docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


def _link(value: str) -> str:
    value = value.strip() if "://" in value else f"https://{value.strip()}"
    if not re.match(r"^https?://[^\s/]+\S*$", value):
        raise ValueError("Paste a full link, like https://www.instagram.com/stories/…")
    return value


def _time(value) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    if (seconds := parse_duration(str(value))) is None:
        raise ValueError(f"“{value}” isn't a time. Use seconds or m:ss, like 1:30.")
    return seconds


class Cookie(BaseModel):  # the shape of chrome.cookies.Cookie
    name: str
    value: str
    domain: str
    path: str = "/"
    secure: bool = False
    expirationDate: float = 0


class Clip(BaseModel):
    url: Annotated[str, AfterValidator(_link)]
    item: int = Field(1, ge=1, le=50, description="Which item of a story or carousel")
    start: Annotated[float | None, BeforeValidator(_time)] = None
    end: Annotated[float | None, BeforeValidator(_time)] = None
    cookies: list[Cookie] | None = Field(None, description="The user's cookies for the site")

    @model_validator(mode="after")
    def _ordered(self):
        if self.start is not None and self.end is not None and self.end <= self.start:
            raise ValueError("End time must be after the start time.")
        return self


@app.exception_handler(ClipError)
async def _clip_error(_, error: ClipError):
    return JSONResponse({"error": error.message, "code": error.code}, error.status)


@app.exception_handler(RequestValidationError)
async def _invalid(_, error: RequestValidationError):
    message = error.errors()[0]["msg"].removeprefix("Value error, ")
    return JSONResponse({"error": message, "code": "invalid_request"}, 422)


@app.get("/api/health")
def health():
    return {"ok": True, "yt_dlp": yt_dlp.version.__version__}


@app.post("/api/info")
def info(clip: Clip):
    """Look up a link: title, platform and its items (each story, carousel photo, …)."""
    return probe(clip.url, clip.cookies)


@app.post("/api/download")
@app.post("/clip", include_in_schema=False)  # kept for copies of the v1 extension
def download(clip: Clip):
    """Download one item, trimmed to start/end if given. The file streams back."""
    path, name = fetch(clip.url, clip.item, clip.start, clip.end, clip.cookies)
    return FileResponse(path, filename=name, background=BackgroundTask(shutil.rmtree, path.parent))

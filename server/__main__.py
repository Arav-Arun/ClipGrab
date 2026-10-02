"""Run locally with `python -m server`, then open http://localhost:8000."""

import uvicorn
from fastapi.staticfiles import StaticFiles

from .main import app

app.mount("/", StaticFiles(directory="public", html=True))  # on Vercel, the CDN serves public/
uvicorn.run(app, port=8000)

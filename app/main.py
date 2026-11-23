from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="AI YouTube Clipper",
    description="A personal, cloud-hosted video clipping prototype.",
    version="0.2.0",
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class InspectRequest(BaseModel):
    url: HttpUrl


def is_supported_video_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"}


@app.get("/", response_class=HTMLResponse)
async def home() -> str:
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "app": "AI YouTube Clipper", "version": "0.2.0"}


@app.post("/api/inspect")
def inspect_video(request: InspectRequest) -> dict:
    url = str(request.url)
    if not is_supported_video_url(url):
        raise HTTPException(status_code=400, detail="Please enter a YouTube video URL.")

    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": 15,
        "retries": 1,
    }
    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=False)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail="Could not inspect this video. It may be private, unavailable, age-restricted, or temporarily blocked by YouTube.",
        ) from exc

    if not info:
        raise HTTPException(status_code=422, detail="No video information was returned.")

    subtitles = info.get("subtitles") or {}
    automatic = info.get("automatic_captions") or {}
    return {
        "title": info.get("title") or "Untitled video",
        "channel": info.get("channel") or info.get("uploader") or "Unknown channel",
        "duration_seconds": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "webpage_url": info.get("webpage_url") or url,
        "manual_captions_available": bool(subtitles),
        "automatic_captions_available": bool(automatic),
        "status": "inspected",
        "message": "Video details retrieved. Clip generation is the next development step.",
    }

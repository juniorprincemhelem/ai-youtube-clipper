from html import unescape
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
GEMINI_MODEL = "gemini-3.5-flash-lite"

app = FastAPI(
    title="AI YouTube Clipper",
    description="A personal, cloud-hosted video clipping prototype.",
    version="0.3.0",
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class InspectRequest(BaseModel):
    url: HttpUrl


def is_supported_video_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"}


def seconds_from_timestamp(value: str) -> float:
    parts = value.replace(",", ".").split(":")
    if len(parts) == 3:
        hours, minutes, seconds = parts
    elif len(parts) == 2:
        hours = 0
        minutes, seconds = parts
    else:
        raise ValueError("Invalid subtitle timestamp")
    return float(hours) * 3600 + float(minutes) * 60 + float(seconds)


def parse_vtt(content: str) -> list[dict]:
    segments = []
    lines = content.replace("\ufeff", "").splitlines()
    timestamp_pattern = re.compile(
        r"(?P<start>\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3})\s+-->\s+"
        r"(?P<end>\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3})"
    )
    for index, line in enumerate(lines):
        match = timestamp_pattern.search(line)
        if not match:
            continue
        text_lines = []
        for following in lines[index + 1:]:
            if not following.strip() or "-->" in following:
                break
            if following.strip().isdigit():
                continue
            cleaned = re.sub(r"<[^>]+>", "", following)
            cleaned = unescape(cleaned).strip()
            if cleaned:
                text_lines.append(cleaned)
        text = " ".join(text_lines)
        if not text:
            continue
        start = seconds_from_timestamp(match.group("start"))
        end = seconds_from_timestamp(match.group("end"))
        if segments and segments[-1]["text"].lower() == text.lower():
            continue
        segments.append({"start": round(start, 2), "end": round(end, 2), "text": text})
    return segments


def get_video_info(url: str) -> dict:
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": 15,
        "retries": 1,
    }
    with yt_dlp.YoutubeDL(options) as downloader:
        return downloader.extract_info(url, download=False)


def extract_english_transcript(url: str) -> list[dict]:
    with tempfile.TemporaryDirectory(prefix="clipper-") as temp_dir:
        output_template = str(Path(temp_dir) / "captions.%(ext)s")
        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["en", "en-US", "en-GB"],
            "subtitlesformat": "vtt/best",
            "outtmpl": output_template,
            "noplaylist": True,
            "socket_timeout": 20,
            "retries": 1,
        }
        with yt_dlp.YoutubeDL(options) as downloader:
            downloader.download([url])
        subtitle_files = list(Path(temp_dir).glob("*.vtt"))
        if not subtitle_files:
            subtitle_files = list(Path(temp_dir).glob("*"))
        for subtitle_file in subtitle_files:
            if subtitle_file.is_file() and subtitle_file.suffix.lower() in {".vtt", ".srt"}:
                segments = parse_vtt(subtitle_file.read_text(encoding="utf-8", errors="replace"))
                if segments:
                    return segments
    return []


def ask_gemini_for_clips(segments: list[dict], video_title: str, duration: int | None) -> list[dict]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="Gemini is not connected yet. Add GEMINI_API_KEY in Vercel Environment Variables and redeploy.")

    transcript = "\n".join(
        f"[{segment['start']:.2f}s - {segment['end']:.2f}s] {segment['text']}"
        for segment in segments
    )
    # Keep requests bounded on the free hosting tier.
    transcript = transcript[:85000]
    prompt = f"""
You are an expert short-form video editor. Analyze this timestamped transcript and find up to 5 genuinely engaging standalone clips for YouTube Shorts, TikTok, or Instagram Reels.
Video title: {video_title}
Full video duration in seconds: {duration if duration is not None else "unknown"}

Choose moments with a strong hook, surprising insight, useful takeaway, emotional turn, funny exchange, or compelling story. Avoid introductions, sponsor reads, repeated points, and fragments that need lots of missing context.
Each clip should normally be 20 to 60 seconds. Use only timestamps supported by the transcript. Start slightly before the hook and end after the thought is complete. Do not invent speech or timestamps.
Return ONLY valid JSON in this exact shape:
{{
  "clips": [
    {{
      "start_seconds": 12.5,
      "end_seconds": 48.0,
      "title": "Short compelling title",
      "hook": "The opening line or moment that grabs attention",
      "reason": "Why this section is likely to hold attention",
      "caption": "A short social caption",
      "hashtags": ["#shorts", "#topic"]
    }}
  ]
}}
Sort the strongest clip first. If no good clips exist, return an empty clips array.

TIMESTAMPED TRANSCRIPT:
{transcript}
"""
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
            "maxOutputTokens": 3500,
        },
    }
    request = Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with urlopen(request, timeout=45) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 429:
            raise HTTPException(status_code=429, detail="Gemini free-tier rate limit reached. Please wait a little and try again.") from exc
        if exc.code in {401, 403}:
            raise HTTPException(status_code=502, detail="Gemini rejected the API key. Check the GEMINI_API_KEY value in Vercel.") from exc
        raise HTTPException(status_code=502, detail=f"Gemini request failed (HTTP {exc.code}).") from exc
    except (URLError, TimeoutError) as exc:
        raise HTTPException(status_code=504, detail="Gemini took too long to respond. Please try again.") from exc

    try:
        text = result["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)
        clips = parsed.get("clips", [])
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail="Gemini returned an unreadable response. Please try again.") from exc

    valid_clips = []
    for clip in clips[:5]:
        try:
            start = max(0, float(clip["start_seconds"]))
            end = float(clip["end_seconds"])
            if end <= start or (duration is not None and start >= duration):
                continue
            if duration is not None:
                end = min(end, float(duration))
            valid_clips.append({
                "start_seconds": round(start, 2),
                "end_seconds": round(end, 2),
                "duration_seconds": round(end - start, 2),
                "title": str(clip.get("title", "Suggested clip"))[:120],
                "hook": str(clip.get("hook", ""))[:300],
                "reason": str(clip.get("reason", ""))[:500],
                "caption": str(clip.get("caption", ""))[:500],
                "hashtags": [str(tag)[:40] for tag in clip.get("hashtags", [])[:8]],
            })
        except (KeyError, TypeError, ValueError):
            continue
    return valid_clips


@app.get("/", response_class=HTMLResponse)
async def home() -> str:
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "app": "AI YouTube Clipper", "version": "0.3.0"}


@app.post("/api/inspect")
def inspect_video(request: InspectRequest) -> dict:
    url = str(request.url)
    if not is_supported_video_url(url):
        raise HTTPException(status_code=400, detail="Please enter a YouTube video URL.")

    try:
        info = get_video_info(url)
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
        "message": "Video details retrieved. You can now ask Gemini to find the best moments.",
    }


@app.post("/api/analyze")
def analyze_video(request: InspectRequest) -> dict:
    url = str(request.url)
    if not is_supported_video_url(url):
        raise HTTPException(status_code=400, detail="Please enter a YouTube video URL.")

    try:
        info = get_video_info(url)
        segments = extract_english_transcript(url)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail="Could not retrieve captions for this video. It may be unavailable or YouTube may be temporarily blocking caption access.",
        ) from exc

    if not segments:
        raise HTTPException(
            status_code=422,
            detail="No English captions were found. This first version needs English captions; audio transcription is a later feature.",
        )

    clips = ask_gemini_for_clips(
        segments,
        info.get("title") or "Untitled video",
        info.get("duration"),
    )
    return {
        "title": info.get("title") or "Untitled video",
        "transcript_segments": len(segments),
        "clips": clips,
        "model": GEMINI_MODEL,
        "message": "Gemini finished analyzing the transcript.",
    }

# AI YouTube Clipper

A local-first personal tool for finding and exporting short clips from videos you own or have permission to process.

## Zero-cost approach

- Python + FastAPI for the local interface
- FFmpeg for cutting and formatting clips
- yt-dlp for permitted public video downloads
- faster-whisper for local transcription
- No paid APIs or subscriptions

Video processing runs on your own computer. GitHub stores the source code only; it does not process or host your videos.

## Requirements

- Windows 10/11
- Python 3.10+
- FFmpeg installed and available on PATH

## Run locally

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000.

## Current status

Starter scaffold. Video intake, transcription, moment ranking and clip export will be added in stages.

Only process videos you own or have permission to use. Respect copyright and platform terms; do not bypass DRM or access controls.

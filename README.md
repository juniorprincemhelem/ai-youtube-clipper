# AI YouTube Clipper

A personal AI-assisted YouTube clipping project, starting with a cloud-hosted prototype.

## Current cloud prototype

- Vercel hosts the website and Python API.
- Paste a public YouTube video URL to inspect its title, channel, duration, thumbnail, and whether captions are available.
- The API uses yt-dlp metadata extraction with downloads disabled.
- The next stages are transcript retrieval, clip-moment suggestions, and short vertical exports.

## Deploy to Vercel (free Hobby plan)

1. Import `juniorprincemhelem/ai-youtube-clipper` into Vercel.
2. Keep the project root as the repository root.
3. Use the included `vercel.json`; no build command or environment variables are required for the current prototype.
4. Deploy, then open the generated Vercel URL.

The project is configured as a Python serverless function. Function duration, memory, bandwidth, and other plan limits apply. YouTube may also block automated access or require additional verification, so inspection is not guaranteed for every video.

## Run locally (optional)

Requirements: Windows 10/11 and Python 3.10+.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000.

## Planned features

1. Retrieve captions/transcripts where available.
2. Rank interesting sections and suggest clip start/end times.
3. Render vertical 9:16 clips with subtitles.
4. Add a local-processing fallback for jobs that exceed free serverless limits.

Only process videos you own or have permission to use. Respect copyright and platform terms; do not bypass DRM or access controls.

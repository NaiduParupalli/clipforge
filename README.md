# AI Video Splitter MVP

A local web app for uploading a video, splitting it into fixed-duration clips or AI-assisted speech highlights, and exporting vertical (9:16) or horizontal (16:9) MP4 clips.

## Requirements
- Python 3.10+
- Node.js 18+
- FFmpeg and ffprobe installed and available on PATH

### Install FFmpeg
- Ubuntu/Debian: `sudo apt update && sudo apt install ffmpeg`
- macOS: `brew install ffmpeg`
- Windows: install FFmpeg from https://ffmpeg.org/download.html and add its `bin` directory to PATH.

Verify:
```bash
ffmpeg -version
ffprobe -version
```

## Run the backend
```bash
cd backend
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell:
# .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

Optional AI transcription (downloads a Whisper model the first time it runs):
```bash
pip install faster-whisper
```
If `faster-whisper` is not installed or transcription fails, AI Highlights mode falls back to scene-change candidates and evenly spaced candidates, with a warning in the job result.

## Run the frontend (new terminal)
```bash
cd frontend
npm install
npm run dev
```
Open the URL shown by Vite (usually http://localhost:5173).

## MVP workflow
1. Upload an MP4, MOV, MKV, or WebM video, or switch to YouTube Link and paste an eligible video URL.
2. Choose Fixed duration or AI Highlights.
3. Choose vertical Shorts or horizontal clips.
4. Click Process video.
5. Preview and download clips, or download all as ZIP.

## Notes and limitations
- Files are stored locally in `backend/data/`; this is a development MVP, not production-hardened.
- AI Highlights is heuristic: it uses speech segment length/text features when Whisper is available. It cannot guarantee viral clips.
- Vertical output uses a centered crop. Face/subject tracking is planned for a later version.
- For best compatibility, use MP4/H.264 sources. Processing speed depends on video length and your computer.
- YouTube URL support uses yt-dlp. Download availability depends on video access, platform changes, and applicable terms; use only videos you own or have permission to process.
- Do not upload copyrighted or private videos unless you have permission.
- For public deployment, add authentication, upload limits, background job workers, storage lifecycle cleanup, rate limiting, and stronger file validation.

## Cloud deployment
See `DEPLOYMENT.md` for Docker-based Ubuntu VPS deployment and PWA instructions.

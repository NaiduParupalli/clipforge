import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent
DATA = Path(os.getenv("DATA_DIR", str(ROOT / "data")))
UPLOADS = DATA / "uploads"
JOBS = DATA / "jobs"
for p in (UPLOADS, JOBS):
    p.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="AI Video Splitter API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB local MVP limit
jobs_lock = threading.Lock()
job_states = {}

class ProcessRequest(BaseModel):
    job_id: str
    mode: str = "fixed"          # fixed | highlights
    output_format: str = "vertical"  # vertical | horizontal
    clip_seconds: int = 60
    max_highlights: int = 8

def run_cmd(args, timeout=None):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "Command failed")[-3000:])
    return result.stdout

def ffmpeg_available():
    return shutil.which("ffmpeg") and shutil.which("ffprobe")

def probe_duration(path: Path) -> float:
    raw = run_cmd([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path)
    ], timeout=60).strip()
    duration = float(raw)
    if duration <= 0:
        raise ValueError("Could not determine a valid video duration.")
    return duration

def update_job(job_id, **updates):
    with jobs_lock:
        state = job_states.setdefault(job_id, {})
        state.update(updates)

def safe_job(job_id):
    if not re.fullmatch(r"[a-f0-9]{32}", job_id or ""):
        raise HTTPException(status_code=400, detail="Invalid job ID.")
    with jobs_lock:
        state = job_states.get(job_id)
    if not state:
        raise HTTPException(status_code=404, detail="Job not found. Upload the video again.")
    return state

def speech_highlights(video_path: Path, duration: float, max_highlights: int):
    """
    Optional local faster-whisper transcription. Picks candidate windows around
    longer/expressive speech segments. This is heuristic, not semantic virality prediction.
    """
    try:
        from faster_whisper import WhisperModel
    except Exception:
        return [], "faster-whisper is not installed; used fallback highlight candidates."

    try:
        model_name = os.getenv("WHISPER_MODEL", "small")
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
        segments, _info = model.transcribe(str(video_path), vad_filter=True, beam_size=3)
        candidates = []
        for seg in segments:
            text = (seg.text or "").strip()
            start, end = max(0.0, float(seg.start)), min(duration, float(seg.end))
            seg_len = end - start
            if seg_len < 2.0 or not text:
                continue
            # Longer speech and emphasis/punctuation are weak candidate signals.
            emphasis = sum(text.lower().count(w) for w in
                           ["why", "how", "secret", "mistake", "important", "amazing", "but", "because"])
            punctuation = text.count("?") + text.count("!")
            score = min(seg_len, 18) + min(len(text) / 35, 5) + emphasis * 1.5 + punctuation * 0.8
            clip_start = max(0.0, start - 4.0)
            clip_end = min(duration, max(end + 4.0, clip_start + 15.0))
            if clip_end - clip_start >= 8:
                candidates.append({"start": clip_start, "end": clip_end, "score": score, "text": text})
        candidates.sort(key=lambda x: x["score"], reverse=True)
        chosen = []
        for cand in candidates:
            if all(cand["end"] <= old["start"] or cand["start"] >= old["end"] for old in chosen):
                chosen.append(cand)
            if len(chosen) >= max_highlights:
                break
        chosen.sort(key=lambda x: x["start"])
        return chosen, None
    except Exception as exc:
        return [], f"Whisper transcription failed ({str(exc)[:180]}); used fallback highlight candidates."

def fallback_highlights(video_path: Path, duration: float, max_highlights: int):
    """Try scene-change timestamps; fall back to evenly spaced windows."""
    candidates = []
    try:
        # Scene detection is intentionally bounded to avoid excessive work.
        output = run_cmd([
            "ffmpeg", "-hide_banner", "-i", str(video_path), "-vf",
            "select='gt(scene,0.32)',showinfo", "-an", "-f", "null", "-"
        ], timeout=300)
        # showinfo is generally on stderr, so rerun without relying on stdout:
        proc = subprocess.run([
            "ffmpeg", "-hide_banner", "-i", str(video_path), "-vf",
            "select='gt(scene,0.32)',showinfo", "-an", "-f", "null", "-"
        ], capture_output=True, text=True, timeout=300)
        for match in re.finditer(r"pts_time:([0-9.]+)", proc.stderr):
            t = float(match.group(1))
            start = max(0.0, t - 5.0)
            end = min(duration, start + min(30.0, duration))
            if end - start >= 8:
                candidates.append({"start": start, "end": end, "score": 1.0, "text": "Scene change"})
    except Exception:
        pass

    if not candidates:
        window = min(30.0, max(8.0, duration / max(1, max_highlights)))
        if duration <= window:
            candidates = [{"start": 0.0, "end": duration, "score": 1.0, "text": "Video overview"}]
        else:
            count = min(max_highlights, max(1, int(duration // window)))
            for i in range(count):
                start = max(0.0, min(duration - window, (i + 0.5) * duration / count - window / 2))
                candidates.append({"start": start, "end": start + window, "score": 1.0, "text": "Auto-selected segment"})
    # Remove overlapping candidates and cap count.
    chosen = []
    for cand in sorted(candidates, key=lambda x: x.get("score", 0), reverse=True):
        if all(cand["end"] <= old["start"] or cand["start"] >= old["end"] for old in chosen):
            chosen.append(cand)
        if len(chosen) >= max_highlights:
            break
    return sorted(chosen, key=lambda x: x["start"])

def export_clip(source: Path, out_path: Path, start: float, end: float, output_format: str):
    duration = max(0.1, end - start)
    if output_format == "vertical":
        # Center crop to 9:16; keeps output vertical, but does not track faces.
        vf = "scale=-2:1920:force_original_aspect_ratio=increase,crop=1080:1920"
    else:
        # Center crop to 16:9 landscape.
        vf = "scale=1920:-2:force_original_aspect_ratio=increase,crop=1920:1080"
    run_cmd([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{start:.3f}", "-i", str(source), "-t", f"{duration:.3f}",
        "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
        "-avoid_negative_ts", "make_zero", str(out_path)
    ], timeout=max(180, int(duration * 5)))

def process_job(req: ProcessRequest):
    state = safe_job(req.job_id)
    source = Path(state["source_path"])
    out_dir = JOBS / req.job_id / "clips"
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        if not ffmpeg_available():
            raise RuntimeError("FFmpeg/ffprobe not found. Install FFmpeg and restart the backend.")
        duration = probe_duration(source)
        clips = []
        warning = None

        if req.mode == "fixed":
            step = max(5, min(3600, int(req.clip_seconds)))
            windows = []
            start = 0.0
            while start < duration:
                end = min(duration, start + step)
                if end - start >= 0.5:
                    windows.append({"start": start, "end": end, "text": "Fixed-duration clip"})
                start = end
        else:
            windows, warning = speech_highlights(source, duration, max(1, min(20, req.max_highlights)))
            if not windows:
                windows = fallback_highlights(source, duration, max(1, min(20, req.max_highlights)))
                warning = warning or "Used scene-change/evenly-spaced fallback; install faster-whisper for speech-assisted highlights."

        total = len(windows)
        if not total:
            raise RuntimeError("No clips could be created from this video.")
        update_job(req.job_id, status="processing", progress=5, message=f"Preparing {total} clips", warning=warning)

        for idx, window in enumerate(windows, start=1):
            start, end = float(window["start"]), float(window["end"])
            filename = f"clip_{idx:03d}_{int(start)}s.mp4"
            out_path = out_dir / filename
            export_clip(source, out_path, start, end, req.output_format)
            clips.append({
                "id": idx,
                "filename": filename,
                "start": round(start, 2),
                "end": round(end, 2),
                "duration": round(end - start, 2),
                "text": window.get("text", ""),
                "url": f"/api/jobs/{req.job_id}/clips/{filename}",
            })
            update_job(req.job_id, progress=5 + int(90 * idx / total), message=f"Exported clip {idx} of {total}")

        zip_path = JOBS / req.job_id / "clips.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for clip in clips:
                zf.write(out_dir / clip["filename"], arcname=clip["filename"])
        update_job(req.job_id, status="completed", progress=100, message="Processing complete",
                   clips=clips, zip_url=f"/api/jobs/{req.job_id}/download-all", warning=warning,
                   output_format=req.output_format, mode=req.mode, duration=round(duration, 2))
    except Exception as exc:
        update_job(req.job_id, status="failed", progress=0, message=str(exc), error=str(exc))

@app.get("/api/health")
def health():
    return {"status": "ok", "ffmpeg_available": bool(ffmpeg_available())}

@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...)):
    original_name = file.filename or "video.mp4"
    suffix = Path(original_name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
    job_id = uuid.uuid4().hex
    upload_dir = UPLOADS / job_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / f"source{suffix}"
    size = 0
    try:
        with target.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Video exceeds the 2 GB MVP upload limit.")
                out.write(chunk)
    except Exception:
        shutil.rmtree(upload_dir, ignore_errors=True)
        raise
    finally:
        await file.close()
    if size == 0:
        shutil.rmtree(upload_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    try:
        if not ffmpeg_available():
            raise HTTPException(status_code=500, detail="FFmpeg/ffprobe not installed. See README.md.")
        duration = probe_duration(target)
    except HTTPException:
        raise
    except Exception as exc:
        shutil.rmtree(upload_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=f"Could not read this video: {str(exc)[:250]}")
    with jobs_lock:
        job_states[job_id] = {
            "job_id": job_id, "source_path": str(target), "filename": original_name,
            "size_bytes": size, "duration": round(duration, 2), "status": "uploaded",
            "progress": 0, "message": "Video uploaded successfully", "clips": [],
        }
    return {"job_id": job_id, "filename": original_name, "size_bytes": size, "duration": round(duration, 2)}



@app.post("/api/youtube")
def download_youtube_video(url: str = Form(...)):
    """Download a user-supplied YouTube video URL for local processing using yt-dlp."""
    from urllib.parse import urlparse
    parsed = urlparse((url or "").strip())
    host = (parsed.hostname or "").lower()
    allowed_hosts = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtube-nocookie.com"}
    if parsed.scheme not in {"http", "https"} or host not in allowed_hosts:
        raise HTTPException(status_code=400, detail="Enter a valid YouTube URL (youtube.com or youtu.be).")
    try:
        import yt_dlp
    except ImportError:
        raise HTTPException(status_code=500, detail="YouTube support is not installed. Run: pip install -r requirements.txt")

    job_id = uuid.uuid4().hex
    upload_dir = UPLOADS / job_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    target_template = str(upload_dir / "source.%(ext)s")
    options = {
        "format": "best[ext=mp4]/best",
        "outtmpl": target_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
        "max_filesize": MAX_UPLOAD_BYTES,
        "socket_timeout": 30,
        "retries": 2,
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url.strip(), download=True)
            downloaded = Path(ydl.prepare_filename(info))
        if not downloaded.exists():
            # yt-dlp may merge the selected streams into MP4.
            possible = list(upload_dir.glob("source.*"))
            if not possible:
                raise RuntimeError("The downloader did not create a video file.")
            downloaded = possible[0]
        size = downloaded.stat().st_size
        if size == 0 or size > MAX_UPLOAD_BYTES:
            raise RuntimeError("Downloaded video is empty or exceeds the 2 GB MVP limit.")
        duration = probe_duration(downloaded)
        with jobs_lock:
            job_states[job_id] = {
                "job_id": job_id, "source_path": str(downloaded),
                "filename": info.get("title") or "YouTube video",
                "size_bytes": size, "duration": round(duration, 2),
                "status": "uploaded", "progress": 0,
                "message": "YouTube video downloaded successfully", "clips": [],
            }
        return {"job_id": job_id, "filename": info.get("title") or "YouTube video",
                "size_bytes": size, "duration": round(duration, 2)}
    except HTTPException:
        shutil.rmtree(upload_dir, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(upload_dir, ignore_errors=True)
        message = str(exc)
        raise HTTPException(status_code=400, detail=f"Could not download this YouTube video: {message[:350]}")

@app.post("/api/process")
def start_processing(req: ProcessRequest):
    state = safe_job(req.job_id)
    if req.mode not in {"fixed", "highlights"}:
        raise HTTPException(status_code=400, detail="mode must be fixed or highlights")
    if req.output_format not in {"vertical", "horizontal"}:
        raise HTTPException(status_code=400, detail="output_format must be vertical or horizontal")
    if state.get("status") == "processing":
        raise HTTPException(status_code=409, detail="This job is already processing.")
    update_job(req.job_id, status="queued", progress=1, message="Queued for processing", clips=[])
    threading.Thread(target=process_job, args=(req,), daemon=True).start()
    return {"job_id": req.job_id, "status": "queued"}

@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    state = safe_job(job_id)
    return {k: v for k, v in state.items() if k != "source_path" and k != "size_bytes"}

@app.get("/api/jobs/{job_id}/clips/{filename}")
def get_clip(job_id: str, filename: str):
    safe_job(job_id)
    if Path(filename).name != filename or not filename.endswith(".mp4"):
        raise HTTPException(status_code=400, detail="Invalid filename.")
    path = JOBS / job_id / "clips" / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Clip not ready.")
    return FileResponse(path, media_type="video/mp4", filename=filename)

@app.get("/api/jobs/{job_id}/download-all")
def download_all(job_id: str):
    safe_job(job_id)
    path = JOBS / job_id / "clips.zip"
    if not path.exists():
        raise HTTPException(status_code=404, detail="ZIP is not ready.")
    return FileResponse(path, media_type="application/zip", filename=f"video-clips-{job_id[:8]}.zip")

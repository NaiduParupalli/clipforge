import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Upload, Scissors, Sparkles, Download, Film, CheckCircle2, AlertCircle, LoaderCircle, FileVideo2, Clock3, Layers3 } from "lucide-react";
import "./style.css";

const API = import.meta.env.VITE_API_BASE || "";
const fmt = (seconds = 0) => {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60).toString().padStart(2, "0")}:${(s % 60).toString().padStart(2, "0")}`;
};

function App() {
  const [file, setFile] = useState(null);
  const [sourceType, setSourceType] = useState("upload");
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [job, setJob] = useState(null);
  const [mode, setMode] = useState("highlights");
  const [format, setFormat] = useState("vertical");
  const [clipSeconds, setClipSeconds] = useState(60);
  const [maxHighlights, setMaxHighlights] = useState(8);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [health, setHealth] = useState(null);
  const inputRef = useRef(null);

  useEffect(() => {
    fetch(`${API}/api/health`).then(r => r.json()).then(setHealth).catch(() => setHealth({status:"offline", ffmpeg_available:false}));
  }, []);

  useEffect(() => {
    if (!job?.job_id || !["queued", "processing"].includes(job.status)) return;
    const timer = setInterval(async () => {
      try {
        const r = await fetch(`${API}/api/jobs/${job.job_id}`);
        const data = await r.json();
        if (!r.ok) throw new Error(data.detail || "Could not read job status");
        setJob(data);
        if (["completed", "failed"].includes(data.status)) setBusy(false);
      } catch (e) {
        setError(e.message);
        setBusy(false);
      }
    }, 1200);
    return () => clearInterval(timer);
  }, [job?.job_id, job?.status]);

  const chooseFile = (f) => {
    if (!f) return;
    setError("");
    setJob(null);
    if (!/\.(mp4|mov|mkv|webm|m4v)$/i.test(f.name)) {
      setError("Choose an MP4, MOV, MKV, WebM, or M4V video.");
      return;
    }
    setFile(f);
  };

  const process = async () => {
    if (sourceType === "upload" && !file) { setError("Choose a video file first."); return; }
    if (sourceType === "youtube" && !youtubeUrl.trim()) { setError("Paste a YouTube link first."); return; }
    setBusy(true); setError(""); setJob(null);
    try {
      let uploaded;
      if (sourceType === "upload") {
        const form = new FormData();
        form.append("file", file);
        const upload = await fetch(`${API}/api/upload`, { method:"POST", body:form });
        uploaded = await upload.json();
        if (!upload.ok) throw new Error(uploaded.detail || "Upload failed.");
      } else {
        const form = new FormData();
        form.append("url", youtubeUrl.trim());
        const response = await fetch(`${API}/api/youtube`, { method:"POST", body:form });
        uploaded = await response.json();
        if (!response.ok) throw new Error(uploaded.detail || "YouTube link processing failed.");
      }
      const req = await fetch(`${API}/api/process`, {
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({
          job_id: uploaded.job_id, mode, output_format:format,
          clip_seconds: Number(clipSeconds), max_highlights:Number(maxHighlights)
        })
      });
      const started = await req.json();
      if (!req.ok) throw new Error(started.detail || "Could not start processing.");
      setJob({ ...uploaded, ...started, status:"queued", progress:1, message:"Queued for processing", clips:[] });
    } catch (e) {
      setError(e.message || "Something went wrong.");
      setBusy(false);
    }
  };

  const download = (url) => window.open(`${API}${url}`, "_blank", "noopener,noreferrer");

  return <div className="app-shell">
    <header className="topbar">
      <a className="brand" href="#"><span className="brand-mark"><Scissors size={20}/></span><span>clip<span className="brand-accent">forge</span></span></a>
      <div className="topbar-right"><span className={`status-dot ${health?.status === "ok" && health?.ffmpeg_available ? "online" : "offline"}`}></span>{health?.status === "ok" && health?.ffmpeg_available ? "Processing engine ready" : "Backend / FFmpeg check needed"}</div>
    </header>

    <main className="main">
      <section className="hero">
        <div className="eyebrow"><Sparkles size={14}/> AI-POWERED VIDEO WORKFLOW</div>
        <h1>One long video.<br/><span>Endless good clips.</span></h1>
        <p className="hero-copy">Turn long videos into scroll-stopping Shorts and clean, shareable clips. Upload once; let ClipForge do the cutting.</p>
      </section>

      <div className="workspace">
        <section className="panel upload-panel">
          <div className="panel-heading"><div><span className="step">01</span><h2>Upload your video</h2></div><span className="subtle">Max 2 GB</span></div>
          <div className="source-tabs">
            <button className={`source-tab ${sourceType==="upload"?"active":""}`} onClick={()=>{setSourceType("upload");setError("");}}><Upload size={15}/> Upload file</button>
            <button className={`source-tab ${sourceType==="youtube"?"active":""}`} onClick={()=>{setSourceType("youtube");setError("");}}><span className="youtube-mark">▶</span> YouTube link</button>
          </div>
          {sourceType === "upload" ? <div className={`dropzone ${file ? "has-file" : ""}`} onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();chooseFile(e.dataTransfer.files?.[0]);}}>
            <input ref={inputRef} type="file" accept=".mp4,.mov,.mkv,.webm,.m4v,video/*" hidden onChange={e=>chooseFile(e.target.files?.[0])}/>
            {file ? <><div className="upload-icon success"><FileVideo2 size={25}/></div><strong className="filename">{file.name}</strong><span className="file-meta">{(file.size/1024/1024).toFixed(1)} MB · Ready to process</span><button className="text-button" onClick={()=>inputRef.current?.click()}>Choose another file</button></>
              : <><div className="upload-icon"><Upload size={25}/></div><strong>Drop your video here</strong><span className="file-meta">MP4, MOV, MKV, WebM or M4V</span><button className="button button-secondary" onClick={()=>inputRef.current?.click()}>Browse files</button></>}
          </div> : <div className="youtube-entry">
            <div className="youtube-entry-icon"><span>▶</span></div>
            <strong>Paste a YouTube video link</strong>
            <span className="file-meta">Use a video you own or have permission to process.</span>
            <input className="youtube-input" type="url" placeholder="https://www.youtube.com/watch?v=..." value={youtubeUrl} onChange={e=>setYoutubeUrl(e.target.value)} onKeyDown={e=>{if(e.key==="Enter" && youtubeUrl.trim()) process();}}/>
            <span className="field-hint">Playlists are not processed. Some videos may be unavailable for download.</span>
          </div>}
          <div className="privacy-note"><span className="privacy-lock">●</span> {sourceType==="upload" ? "Files are processed on your computer while this local app is running." : "The video is downloaded to your local machine before processing."}</div>
        </section>

        <section className="panel settings-panel">
          <div className="panel-heading"><div><span className="step">02</span><h2>Choose your cut</h2></div></div>
          <div className="mode-grid">
            <button className={`mode-card ${mode==="highlights"?"selected":""}`} onClick={()=>setMode("highlights")}>
              <span className="mode-icon purple"><Sparkles size={19}/></span><span className="mode-title">AI Highlights</span><span className="mode-desc">Find promising moments from speech or scene changes.</span>{mode==="highlights"&&<CheckCircle2 className="selected-check" size={17}/>}
            </button>
            <button className={`mode-card ${mode==="fixed"?"selected":""}`} onClick={()=>setMode("fixed")}>
              <span className="mode-icon orange"><Scissors size={19}/></span><span className="mode-title">Fixed duration</span><span className="mode-desc">Split the full video into equal time segments.</span>{mode==="fixed"&&<CheckCircle2 className="selected-check" size={17}/>}
            </button>
          </div>

          {mode==="fixed" ? <div className="field-group"><label htmlFor="duration">Clip duration</label><select id="duration" value={clipSeconds} onChange={e=>setClipSeconds(Number(e.target.value))}><option value="30">30 seconds</option><option value="60">1 minute</option><option value="120">2 minutes</option><option value="300">5 minutes</option><option value="600">10 minutes</option></select></div>
          : <div className="field-group"><label htmlFor="count">Maximum highlights</label><select id="count" value={maxHighlights} onChange={e=>setMaxHighlights(Number(e.target.value))}><option value="4">4 clips</option><option value="6">6 clips</option><option value="8">8 clips</option><option value="12">12 clips</option><option value="20">20 clips</option></select><p className="field-hint">Uses local speech analysis when faster-whisper is installed.</p></div>}

          <div className="field-group"><label>Output format</label>
            <div className="format-grid">
              <button className={`format-option ${format==="vertical"?"selected":""}`} onClick={()=>setFormat("vertical")}><div className="ratio ratio-vertical"><span/></div><span><b>Vertical Shorts</b><small>9:16 · 1080 × 1920</small></span>{format==="vertical"&&<CheckCircle2 size={17}/>}</button>
              <button className={`format-option ${format==="horizontal"?"selected":""}`} onClick={()=>setFormat("horizontal")}><div className="ratio ratio-horizontal"><span/></div><span><b>Horizontal</b><small>16:9 · 1920 × 1080</small></span>{format==="horizontal"&&<CheckCircle2 size={17}/>}</button>
            </div>
          </div>
          <button className="button button-primary process-button" onClick={process} disabled={(sourceType==="upload" ? !file : !youtubeUrl.trim()) || busy || !(health?.status==="ok" && health?.ffmpeg_available)}>
            {busy ? <><LoaderCircle size={18} className="spin"/> Processing video…</> : <><Sparkles size={18}/> Generate clips</>}
          </button>
          {!(health?.status==="ok" && health?.ffmpeg_available) && <p className="error-text">Start the FastAPI backend and make sure FFmpeg is installed.</p>}
          {error && <p className="error-text"><AlertCircle size={15}/>{error}</p>}
        </section>
      </div>

      {job && <section className="panel results-panel">
        <div className="panel-heading"><div><span className="step">03</span><h2>Your clips</h2></div>{job.status==="completed"&&<button className="button button-secondary download-all" onClick={()=>download(job.zip_url)}><Download size={16}/> Download all (.zip)</button>}</div>
        {["queued","processing"].includes(job.status) && <div className="progress-area"><div className="progress-label"><span><LoaderCircle size={16} className="spin"/> {job.message || "Processing…"}</span><b>{job.progress || 0}%</b></div><div className="progress-track"><div className="progress-fill" style={{width:`${job.progress || 0}%`}}/></div><p className="field-hint">Keep this tab open while clips are being created.</p></div>}
        {job.status==="failed" && <div className="error-box"><AlertCircle size={18}/><div><b>Processing failed</b><p>{job.error || job.message}</p></div></div>}
        {job.warning && <div className="warning-box"><AlertCircle size={17}/><span>{job.warning}</span></div>}
        {job.status==="completed" && <>
          <div className="results-summary"><div><Layers3 size={17}/><b>{job.clips?.length || 0} clips created</b></div><div><Clock3 size={17}/><span>Source length {fmt(job.duration)}</span></div><div><Film size={17}/><span>{job.output_format==="vertical"?"Vertical 9:16":"Horizontal 16:9"}</span></div></div>
          <div className="clips-grid">{(job.clips || []).map(clip=><article className="clip-card" key={clip.id}>
            <div className={`clip-preview ${job.output_format==="vertical"?"preview-vertical":"preview-horizontal"}`}><video src={`${API}${clip.url}`} controls preload="metadata"/><span className="clip-number">CLIP {String(clip.id).padStart(2,"0")}</span></div>
            <div className="clip-info"><b>{clip.text?.length>48?clip.text.slice(0,48)+"…":clip.text || `Clip ${clip.id}`}</b><span>{fmt(clip.start)} – {fmt(clip.end)} · {fmt(clip.duration)}</span><button className="clip-download" onClick={()=>download(clip.url)}><Download size={15}/> Download MP4</button></div>
          </article>)}</div>
        </>}
      </section>}

      <footer><span>CLIPFORGE MVP</span><span>Built for creators · Local processing</span></footer>
    </main>
  </div>;
}

createRoot(document.getElementById("root")).render(<App />);

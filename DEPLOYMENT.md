# ClipForge deployment on Ubuntu VPS

This package includes Docker Compose, FFmpeg in the backend image, a persistent data volume, same-origin API proxy, and a minimal PWA manifest/icon.

## Important before public launch
This is a low-cost single-server MVP. The current backend stores job metadata in memory and uses an in-process thread, so restarts lose job status and it is not robust for many concurrent public users. Before broad public sharing, add authentication, per-user quotas, upload/download rate limits, automatic cleanup, durable job metadata, and a Redis-backed worker queue. Public unauthenticated use can be abused and incur hosting/bandwidth costs.

## Suggested server
Ubuntu 22.04/24.04 VPS, 2–4 vCPU, 4–8 GB RAM, 80+ GB SSD. Hour-long sources and exports may require many GB. A domain pointing to the server is needed for HTTPS/PWA installation.

## 1. Install Docker
Install Docker Engine and the Compose plugin using Docker's official Ubuntu instructions. Verify `docker --version` and `docker compose version`.

## 2. Copy project to the server
From your local Ubuntu computer, replace SERVER_USER and SERVER_IP:
```bash
scp -r ~/Downloads/ai-video-splitter-youtube-mvp/ai-video-splitter SERVER_USER@SERVER_IP:~/clipforge
ssh SERVER_USER@SERVER_IP
cd ~/clipforge
```
If you extracted this deployment ZIP, use that extracted project path instead.

## 3. Firewall
```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```
Also allow TCP 80/443 in the VPS provider firewall.

## 4. HTTP smoke test
```bash
docker compose up -d --build
docker compose ps
docker compose logs -f backend
```
Visit `http://SERVER_IP`. This is only a smoke test; PWA installation requires HTTPS except on localhost.

## 5. Enable HTTPS with a domain
Create an A record for your domain pointing to SERVER_IP. Edit `frontend/Caddyfile`, replace `:80 {` with your real domain:
```caddy
clipforge.example.com {
  @api path /api/*
  reverse_proxy @api backend:8000
  root * /usr/share/caddy
  try_files {path} /index.html
  file_server
}
```
Replace the example domain with yours, then:
```bash
docker compose up -d --build
```
Caddy obtains and renews HTTPS certificates when DNS points to the server and ports 80/443 are reachable. Visit `https://your-domain`.

## 6. Updates and health check
```bash
docker compose up -d --build
docker compose logs --tail=100 backend
curl -fsS http://127.0.0.1/api/health
```
Health JSON should include `"status":"ok"` and `"ffmpeg_available":true`.

## Install PWA
- Android: open HTTPS site in Chrome → menu → Install app / Add to Home screen.
- iPhone/iPad: open HTTPS site in Safari → Share → Add to Home Screen.
- Desktop Chrome/Edge: use the install icon or browser menu.
This minimal PWA shell does not support offline video processing.

## Long-video cautions
- Upload cap is 2 GB.
- Keep several GB free; source videos plus outputs can be large.
- `WHISPER_MODEL=tiny` reduces CPU/RAM use but larger models may improve transcription.
- YouTube access/download availability can change; process only videos you own or have permission to use.
- For robust public long-running jobs, migrate job state to PostgreSQL and use Redis + Celery/RQ instead of in-process threads.

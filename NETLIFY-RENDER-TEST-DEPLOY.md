# ClipForge: Netlify frontend + Render backend (free testing)

This setup is for a small test only. Free backend instances can sleep, restart, and have limited CPU/RAM/disk. A 1-hour video may fail or be very slow. The current app stores job state in memory, so a backend restart can lose progress/results. Do not use for public production without durable storage, queue, cleanup, rate limits and authentication.

## A. Push this project to GitHub
1. Extract this ZIP.
2. Create a GitHub repository named `clipforge`.
3. Upload the contents of the `ai-video-splitter` folder (the files inside it, not the parent ZIP).
4. Ensure `netlify.toml` is in the repository root, alongside `backend/` and `frontend/`.

## B. Deploy backend on Render
1. In Render, create a **New Web Service** and connect the GitHub repository.
2. Set **Root Directory** to `backend`.
3. Set **Runtime** to Docker.
4. Use Dockerfile path `./Dockerfile` (relative to backend root, if requested).
5. Choose the free instance for testing and deploy.
6. After deploy, copy the service URL, e.g. `https://YOUR-SERVICE.onrender.com`.
7. Test `https://YOUR-SERVICE.onrender.com/api/health`. It should return JSON with `status: ok` and `ffmpeg_available: true`.
8. Set environment variable `CORS_ORIGINS` to the Netlify site origin, e.g. `https://YOUR-SITE.netlify.app` (no trailing slash). You can set it now after you know the Netlify URL; redeploy/restart if needed.

## C. Deploy frontend on Netlify
1. In Netlify choose Add new project / Import an existing project and connect the same GitHub repository.
2. The included `netlify.toml` sets base directory `frontend`, build command `npm run build`, and publish directory `dist`.
3. Add environment variable `VITE_API_BASE` with value equal to the Render backend URL, e.g. `https://YOUR-SERVICE.onrender.com` (no trailing slash).
4. Deploy the site and copy its URL, e.g. `https://YOUR-SITE.netlify.app`.
5. Return to Render and set `CORS_ORIGINS` to that exact Netlify origin, then restart/redeploy the backend.
6. Reload Netlify site and wait for backend cold start on first request.

## D. Test in this order
1. Open `https://YOUR-SITE.netlify.app`.
2. The status should show the processing engine ready. If not, open the backend `/api/health` URL directly and check Render logs and the `VITE_API_BASE` setting.
3. Try a small video upload first (10–30 seconds), then fixed-duration splitting, one clip download, and Download all (.zip).
4. Try a public YouTube URL only after upload splitting works. YouTube availability and yt-dlp compatibility can change.
5. Test AI Highlights only if the app's configured transcription/dependencies support it; check the UI/backend logs for any missing optional dependency.
6. Install the PWA from Chrome/Edge's install option or mobile browser menu. HTTPS is supplied by Netlify.

## Limits and safety
- Free backend hosting is a smoke-test environment, not reliable for one-hour video processing. It may sleep, restart, run out of memory/disk, or lose results. Use a small test file first.
- The app currently has no user login or quotas. Do not publish it widely until authentication, rate limiting, storage cleanup and resource limits are added.
- Only process videos you own or have permission to download/use.
- Netlify hosts the frontend; it does not run the Python/FFmpeg backend in this architecture.

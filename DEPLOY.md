# Deploying to production (Linux server)

## Deploy on Render (recommended)

1. **Push the project to GitHub** (if not already).
2. Go to [dashboard.render.com](https://dashboard.render.com) → **New** → **Web Service**.
3. Connect your GitHub account and select the repo.
4. Configure:
   - **Name**: e.g. `instagram-analyzer`
   - **Region**: choose closest to you
   - **Root Directory**: leave empty
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command:** `bash start.sh` (or `cd backend && gunicorn app:app -c gunicorn_config.py`).
  - Uses `backend/gunicorn_config.py` so the port is read from the `PORT` env var **inside Python**, which fixes "No open HTTP ports detected" on Render.
  - Timeout 5 min, 1 worker.
5. **Advanced** (optional):
   - Env var `PYTHON_VERSION=3.12` if you want a specific version.
   - **Health Check Path**: set to `/healthz` so Render knows the app is up (Settings → Health Check Path).
6. Click **Create Web Service**. Render sets `PORT` automatically and gives you a URL like `https://your-service.onrender.com`.

**Note:** On the free tier the service sleeps after ~15 minutes of no traffic; the first request after that may take **1–2 minutes** to wake up (keep the tab open and wait).

**If the site doesn’t open:** wait 1–2 minutes and refresh (cold start); check Render **Logs** for errors; in **Settings** set Health Check Path to `/healthz`.

---

## Run with Gunicorn (VPS / your own server)

From the project root:

```bash
pip install -r requirements.txt
cd backend
PORT=8000 gunicorn -w 1 -b 0.0.0.0:$PORT --timeout 300 app:app
```

- `-w 1` — one worker (progress updates work correctly).
- `--timeout 300` — request timeout 5 minutes (so /analyze verification does not get cut).
- `-b 0.0.0.0:$PORT` — listen on all interfaces; set `PORT` in the environment (e.g. 8000 or your host’s port).
- Run behind a reverse proxy (nginx, Caddy) for HTTPS.

---

## Notes

- **Upload limit**: 5 MB (configurable via `MAX_CONTENT_LENGTH` in `app.py`).
- **No profile checks**: Lists are shown as in your Instagram export; no API or session needed.
- **“Open in tabs”**: Works in the user’s browser (client-side); no server-side open needed.

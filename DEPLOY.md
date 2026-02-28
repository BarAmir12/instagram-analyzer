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
   - **Start Command**: `cd backend && gunicorn -w 1 -b 0.0.0.0:$PORT app:app`
5. **Advanced** (optional): add env var `PYTHON_VERSION=3.12` if you want a specific version.
6. Click **Create Web Service**. Render sets `PORT` automatically and gives you a URL like `https://your-service.onrender.com`.

**Note:** On the free tier the service sleeps after ~15 minutes of no traffic; the first request after that may take ~1 minute to wake up.

---

## Run with Gunicorn (VPS / your own server)

From the project root:

```bash
pip install -r requirements.txt
cd backend
PORT=8000 gunicorn -w 1 -b 0.0.0.0:$PORT app:app
```

- `-w 1` — one worker (progress updates work correctly).
- `-b 0.0.0.0:$PORT` — listen on all interfaces; set `PORT` in the environment (e.g. 8000 or your host’s port).
- Run behind a reverse proxy (nginx, Caddy) for HTTPS.

---

## Notes

- **Upload limit**: 80 MB (configurable via `MAX_CONTENT_LENGTH` in `app.py`).
- **Cookies**: On Linux, Chrome/Keychain login is skipped; the app uses cache or basic cookies.
- **“Open in tabs”**: Works in the user’s browser (client-side); no server-side open needed.

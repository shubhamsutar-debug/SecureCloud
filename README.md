# SecureCloud — Encrypted Cloud File Storage System

A full-stack demonstration of end-to-end encrypted file storage:  
split → AES-256 encrypt → Vercel Blob → download → decrypt → SHA-256 verify.

---

## Project structure

```
encrypted-cloud-project/
├── app.py                  ← Flask web backend (NEW)
├── core.py                 ← Shared pipeline logic (NEW, extracted from main.py)
├── main.py                 ← Standalone CLI entry-point (updated to import core.py)
├── cloud_storage.py        ← Vercel Blob upload / download (unchanged)
├── requirements.txt        ← Python dependencies (updated)
├── gunicorn.conf.py        ← Production WSGI config (NEW)
├── render.yaml             ← Render.com deployment config (NEW)
├── vercel.json             ← Vercel static-frontend routing (NEW)
├── .gitignore              ← Protects secrets & generated files (updated)
├── .env.local              ← Your local secrets (NEVER committed)
│
└── website/
    └── index.html          ← Single-page SaaS frontend (NEW)
```

---

## How the code connects

```
Browser  ──POST /api/process──►  app.py  ──imports──►  core.py
                                                           ├── cloud_storage.py  (upload_block / download_block)
                                                           └── cryptography.fernet  (Fernet AES-256)

Browser  ──GET /api/download/<id>──►  app.py  ──streams reconstructed file
```

- `core.py` contains **all** the pipeline logic (split, encrypt, upload, download, decrypt, verify).  
- `main.py` imports `process_file` from `core.py` and works exactly as before via `python main.py`.  
- `app.py` also imports from `core.py` — no code is duplicated.

---

## Local development (Windows PowerShell)

### 1. Install dependencies

```powershell
cd "C:\Users\hp\Desktop\encrypted-cloud-project"

# Create a virtual environment (skip if already done)
python -m venv .venv

# Activate it
.\.venv\Scripts\Activate.ps1

# Install all packages
pip install -r requirements.txt

# Also install gunicorn for local production-style testing (optional)
pip install gunicorn==21.2.0
```

### 2. Confirm your .env.local has the token

Open `.env.local` and make sure it contains:

```
BLOB_READ_WRITE_TOKEN=vercel_blob_rw_xxxxxxxxxxxxxxxx
```

Do **not** add quotes around the value.

### 3. Start the Flask development server

```powershell
python app.py
```

You will see:

```
 * Running on http://127.0.0.1:5000
```

Open `http://localhost:5000` in your browser. The full UI is served from there.

### 4. Test the CLI as before (unchanged)

```powershell
python main.py
```

---

## Security — what is protected

| Secret / file           | Where it lives            | Exposed in frontend JS? |
|-------------------------|---------------------------|-------------------------|
| `BLOB_READ_WRITE_TOKEN` | `.env.local` / env var    | **No**                  |
| Fernet key              | Server RAM (per request)  | **No**                  |
| `secret.key`            | Gitignored, CLI only      | **No**                  |
| Encrypted blocks        | Vercel Blob (private ACL) | **No**                  |

---

## Deployment

### Option A — Backend on Render, frontend on Vercel

**Backend (Render.com — free tier)**

1. Push the repo to GitHub (your `.gitignore` already excludes secrets).
2. Go to https://render.com/new → "Web Service" → connect your repo.
3. Render auto-detects `render.yaml`.
4. In Render dashboard → Environment → add `BLOB_READ_WRITE_TOKEN`.
5. Deploy. Your backend URL will be `https://securecloud-backend.onrender.com`.

**Frontend (Vercel)**

1. In `website/index.html`, find the `fetch('/api/process', ...)` call.
2. Change it to `fetch('https://securecloud-backend.onrender.com/api/process', ...)`.
3. Also update the `window.location.href` download URL similarly.
4. Push to GitHub, import to Vercel. It serves `website/index.html` as a static site.

> **CORS note**: add `flask-cors` and `CORS(app, origins=["https://your-vercel-domain.vercel.app"])` in `app.py` when running backend and frontend on different origins.

### Option B — Everything on Render (easiest for a college assignment)

Deploy the Flask app to Render as above. Flask serves `website/index.html` directly from the `/` route. No separate Vercel frontend deployment needed.

### HTTPS / CDN

- Render and Vercel both provide HTTPS automatically via Let's Encrypt — no manual certificate configuration needed.
- Vercel's CDN serves static assets from edge locations worldwide.
- All API calls from the browser to the backend should use HTTPS in production to protect file data in transit.

---

## Files created / modified

| File                       | Status   | Description                                      |
|----------------------------|----------|--------------------------------------------------|
| `core.py`                  | **NEW**  | Shared pipeline (split, encrypt, upload, verify) |
| `app.py`                   | **NEW**  | Flask web server with 3 endpoints                |
| `website/index.html`       | **NEW**  | SaaS-style single-page frontend                  |
| `gunicorn.conf.py`         | **NEW**  | Production WSGI config                           |
| `render.yaml`              | **NEW**  | Render.com deployment manifest                   |
| `vercel.json`              | **NEW**  | Vercel static routing config                     |
| `README.md`                | **NEW**  | This file                                        |
| `main.py`                  | UPDATED  | Now imports `process_file` from `core.py`        |
| `requirements.txt`         | UPDATED  | Added Flask, Werkzeug (cryptography unchanged)   |
| `.gitignore`               | UPDATED  | Tightened rules; added temp dirs, IDE files      |
| `cloud_storage.py`         | unchanged | Vercel Blob wrappers                            |

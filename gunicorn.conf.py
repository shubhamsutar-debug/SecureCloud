# gunicorn.conf.py — Production WSGI config for Render / Railway / VPS.
# Used by: gunicorn app:app -c gunicorn.conf.py

import os

bind    = f"0.0.0.0:{os.environ.get('PORT', '5000')}"
workers = 1          # Keep at 1 — in-memory run store is not shared between workers.
timeout = 180        # Fernet + Vercel Blob upload can take a while for large files.
loglevel = "info"
accesslog = "-"
errorlog  = "-"

"""
api/index.py — Vercel serverless entry point.

Vercel looks for a callable named `app` (or `handler`) in this file.
We simply re-export the Flask app from app.py so all routes are served
through a single serverless function.

Vercel serverless notes:
  - Each request is a fresh invocation; the in-memory _runs dict in app.py
    will not persist across invocations.  For a college demo this is fine —
    the download link is followed immediately after processing.
  - /tmp is writable and has ~500 MB; tempfile.mkdtemp() works correctly.
  - BLOB_READ_WRITE_TOKEN is injected automatically from Vercel project env.
"""

import sys
import os

# Make the project root importable (Vercel runs api/index.py from the repo root)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # re-export Flask app; Vercel detects the `app` name

# Vercel's Python runtime calls the WSGI `app` callable directly.

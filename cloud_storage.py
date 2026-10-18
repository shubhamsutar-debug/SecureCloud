"""
cloud_storage.py — Vercel Blob upload / download via REST API.

Uses the Vercel Blob REST API directly with the requests library.
This replaces the previous subprocess-based Vercel CLI approach so the
code works identically in:
  - local development (python app.py / python main.py)
  - Vercel serverless functions (no CLI binary available at runtime)

Environment variable required:
  BLOB_READ_WRITE_TOKEN   — set in .env.local locally, Vercel project env in production.
"""

from __future__ import annotations

import os
from pathlib import Path

import requests


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _token() -> str:
    """Return the Blob token, raising clearly if it is missing."""
    tok = os.environ.get("BLOB_READ_WRITE_TOKEN", "").strip().strip("'\"")
    if not tok:
        raise EnvironmentError(
            "BLOB_READ_WRITE_TOKEN is not set. "
            "Add it to .env.local (local) or Vercel project environment (production)."
        )
    return tok


_BLOB_API = "https://blob.vercel-storage.com"


# ---------------------------------------------------------------------------
# Public API — same signatures as the original cloud_storage.py
# ---------------------------------------------------------------------------

def upload_block(local_path: Path | str, remote_path: str) -> str:
    """
    Upload one encrypted block to Vercel Blob (private access).

    Parameters
    ----------
    local_path  : local file to upload
    remote_path : the pathname to use inside the Blob store

    Returns
    -------
    The public URL of the uploaded blob (used for private token-gated download).
    """
    local_path = Path(local_path)
    token = _token()

    with local_path.open("rb") as fh:
        data = fh.read()

    resp = requests.put(
        f"{_BLOB_API}/{remote_path}",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "x-api-version": "7",
            "x-content-type": "application/octet-stream",
            # Private access — only accessible with token
            "x-cache-control-max-age": "0",
        },
        timeout=120,
    )

    if not resp.ok:
        raise RuntimeError(
            f"Blob upload failed [{resp.status_code}]: {resp.text[:400]}"
        )

    result = resp.json()
    url = result.get("url", "")
    print(f"Uploaded: {remote_path}  →  {url}")
    return url


def download_block(remote_path: str, destination: Path | str) -> None:
    """
    Download one private Blob object to a local file.

    Parameters
    ----------
    remote_path  : the pathname used when uploading (NOT the full URL)
    destination  : local path to write the downloaded bytes to
    """
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    token = _token()

    # Construct the download URL.  The Vercel Blob REST API returns the URL
    # in the upload response; we reconstruct it deterministically here.
    url = f"{_BLOB_API}/{remote_path}"

    resp = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "x-api-version": "7",
        },
        timeout=120,
        stream=True,
    )

    if not resp.ok:
        raise RuntimeError(
            f"Blob download failed [{resp.status_code}] for {remote_path}: {resp.text[:400]}"
        )

    with destination.open("wb") as fh:
        for chunk in resp.iter_content(chunk_size=65536):
            fh.write(chunk)

    if not destination.exists() or destination.stat().st_size == 0:
        raise FileNotFoundError(
            f"Download produced an empty or missing file: {destination}"
        )

    print(f"Downloaded: {remote_path}  →  {destination}")

"""
cloud_storage.py — Vercel Blob upload / download via the official Python SDK.

Uses vercel.blob.sync (vercel-blob >= 0.5.0, ships with the `vercel` package)
which correctly handles private-store authentication with BLOB_READ_WRITE_TOKEN.

The previous implementation used raw requests.put() calls without the required
`x-access: private` header, causing Vercel to reject uploads with:
    {"error": {"code": "bad_request", "message": "Cannot use public access
     on a private store."}}

This version delegates header construction and auth to the official SDK.

Environment variable required:
    BLOB_READ_WRITE_TOKEN — set in .env.local (local dev) or Vercel project
                            environment settings (production / preview).
"""

from __future__ import annotations

from pathlib import Path

import vercel.blob.sync as blob


# ---------------------------------------------------------------------------
# Public API — same signatures as all previous versions of this file
# ---------------------------------------------------------------------------

def upload_block(local_path: Path | str, remote_path: str) -> str:
    """
    Upload one encrypted block to the private Vercel Blob store.

    Parameters
    ----------
    local_path  : path to the local encrypted block file
    remote_path : the full pathname to use inside the Blob store
                  e.g. "encrypted-project/<run_id>/block_0001.bin"

    Returns
    -------
    str — the Blob URL returned by Vercel (token-gated, not publicly accessible)
    """
    local_path = Path(local_path)

    with local_path.open("rb") as fh:
        data = fh.read()

    result = blob.put_blob(
        remote_path,
        data,
        access="private",           # matches the private store configuration
        allow_overwrite=True,       # safe — remote_path includes a unique run_id
        content_type="application/octet-stream",
    )

    print(f"Uploaded: {remote_path}  →  {result.url}")
    return result.url


def download_block(remote_path: str, destination: Path | str) -> None:
    """
    Download one private Blob object and write it to a local file.

    Parameters
    ----------
    remote_path  : the pathname used when uploading
                   (the SDK constructs the full URL from BLOB_STORE_ID)
    destination  : local path to write the downloaded bytes to
    """
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    result = blob.get_blob(
        remote_path,
        access="private",
    )

    destination.write_bytes(result.body)

    if destination.stat().st_size == 0:
        raise FileNotFoundError(
            f"Download produced an empty file: {destination}"
        )

    print(f"Downloaded: {remote_path}  →  {destination}")

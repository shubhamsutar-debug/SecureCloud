"""
core.py — shared encryption / cloud-storage pipeline.

Both app.py (Flask web server) and main.py (CLI) import from here.
No secrets, no file paths, no globals are exposed outside this module.
"""

from __future__ import annotations  # enables list[str] on Python 3.8

from pathlib import Path
import hashlib
import uuid

from cryptography.fernet import Fernet

from cloud_storage import upload_block, download_block


BLOCK_SIZE = 1024  # bytes — same as original main.py


# ---------------------------------------------------------------------------
# Hashing helper (originally defined in main.py — kept here so both callers
# can import it without duplication)
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    """Return the hex SHA-256 digest of *path*."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(4096), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def process_file(source_path: Path, work_dir: Path) -> dict:
    """
    Full pipeline: split → encrypt → upload → download → decrypt → verify.

    Parameters
    ----------
    source_path : Path
        The file to process (already saved on disk by the caller).
    work_dir : Path
        A per-run scratch directory.  Sub-directories ``encrypted_blocks``
        and ``downloaded_blocks`` are created inside it.

    Returns
    -------
    dict with keys:
        run_id, original_hash, reconstructed_hash, integrity_pass,
        block_count, reconstructed_path, log (list[str])
    """
    log: list[str] = []

    run_id = uuid.uuid4().hex[:12]
    blocks_dir = work_dir / "encrypted_blocks"
    download_dir = work_dir / "downloaded_blocks"
    output_path = work_dir / "reconstructed_file"

    blocks_dir.mkdir(parents=True, exist_ok=True)
    download_dir.mkdir(parents=True, exist_ok=True)

    # ── Step 1: hash the original ──────────────────────────────────────────
    original_hash = sha256_file(source_path)
    log.append(f"Original SHA-256: {original_hash}")

    # ── Step 2: encrypt and upload ─────────────────────────────────────────
    key = Fernet.generate_key()
    cipher = Fernet(key)
    remote_paths: list[str] = []

    log.append("Encrypting and uploading blocks …")

    with source_path.open("rb") as src:
        index = 1
        while True:
            data = src.read(BLOCK_SIZE)
            if not data:
                break

            encrypted = cipher.encrypt(data)
            local_block = blocks_dir / f"block_{index:04d}.bin"
            local_block.write_bytes(encrypted)

            remote_path = f"encrypted-project/{run_id}/block_{index:04d}.bin"
            upload_block(local_block, remote_path)
            remote_paths.append(remote_path)
            log.append(f"  Uploaded block {index:04d}")
            index += 1

    block_count = len(remote_paths)
    log.append(f"Uploaded {block_count} encrypted block(s).")

    # ── Step 3: download and decrypt ───────────────────────────────────────
    log.append("Downloading and decrypting blocks …")

    with output_path.open("wb") as out:
        for idx, remote_path in enumerate(remote_paths, start=1):
            downloaded = download_dir / f"block_{idx:04d}.bin"
            download_block(remote_path, downloaded)

            encrypted_data = downloaded.read_bytes()
            plaintext = cipher.decrypt(encrypted_data)
            out.write(plaintext)
            log.append(f"  Decrypted block {idx:04d}")

    # ── Step 4: verify ─────────────────────────────────────────────────────
    reconstructed_hash = sha256_file(output_path)
    integrity_pass = original_hash == reconstructed_hash

    log.append(f"Reconstructed SHA-256: {reconstructed_hash}")
    log.append(
        f"Integrity verification: {'PASS [OK]' if integrity_pass else 'FAIL [ERROR]'}"
    )

    return {
        "run_id": run_id,
        "original_hash": original_hash,
        "reconstructed_hash": reconstructed_hash,
        "integrity_pass": integrity_pass,
        "block_count": block_count,
        "reconstructed_path": str(output_path),
        "log": log,
    }

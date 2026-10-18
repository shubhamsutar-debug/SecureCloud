from pathlib import Path
import os
import shutil
import subprocess


def _ensure_env():
    """Ensure environment variables from .env.local are loaded and sanitized."""
    env_local = Path(".env.local")
    if env_local.exists():
        for line in env_local.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip().strip("'\"")
                if k not in os.environ or os.environ[k].startswith(('"', "'")):
                    os.environ[k] = v


def run_vercel(*args):
    """Run a Vercel CLI command and show useful errors."""
    _ensure_env()

    # Locate vercel executable on Windows (.cmd, etc.) or Unix
    cmd = shutil.which("vercel") or shutil.which("vercel.cmd") or "vercel"

    # Ensure token is passed explicitly if available and not already specified
    token = os.environ.get("BLOB_READ_WRITE_TOKEN", "").strip().strip("'\"")
    extra_args = []
    if token and ("blob" in args) and ("--rw-token" not in args) and ("--oidc-token" not in args):
        extra_args.extend(["--rw-token", token])

    result = subprocess.run(
        [cmd, *args, *extra_args],
        capture_output=True,
        text=True,
        shell=False,
        env=os.environ
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Vercel command failed:\n{result.stderr}\n{result.stdout}"
        )

    if result.stdout:
        print(result.stdout.strip())


def upload_block(local_path, remote_path):
    """Upload one encrypted block to private Vercel Blob."""
    local_path = Path(local_path)

    run_vercel(
        "blob", "put", str(local_path),
        "--access", "private",
        "--pathname", remote_path
    )

    print(f"Uploaded: {remote_path}")


def download_block(remote_path, destination):
    """Download one private Blob object to a local file."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    run_vercel(
        "blob", "get", remote_path,
        "--access", "private",
        "--output", str(destination)
    )

    if not destination.exists():
        raise FileNotFoundError(
            f"Download did not create: {destination}"
        )

    print(f"Downloaded: {remote_path} -> {destination}")

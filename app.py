"""
app.py — Flask WSGI app for SecureCloud.

Local development:
    python app.py              (Flask dev server on http://localhost:5000)

Vercel production:
    Vercel auto-detects the `app` variable and runs it as a serverless function.
    All routes are handled here. Static assets in public/ are served by Vercel CDN.

Endpoints
---------
GET  /                   Serve the frontend HTML.
GET  /api/health         Health check.
POST /api/process        Accept file upload, run full pipeline, return JSON.
GET  /api/download/<id>  Stream reconstructed file back to browser.
"""

from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

# ---------------------------------------------------------------------------
# Load .env.local for local development (Vercel injects env vars natively)
# ---------------------------------------------------------------------------
def _load_env_local():
    env_local = Path(__file__).parent / ".env.local"
    if not env_local.exists():
        return
    for line in env_local.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip("'\"")
        os.environ.setdefault(k, v)

_load_env_local()

# Import pipeline after env is loaded so cloud_storage.py can read the token
from core import process_file  # noqa: E402

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(
    __name__,
    template_folder="templates",   # Flask looks here for render_template()
    static_folder="public",        # Vercel CDN also serves public/ directly
    static_url_path="/public",
)

app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB upload limit

ALLOWED_EXTENSIONS = {
    "txt", "pdf", "png", "jpg", "jpeg", "gif", "mp3", "mp4",
    "csv", "json", "xml", "zip", "docx", "xlsx", "py", "js",
}

# In-memory run store: run_id -> {work_dir, reconstructed_path, original_filename}
# NOTE: Vercel serverless functions are stateless across invocations.
# The download must happen in the same invocation window as the upload
# (within a single HTTP request chain). For a college demo this works fine
# because the process endpoint completes the full pipeline synchronously.
_runs: dict = {}
_runs_lock = threading.Lock()


def _allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ---------------------------------------------------------------------------
# CORS — allow cross-origin requests during development
# ---------------------------------------------------------------------------
@app.after_request
def _cors(response):
    response.headers.setdefault("Access-Control-Allow-Origin", "*")
    response.headers.setdefault("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    response.headers.setdefault("Access-Control-Allow-Headers", "Content-Type")
    return response


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Serve the single-page frontend."""
    return render_template("index.html")


@app.route("/favicon.ico")
def favicon():
    return "", 204


@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok", "app": "SecureCloud"})


@app.route("/api/process", methods=["POST", "OPTIONS"])
def api_process():
    if request.method == "OPTIONS":
        return "", 204

    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file field in request."}), 400

    uploaded = request.files["file"]
    if not uploaded.filename:
        return jsonify({"success": False, "error": "No file selected."}), 400

    filename = secure_filename(uploaded.filename)
    if not _allowed(filename):
        return jsonify({
            "success": False,
            "error": (
                f"File type not allowed. "
                f"Permitted: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            ),
        }), 415

    # /tmp is writable on both local and Vercel serverless
    work_dir = Path(tempfile.mkdtemp(prefix="securecloud_run_"))

    try:
        source_path = work_dir / filename
        uploaded.save(str(source_path))
        file_size = source_path.stat().st_size

        result = process_file(source_path, work_dir / "pipeline")
        run_id = result["run_id"]

        with _runs_lock:
            _runs[run_id] = {
                "work_dir": str(work_dir),
                "reconstructed_path": result["reconstructed_path"],
                "original_filename": filename,
            }

        return jsonify({
            "success": True,
            "run_id": run_id,
            "filename": filename,
            "file_size": file_size,
            "block_count": result["block_count"],
            "original_hash": result["original_hash"],
            "reconstructed_hash": result["reconstructed_hash"],
            "integrity_pass": result["integrity_pass"],
            "log": result["log"],
        })

    except Exception as exc:  # pylint: disable=broad-except
        import shutil
        shutil.rmtree(work_dir, ignore_errors=True)
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/download/<run_id>")
def api_download(run_id: str):
    import shutil

    if not run_id.isalnum() or len(run_id) > 40:
        return jsonify({"error": "Invalid run ID."}), 400

    with _runs_lock:
        run_info = _runs.get(run_id)

    if run_info is None:
        return jsonify({"error": "Run not found or already downloaded."}), 404

    reconstructed = Path(run_info["reconstructed_path"])
    original_filename = run_info.get("original_filename", "reconstructed_file")
    work_dir = run_info["work_dir"]

    if not reconstructed.exists():
        with _runs_lock:
            _runs.pop(run_id, None)
        return jsonify({"error": "Reconstructed file missing on server."}), 500

    with _runs_lock:
        _runs.pop(run_id, None)

    response = send_file(
        str(reconstructed),
        as_attachment=True,
        download_name=f"reconstructed_{original_filename}",
        mimetype="application/octet-stream",
    )

    @response.call_on_close
    def _cleanup():
        shutil.rmtree(work_dir, ignore_errors=True)

    return response


# ---------------------------------------------------------------------------
# Local dev entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True, port=5000)

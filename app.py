"""
app.py — Flask web server for SecureCloud.

Endpoints
---------
GET  /                          Serve the frontend HTML.
POST /api/process               Accept an uploaded file, run the full
                                encrypt → upload → download → verify pipeline,
                                return JSON results.
GET  /api/download/<run_id>     Stream the reconstructed file back to the
                                browser.

Security notes
--------------
* The Fernet key is generated per-run and never leaves the server.
* BLOB_READ_WRITE_TOKEN is read from the environment (set in .env.local or
  Vercel project settings) and never forwarded to the browser.
* Reconstructed files are stored in a per-run temp directory that is cleaned
  up after the download completes.
* Uploaded file names are sanitised with werkzeug.utils.secure_filename.
"""

import os
import tempfile
import threading
from pathlib import Path

from flask import (
    Flask,
    jsonify,
    request,
    send_file,
)
from werkzeug.utils import secure_filename

from core import process_file

# ---------------------------------------------------------------------------
# Load environment secrets early (stripping any accidental quotes)
# ---------------------------------------------------------------------------
_env_local = Path(".env.local")
if _env_local.exists():
    for _line in _env_local.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            _k = _k.strip()
            _v = _v.strip().strip("'\"")
            if _k not in os.environ or os.environ[_k].startswith(('"', "'")):
                os.environ[_k] = _v

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = Flask(__name__, static_folder="website/static", template_folder="website")

@app.after_request
def add_cors_headers(response):
    """Enable CORS so frontend works smoothly from Live Server or custom ports."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response

# Maximum upload size: 50 MB.  Adjust as needed.
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024


ALLOWED_EXTENSIONS = {
    "txt", "pdf", "png", "jpg", "jpeg", "gif", "mp3", "mp4",
    "csv", "json", "xml", "zip", "docx", "xlsx", "py", "js",
}

# In-memory store:  run_id → {"work_dir": str, "reconstructed_path": str}
# A per-process dict is fine for a single-worker demo/assignment server.
_runs = {}  # type: dict
_runs_lock = threading.Lock()


def _allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ---------------------------------------------------------------------------
# Read the HTML template at startup so we can serve it inline (no separate
# template folder needed for a single-page app).
# ---------------------------------------------------------------------------

_HTML_PATH = Path(__file__).parent / "website" / "index.html"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Serve the frontend."""
    if _HTML_PATH.exists():
        return _HTML_PATH.read_text(encoding="utf-8")
    return "<h1>SecureCloud frontend not found.</h1><p>Place website/index.html.</p>", 404


@app.route("/favicon.ico")
def favicon():
    """Empty favicon response to avoid 404 console errors."""
    return "", 204


@app.route("/api/health")
def api_health():
    """Health check endpoint to verify backend status."""
    return jsonify({"status": "ok", "app": "SecureCloud"})


@app.route("/api/process", methods=["POST", "OPTIONS"])
def api_process():
    if request.method == "OPTIONS":
        return "", 204

    """
    Accept a file upload, run the full pipeline, return JSON.

    Expected request: multipart/form-data with field name ``file``.

    Response JSON
    -------------
    {
        "success": true,
        "run_id": "...",
        "filename": "...",
        "file_size": 12345,
        "block_count": 9,
        "original_hash": "...",
        "reconstructed_hash": "...",
        "integrity_pass": true,
        "log": ["...", "..."]
    }
    """
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file field in request."}), 400

    uploaded = request.files["file"]

    if uploaded.filename == "" or uploaded.filename is None:
        return jsonify({"success": False, "error": "No file selected."}), 400

    filename = secure_filename(uploaded.filename)

    if not _allowed(filename):
        return jsonify({
            "success": False,
            "error": f"File type not allowed. Permitted: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        }), 415

    # Create a persistent temp dir for this run so the reconstructed file
    # survives until the client downloads it.
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
        # Clean up the work dir on failure so we don't leak disk space.
        import shutil
        shutil.rmtree(work_dir, ignore_errors=True)
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/download/<run_id>")
def api_download(run_id: str):
    """Stream the reconstructed file and then clean up the temp directory."""
    import shutil

    # Validate run_id to prevent path-traversal attacks.
    if not run_id.isalnum() or len(run_id) > 40:
        return jsonify({"error": "Invalid run ID."}), 400

    # Peek first — don't pop until we know the file is there.
    with _runs_lock:
        run_info = _runs.get(run_id)

    if run_info is None:
        return jsonify({"error": "Run not found or already downloaded."}), 404

    reconstructed = Path(run_info["reconstructed_path"])
    original_filename = run_info.get("original_filename", "reconstructed_file")
    work_dir = run_info["work_dir"]

    if not reconstructed.exists():
        # File is missing — remove the stale entry and report error.
        with _runs_lock:
            _runs.pop(run_id, None)
        return jsonify({"error": "Reconstructed file missing on server."}), 500

    # Remove the entry now so a second click gets a clean 404 instead of
    # trying to stream a file that may already be cleaned up.
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
# Dev server entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Load .env.local when running locally (python app.py).
    env_local = Path(".env.local")
    if env_local.exists():
        for line in env_local.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    app.run(debug=True, port=5000)

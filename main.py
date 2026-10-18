"""
main.py — standalone CLI entry-point (unchanged behaviour).

The encryption / cloud-storage pipeline now lives in core.py so that
app.py (the Flask web server) can reuse it without duplication.
"""

from pathlib import Path
import tempfile

from core import process_file

INPUT_FILE = Path("sample.txt")


def main():
    if not INPUT_FILE.exists():
        INPUT_FILE.write_text(
            "Encrypted cloud storage project demo.\n" * 100,
            encoding="utf-8",
        )

    # Reconfigure stdout/stderr to utf-8 if supported
    import sys
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    # Each CLI run gets its own temp scratch space so blocks from different
    # runs never collide on disk.
    with tempfile.TemporaryDirectory(prefix="securecloud_cli_") as tmp:
        work_dir = Path(tmp)

        result = process_file(INPUT_FILE, work_dir)

        print("\n".join(result["log"]))
        print(
            "\n-> Integrity verification:",
            "PASS [OK]" if result["integrity_pass"] else "FAIL [ERROR]",
        )

        if not result["integrity_pass"]:
            raise RuntimeError("Integrity check failed!")

        print(
            f"\nSUCCESS — {result['block_count']} block(s) processed. "
            "Cloud upload, download and reconstruction completed."
        )


if __name__ == "__main__":
    main()

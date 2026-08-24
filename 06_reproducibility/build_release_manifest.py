"""Create a deterministic SHA-256 manifest for the release tree."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUTPUT = HERE / "release_manifest.csv"
EXCLUDED_PARTS = {".git", "__pycache__", ".pytest_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".tmp"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def category(path: Path) -> str:
    first = path.parts[0] if path.parts else "root"
    return {
        "01_model_core": "model",
        "02_experiment_code": "code",
        "03_data": "data",
        "04_figures": "figure",
        "05_documents": "document",
        "06_reproducibility": "reproducibility",
    }.get(first, "project")


def main() -> int:
    rows = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path == OUTPUT:
            continue
        relative = path.relative_to(ROOT)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if path.suffix.lower() in EXCLUDED_SUFFIXES:
            continue
        rows.append(
            {
                "relative_path": relative.as_posix(),
                "category": category(relative),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["relative_path", "category", "bytes", "sha256"]
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {OUTPUT} with {len(rows)} files (manifest excludes itself)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

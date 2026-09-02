"""Build the Version 3 release file manifest (excluding the manifest itself)."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path


HERE = Path(__file__).resolve().parent
V3_ROOT = HERE.parent
OUTPUT = HERE / "release_manifest_v3.csv"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> int:
    rows: list[dict[str, object]] = []
    for path in sorted(V3_ROOT.rglob("*")):
        if not path.is_file() or path == OUTPUT:
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        relative = path.relative_to(V3_ROOT)
        rows.append(
            {
                "relative_path": relative.as_posix(),
                "category": relative.parts[0],
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["relative_path", "category", "bytes", "sha256"]
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"{OUTPUT}: {len(rows)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

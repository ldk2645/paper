"""Read-only comparison of completed serial/parallel S0 artifact bundles.

Usage: python -B scripts/compare_research_outputs.py SERIAL PARALLEL
Both bundles must first pass the existing integrity and semantic validator.
Only batch identities and manifest execution details are normalized; all other
selected artifacts, including every non-metadata raw file, must match bytewise.
"""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import validate_research_outputs as validator


METADATA_IDENTITIES = {"batch_id", "world_id", "parent_world_id"}
MANIFEST_EXECUTION_FIELDS = {"batch_id", "workers", "started_at", "finished_at"}
FIXED_FILES = {"configuration.json", "resolved_design.json",
               "paired_diagnostics.json", "validation.json"}
DIRECTORIES = {"snapshots", "checks", "derived", "raw"}


def comparison_files(output):
    return {path.relative_to(output).as_posix(): path
            for path in output.rglob("*") if path.is_file()
            and (path.relative_to(output).as_posix() in FIXED_FILES
                 or path.relative_to(output).parts[0] in DIRECTORIES)}


def without_fields(value, fields):
    # Normalize top-level artifact identities only, never nested model data.
    return {key: item for key, item in value.items() if key not in fields}


def compare(left, right):
    left, right = Path(left).resolve(strict=True), Path(right).resolve(strict=True)
    validations = [validator.validate(left), validator.validate(right)]
    manifests = [validator.read(path / "manifest.json") for path in (left, right)]
    validator.require(manifests[0]["source_hash"] == manifests[1]["source_hash"]
                      and manifests[0]["source_sha256"] == manifests[1]["source_sha256"],
                      "Source hash mismatch between batches")

    for name in ("manifest.json", "launch_manifest.json"):
        values = [without_fields(validator.read(path / name), MANIFEST_EXECUTION_FIELDS)
                  for path in (left, right)]
        validator.require(values[0] == values[1], f"Manifest comparison mismatch: {name}")

    files = [comparison_files(path) for path in (left, right)]
    validator.require(set(files[0]) == set(files[1]),
                      f"Comparison file set mismatch; left_only={sorted(set(files[0]) - set(files[1]))}, "
                      f"right_only={sorted(set(files[1]) - set(files[0]))}")
    metadata_count = raw_count = 0
    for relative in sorted(files[0]):
        paths = [mapping[relative] for mapping in files]
        is_raw = relative.startswith("raw/")
        raw_count += is_raw
        if is_raw and len(Path(relative).parts) == 3 and paths[0].name == "metadata.json":
            values = [without_fields(validator.read(path), METADATA_IDENTITIES) for path in paths]
            validator.require(values[0] == values[1], f"Metadata comparison mismatch: {relative}")
            metadata_count += 1
        else:
            validator.require(paths[0].read_bytes() == paths[1].read_bytes(),
                              f"Byte comparison mismatch: {relative}")

    return {"status": "passed", "stage": "S0", "formal_ready": False, "read_only": True,
            "left": str(left), "right": str(right),
            "batch_ids": [manifest["batch_id"] for manifest in manifests],
            "source_hash": manifests[0]["source_hash"],
            "compared_files": len(files[0]) + 2,
            "byte_compared_files": len(files[0]) - metadata_count,
            "normalized_metadata_files": metadata_count, "normalized_manifest_files": 2,
            "raw_files": raw_count,
            "ignored_metadata_fields": sorted(METADATA_IDENTITIES),
            "ignored_manifest_fields": sorted(MANIFEST_EXECUTION_FIELDS),
            "validations": validations,
            "scope": "S0 stored-artifact reproducibility; no fresh simulation or formal release"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    args = parser.parse_args()
    try:
        result = compare(args.left, args.right)
    except (ValueError, TypeError, KeyError, IndexError, OSError) as exc:
        print(json.dumps({"status": "failed", "read_only": True, "error": str(exc)},
                         ensure_ascii=False))
        raise SystemExit(1)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()

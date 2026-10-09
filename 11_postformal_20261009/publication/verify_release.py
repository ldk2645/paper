#!/usr/bin/env python3
"""Read-only verification of the 2026-10-09 supplementary research release.

Usage after publication: python -B publication/verify_release.py
Usage while staging:    python -B verify_release.py --root PATH_TO_RELEASE

The release contains four batch-root provenance files, not the complete raw
batch. This verifies those bindings and reconstructs the published statistical
tables from the validated records. It never calls the raw-batch validator or
runs a simulation. Historical absolute path labels are preserved but never
used to locate inputs. The frozen registry enforces its Python/NumPy versions.

``verify_analysis(root)`` is also available for checking the original project
without a publication manifest; it still reads only the four batch-root files.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import importlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import sys
import time
from unittest.mock import patch

sys.dont_write_bytecode = True

REGISTRY = "postformal/robustness/registry_20261008"
EXECUTION = "postformal/robustness/execution_20261008"
PACKAGE_MANIFEST = "publication/package_manifest.json"
BATCH_ROOT_FILES = frozenset(("manifest.json", "launch.json", "progress.jsonl", "artifact_hashes.json"))
IGNORED_DIRECTORIES = frozenset(("__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".git"))
IGNORED_SUFFIXES = frozenset((".pyc", ".pyo"))
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON key: " + key)
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("Nonfinite JSON constant: " + value)


def _finite_float(value):
    result = float(value)
    require(math.isfinite(result), "Nonfinite JSON number")
    return result


def loads_json(payload):
    return json.loads(payload, object_pairs_hook=_unique_object,
                      parse_constant=_reject_constant, parse_float=_finite_float)


def read_json(path):
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8-sig") as stream:
        return loads_json(stream.read())


def _relative_path(value):
    require(isinstance(value, str) and value and "\\" not in value and ":" not in value,
            "Invalid relative artifact path: " + repr(value))
    relative = PurePosixPath(value)
    require(not relative.is_absolute() and ".." not in relative.parts and
            relative.as_posix() == value and "." not in relative.parts,
            "Unsafe or noncanonical artifact path: " + value)
    return relative


def artifact(root, relative):
    root = Path(root).resolve()
    relative = _relative_path(relative)
    path = root.joinpath(*relative.parts)
    require(path.is_file() and path.resolve().is_relative_to(root), "Missing artifact: " + relative.as_posix())
    cursor = path
    while cursor != root:
        require(not cursor.is_symlink(), "Symlink artifact: " + relative.as_posix())
        cursor = cursor.parent
    return path


def _ignored(relative):
    relative = PurePosixPath(relative)
    return bool(set(relative.parts) & IGNORED_DIRECTORIES) or relative.suffix in IGNORED_SUFFIXES


def listed_files(root, *, ignore_caches=False):
    root = Path(root)
    require(not root.is_symlink() and root.is_dir(), "Missing or symlink directory: " + str(root))
    root = root.resolve()
    result = set()
    for directory, children, files in os.walk(root, followlinks=False):
        for child in list(children):
            path = Path(directory) / child
            relative = path.relative_to(root).as_posix()
            if ignore_caches and _ignored(relative):
                children.remove(child)
                continue
            require(not path.is_symlink(), "Symlink directory: " + relative)
        for filename in files:
            path = Path(directory) / filename
            relative = path.relative_to(root).as_posix()
            if ignore_caches and _ignored(relative):
                continue
            require(not path.is_symlink(), "Symlink artifact: " + relative)
            result.add(relative)
    return result


def verify_package(root):
    """Check the complete published file set, byte sizes, and SHA-256 values."""
    root = Path(root).resolve()
    # Refuse a full raw batch before walking or hashing a release accidentally
    # pointed at the original project. Raw snapshots are deliberately omitted.
    batch = root / EXECUTION / "batch"
    require(batch.is_dir() and {p.name for p in batch.iterdir()} == BATCH_ROOT_FILES and
            all(p.is_file() and not p.is_symlink() for p in batch.iterdir()),
            "Published batch must contain exactly four root provenance files")
    path = artifact(root, PACKAGE_MANIFEST)
    document = read_json(path)
    require(isinstance(document, dict) and isinstance(document.get("files"), list) and document["files"],
            "Invalid or empty package manifest")
    expected, total_bytes = set(), 0
    for entry in document["files"]:
        require(isinstance(entry, dict) and {"path", "bytes", "sha256"} <= set(entry), "Invalid package manifest entry")
        relative = _relative_path(entry["path"]).as_posix()
        require(relative != PACKAGE_MANIFEST and not _ignored(relative) and relative not in expected,
                "Duplicate, excluded, or self-referencing package entry: " + relative)
        require(type(entry["bytes"]) is int and entry["bytes"] >= 0 and
                isinstance(entry["sha256"], str) and SHA256_PATTERN.fullmatch(entry["sha256"]),
                "Invalid package size/hash: " + relative)
        target = artifact(root, relative)
        require(target.stat().st_size == entry["bytes"], "Package byte-size mismatch: " + relative)
        require(sha256(target) == entry["sha256"], "Package SHA-256 mismatch: " + relative)
        expected.add(relative)
        total_bytes += entry["bytes"]
    actual = listed_files(root, ignore_caches=True) - {PACKAGE_MANIFEST}
    require(actual == expected, "Package file set mismatch: missing=" + repr(sorted(expected - actual)[:10]) +
            "; unexpected=" + repr(sorted(actual - expected)[:10]))
    return {"files": len(expected), "bytes": total_bytes, "manifest_hash": sha256(path)}


def verify_inventory(directory):
    """Verify a complete small bundle, including its exact inventory roster."""
    directory = Path(directory)
    inventory_path = artifact(directory, "artifact_hashes.json")
    expected = read_json(inventory_path)
    require(isinstance(expected, dict), "Inventory is not an object: " + str(directory))
    actual = listed_files(directory) - {"artifact_hashes.json"}
    require(actual == set(expected), "Inventory file set mismatch: " + str(directory))
    for relative, digest in expected.items():
        require(isinstance(digest, str) and SHA256_PATTERN.fullmatch(digest), "Invalid inventory digest: " + relative)
        require(sha256(artifact(directory, relative)) == digest, "Inventory SHA-256 mismatch: " + relative)
    return {"files": len(expected), "inventory_hash": sha256(inventory_path)}


def _load_project(root):
    root = Path(root).resolve()
    sys.path.insert(0, str(root))
    names = ("postformal.simulation.registry", "postformal.simulation.analysis",
             "postformal.simulation.common", "abm_jasss.research_config", "abm_jasss.research_world")
    modules = tuple(importlib.import_module(name) for name in names)
    for name, module in zip(names, modules):
        require(Path(module.__file__).resolve().is_relative_to(root),
                "Module was loaded from another project root: " + name)
    return modules


def equal_values(actual, expected, context):
    """Strict comparison preserves null, boolean, integer and float types."""
    require(type(actual) is type(expected), "Type mismatch: " + context)
    if isinstance(expected, dict):
        require(set(actual) == set(expected), "Fields mismatch: " + context)
        for key, value in expected.items():
            equal_values(actual[key], value, context + "." + key)
    elif isinstance(expected, list):
        require(len(actual) == len(expected), "Length mismatch: " + context)
        for index, (left, right) in enumerate(zip(actual, expected)):
            equal_values(left, right, f"{context}[{index}]")
    else:
        require(actual == expected, "Value mismatch: " + context)


def _csv_cell(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def verify_csv(path, rows):
    """Compare every cell using the frozen writer's exact serialization rules."""
    fields = list(dict.fromkeys(key for row in rows for key in row))
    require(bool(fields), "No reconstructed CSV fields")
    count = 0
    with Path(path).open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == fields, "CSV columns differ from reconstruction: " + str(path))
        for count, actual in enumerate(reader, 1):
            require(count <= len(rows), "Unexpected extra CSV row: " + str(path))
            expected = rows[count - 1]
            require(set(actual) == set(fields), "Malformed CSV row: " + str(path))
            for field in fields:
                require(actual[field] == _csv_cell(expected.get(field)),
                        f"Reconstructed CSV mismatch: {Path(path).name}, row {count}, field {field}")
    require(count == len(rows), "Missing CSV rows: " + str(path))


def _verify_batch_roots(root, gate, jobs, common, config):
    """Read only the four published roots; do not validate/hash raw snapshots."""
    batch = root / EXECUTION / "batch"
    for filename in BATCH_ROOT_FILES:
        artifact(batch, filename)
    manifest, launch = read_json(batch / "manifest.json"), read_json(batch / "launch.json")
    archived_inventory = read_json(batch / "artifact_hashes.json")
    require(isinstance(archived_inventory, dict), "Invalid archived batch inventory")
    expected_worlds = sum(len(common.arms(job)) for job in jobs)
    require(manifest["schema"] == "postformal-batch-1" and manifest["stage"] == "postformal_supplement" and
            manifest["status"] == "complete" and manifest["failures"] == [] and
            manifest["code_version"] == config.RESEARCH_VERSION, "Invalid completed batch lifecycle")
    for field in ("registry_hash", "inventory_hash", "source_hash", "extension_source_hash",
                  "dependency_source_hash", "specification_hash"):
        require(manifest[field] == gate[field], "Batch/registry binding mismatch: " + field)
    require(manifest["completed_groups"] == manifest["expected_groups"] == len(jobs) and
            manifest["world_records"] == manifest["expected_world_records"] == expected_worlds,
            "Batch counts differ from registry")
    require(launch["status"] == "running" and launch["completed_groups"] == 0 and launch["failures"] == [],
            "Invalid launch lifecycle")
    for field in ("schema", "stage", "batch_id", "registry_path", "registry_hash", "inventory_hash", "source_hash",
                  "extension_source_hash", "dependency_source_hash", "specification_hash", "code_version",
                  "expected_groups", "expected_world_records", "workers", "started_at"):
        require(launch[field] == manifest[field], "Launch/final batch mismatch: " + field)
    expected_files = {"manifest.json", "launch.json", "progress.jsonl"}
    progress_expected = {}
    for job in jobs:
        group = job["group_id"]
        progress_expected[group] = len(common.arms(job))
        expected_files.update((f"groups/{group}.json", f"initial_arrays/{group}.json",
                               f"mother_snapshots/{group}.json.gz", f"diagnostics/{group}.json"))
        for family, arm, _ in common.arms(job):
            run_id = f"{family}_{group}_{arm}"
            expected_files.update((f"raw/{run_id}/snapshot.json.gz", f"raw/{run_id}/metadata.json",
                                   f"derived/{run_id}.json"))
    require(set(archived_inventory) == expected_files, "Archived raw-batch inventory differs from registered roster")
    for relative, digest in archived_inventory.items():
        _relative_path(relative)
        require(isinstance(digest, str) and SHA256_PATTERN.fullmatch(digest), "Invalid archived batch digest: " + relative)
    for relative in BATCH_ROOT_FILES - {"artifact_hashes.json"}:
        require(sha256(batch / relative) == archived_inventory[relative], "Archived batch-root hash mismatch: " + relative)
    progress_observed = {}
    with (batch / "progress.jsonl").open("r", encoding="utf-8-sig") as stream:
        for line in stream:
            row = loads_json(line)
            group = row["group_id"]
            require(row["status"] == "complete" and group in progress_expected and group not in progress_observed,
                    "Invalid completed progress roster")
            require(type(row["world_records"]) is int, "Invalid progress world count")
            progress_observed[group] = row["world_records"]
    require(progress_observed == progress_expected, "Progress counts differ from registry")
    return manifest, {"groups": len(jobs), "world_records": expected_worlds,
                      "trajectory_records": sum(len(common.arms(job)) * job["model"]["steps"] for job in jobs),
                      "archived_inventory_files": len(archived_inventory),
                      "batch_manifest_hash": sha256(batch / "manifest.json"),
                      "batch_inventory_hash": sha256(batch / "artifact_hashes.json")}


def verify_analysis(root):
    """Verify small provenance bundles and exactly rebuild all published tables."""
    root = Path(root).resolve()
    registry, analysis, common, config, world = _load_project(root)
    registry_path, execution = root / REGISTRY, root / EXECUTION
    gate = registry.validate_registry(registry_path)
    require(gate["status"] == "passed", "Frozen registry did not pass")
    spec = read_json(registry_path / "configuration.json")
    jobs = read_json(registry_path / "resolved_design.json")
    bundle_checks = {name: verify_inventory(execution / name) for name in ("validation", "analysis", "report")}
    batch, batch_check = _verify_batch_roots(root, gate, jobs, common, config)
    validation = read_json(execution / "validation/validation.json")
    summary = read_json(execution / "analysis/summary.json")
    report = read_json(execution / "report/summary.json")
    acceptance = read_json(execution / "acceptance.json")
    validation_hash = sha256(execution / "validation/validation.json")
    require(validation["status"] == "passed" and validation["read_only"] is True and
            validation["stage"] == "postformal_read_only_validation" and
            validation["government_publication_fork_replay_rebuilt"] is True and
            validation["derived_and_no_drift_rebuilt"] is True, "Incomplete original raw-validation evidence")
    for field in ("groups", "world_records", "trajectory_records", "batch_manifest_hash", "batch_inventory_hash"):
        require(validation[field] == batch_check[field], "Validation/batch mismatch: " + field)
    require(validation["hashed_files"] == batch_check["archived_inventory_files"], "Validation inventory count mismatch")
    require(validation["batch_id"] == batch["batch_id"] and validation["registry_hash"] == gate["registry_hash"],
            "Validation identity mismatch")
    require(validation["records_hash"] == sha256(execution / "validation/records.json.gz"), "Validation record binding mismatch")
    require(summary["status"] == "complete" and summary["stage"] == "postformal_analysis" and
            summary["batch_id"] == batch["batch_id"] and summary["batch_inventory_hash"] == batch_check["batch_inventory_hash"] and
            summary["validation_hash"] == validation_hash, "Analysis provenance mismatch")
    for field in ("registry_hash", "source_hash", "extension_source_hash"):
        require(summary[field] == gate[field], "Analysis/registry binding mismatch: " + field)
    require(acceptance["status"] == "passed" and acceptance["validation_hash"] == validation_hash and
            acceptance["registry"] == batch["registry_path"],
            "Acceptance validation binding mismatch")
    equal_values(acceptance["analysis"], summary, "acceptance.analysis")
    require([step["stage"] for step in acceptance["steps"]] == ["run", "validate", "analyze", "report"] and
            all(step["status"] == "passed" for step in acceptance["steps"]), "Acceptance stage roster mismatch")
    for field, value in summary.items():
        require(field in report, "Report omitted analysis field: " + field)
        equal_values(report[field], value, "report." + field)
    require(report["analysis_inventory_hash"] == bundle_checks["analysis"]["inventory_hash"],
            "Report analysis-inventory binding mismatch")
    records = read_json(execution / "validation/records.json.gz")
    require(set(records) == {"records", "auxiliary_records"}, "Unexpected validation-record fields")
    # A defensive guard makes accidental future simulation calls fail closed.
    with patch.object(world.ResearchWorld, "run", side_effect=AssertionError("Verifier must not simulate")), \
         patch.object(world.ResearchWorld, "step", side_effect=AssertionError("Verifier must not simulate")):
        primary, auxiliary, paired = analysis.build_tables(records["records"], records["auxiliary_records"], spec)
    verify_csv(execution / "analysis/primary.csv", primary)
    verify_csv(execution / "analysis/auxiliary.csv", auxiliary)
    equal_values(read_json(execution / "analysis/paired_values.json.gz"), paired, "paired_values")
    require(summary["primary_rows"] == len(primary) == 1362 and summary["auxiliary_rows"] == len(auxiliary) == 3556,
            "Unexpected published table counts")
    require(len(paired) == 272400 and len(records["records"]) == len(records["auxiliary_records"]) == 50800,
            "Unexpected paired or validated record counts")
    families = {}
    for kind, expected_size in (("within_variant", 714), ("effect_change", 648)):
        selected = [row for row in primary if row["analysis_family"] == kind]
        require(len(selected) == expected_size and all(row["holm_family_size"] == expected_size for row in selected),
                "Incorrect fixed Holm family: " + kind)
        families[kind] = {"items": len(selected), "estimated": sum(row["status"] == "estimated" for row in selected),
                          "holm_rejections": sum(row["reject_holm_0_05"] for row in selected),
                          "precision_met": sum(row["observed_target_half_width_met"] is True for row in selected)}
    equal_values(summary["families"], families, "analysis.families")
    pdfs = {p.name for p in (execution / "report").glob("*.pdf")}
    pngs = {p.name for p in (execution / "report").glob("*.png")}
    require(isinstance(report["plots"], list) and len(report["plots"]) == len(set(report["plots"])) and
            set(report["plots"]) == pdfs and {Path(name).stem for name in pdfs} == {Path(name).stem for name in pngs} and
            len(pdfs) == len(pngs) == 48, "Report PDF/PNG roster mismatch")
    require(batch_check["groups"] == 6000 and batch_check["world_records"] == 49200 and
            batch_check["trajectory_records"] == 15420000, "Unexpected registered release counts")
    # Rehash small evidence bundles after rebuilding; never traverse the batch.
    for name, before in bundle_checks.items():
        require(verify_inventory(execution / name) == before, "Evidence changed during verification: " + name)
    require(sha256(execution / "validation/validation.json") == validation_hash, "Validation changed during verification")
    return {"status": "passed", "read_only": True, "simulations_executed": 0,
            "raw_batch_revalidation_performed": False, "registry_hash": gate["registry_hash"],
            "validation_hash": validation_hash, "groups": batch_check["groups"],
            "world_records": batch_check["world_records"], "trajectory_records": batch_check["trajectory_records"],
            "validated_records": len(records["records"]), "primary_rows": len(primary), "auxiliary_rows": len(auxiliary),
            "paired_values": len(paired), "pdf_files": len(pdfs), "png_files": len(pngs), "families": families,
            "small_bundle_inventories": bundle_checks,
            "scope": "Published provenance and exact statistical reconstruction; omitted raw snapshots are covered by the bound original validation report."}


def verify_release(root):
    root = Path(root).resolve()
    package = verify_package(root)
    result = verify_analysis(root)
    require(verify_package(root) == package, "Published package changed during verification")
    result["package"] = package
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1],
                        help="Release root (defaults to the parent of publication/)")
    args = parser.parse_args(argv)
    started = time.perf_counter()
    try:
        report = verify_release(args.root)
        report["seconds"] = round(time.perf_counter() - started, 3)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, allow_nan=False))
    except Exception as error:
        print(json.dumps({"status": "failed", "read_only": True, "error": str(error)}, ensure_ascii=False, sort_keys=True))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

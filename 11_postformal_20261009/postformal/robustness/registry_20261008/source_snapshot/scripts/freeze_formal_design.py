"""Run the full suite and freeze a new formal registry; never simulate formal seeds."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess
import sys
import time
import traceback

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.formal_registry import build_registry, validate_registry, source_inventory
from scripts.precision_artifacts import read, write_json, sha256
from scripts.run_formal_study import plan
from scripts.validate_s1_outputs import require


def freeze(config, protocol, output, acceptance, parent_registry=None):
    output, acceptance = Path(output).resolve(), Path(acceptance).resolve()
    require(not output.exists() and not acceptance.exists(), "Freeze outputs already exist")
    require(output != acceptance and not output.is_relative_to(acceptance)
            and not acceptance.is_relative_to(output), "Freeze and acceptance directories must be separate")
    require(acceptance.is_relative_to(ROOT), "Test evidence must be inside the project")
    require(Path(config).is_file() and Path(protocol).is_file(), "Missing configuration or protocol")
    before = source_inventory()
    acceptance.mkdir(parents=True, exist_ok=False)
    try:
        argv = [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-v"]
        started = time.monotonic()
        print("START full tests; formal seeds are not run", flush=True)
        log_path = acceptance / "tests.log"
        with log_path.open("x", encoding="utf-8", newline="\n") as log:
            result = subprocess.run(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=False)
        content = log_path.read_text(encoding="utf-8-sig")
        counts = re.findall(r"^Ran (\d+) tests? in ", content, re.MULTILINE)
        evidence = {"status": "passed" if result.returncode == 0 else "failed",
            "command": argv, "returncode": result.returncode,
            "tests_run": int(counts[-1]) if counts else 0,
            "source_sha256": before, "log_path": log_path.relative_to(ROOT).as_posix(),
            "log_sha256": sha256(log_path)}
        write_json(acceptance / "tests.json", evidence)
        require(result.returncode == 0 and evidence["tests_run"] > 0 and content.rstrip().endswith("OK"),
                "Full suite failed or evidence was incomplete; inspect tests.log")
        require(source_inventory() == before, "Source changed during full tests; freeze refused")
        print(f"PASS {evidence['tests_run']} tests in {time.monotonic() - started:.1f}s; building frozen registry", flush=True)
        build_registry(config, output, protocol_path=protocol, test_evidence_path=acceptance / "tests.json",
                       parent_registry=parent_registry)
        validation = validate_registry(output)
        write_json(acceptance / "registry_validation.json", validation)
        execution_plan = plan(output)
        require(execution_plan["models_executed"] == 0, "Freeze must not execute formal models")
        write_json(acceptance / "execution_plan.json", execution_plan)
        write_json(acceptance / "acceptance.json", {
            "status": "passed", "stage": "formal_freeze", "formal_ready": True,
            "completed_at": datetime.now(timezone.utc).isoformat(), "models_executed": 0,
            "registry": str(output), "registry_hash": validation["registry_hash"],
            "source_hash": validation["source_hash"], "tests_run": evidence["tests_run"],
            "scope": "Frozen E2/E3/E4 design and guarded execution tools; formal simulation not started"})
    except Exception:
        write_json(acceptance / "failure.json", {"status": "failed", "formal_ready": False,
                                                  "traceback": traceback.format_exc()})
        raise
    finally:
        write_json(acceptance / "evidence_hashes.json", {p.name: sha256(p)
            for p in sorted(acceptance.iterdir()) if p.is_file()})
    print(f"COMPLETE frozen registry: {output}", flush=True)
    return read(acceptance / "acceptance.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/formal_design_20261003.json", type=Path)
    parser.add_argument("--protocol", default="formal_execution_protocol_20261003.md", type=Path)
    parser.add_argument("--output", default="outputs/formal_registry_20261003", type=Path)
    parser.add_argument("--acceptance", default="outputs/formal_freeze_acceptance_20261003", type=Path)
    parser.add_argument("--parent-registry", type=Path,
                        help="Preserve an existing frozen registration for a verified software repair")
    args = parser.parse_args()
    freeze(args.config, args.protocol, args.output, args.acceptance, args.parent_registry)

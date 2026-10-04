"""Build and inspect a frozen formal design without running model worlds."""
import argparse
import ast
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import platform
from pathlib import Path
import re
import shutil
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from abm_jasss.research_config import ResearchConfig, RESEARCH_VERSION
from abm_jasss.research_world import canonical_hash, jsonable, source_hash
from scripts.precision_artifacts import read, write_json
from scripts.run_precision_pilot import CONTRASTS, PRIMARY, analysis_spec, resolve_design
from scripts.validate_s1_outputs import require


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _relative_file(root, relative):
    """Require a real file below the chosen project/package root."""
    root = Path(root).resolve()
    require(isinstance(relative, str) and relative and "\\" not in relative,
            "Artifact paths must be nonempty POSIX relative paths")
    path = root / relative
    require(not Path(relative).is_absolute() and ".." not in Path(relative).parts,
            "Artifact path escapes its root")
    require(path.is_file() and path.resolve().is_relative_to(root), f"Missing artifact: {relative}")
    require(not path.is_symlink() and not any(p.is_symlink() for p in path.parents if p != root),
            "Symlinks are not permitted in a registry")
    return path


def source_inventory(root=ROOT):
    """Hash exact executable code, tests and the pinned dependency declaration."""
    root = Path(root)
    paths = [path for folder in ("abm_jasss", "scripts", "tests")
             for path in sorted((root / folder).rglob("*.py"))]
    paths.append(root / "requirements.txt")
    require(all(path.is_file() and not path.is_symlink() for path in paths), "Missing source files")
    return {path.relative_to(root).as_posix(): sha256(path) for path in paths}


def _seed_values(value, key=""):
    if isinstance(value, dict):
        for name, nested in value.items():
            yield from _seed_values(nested, name)
    elif isinstance(value, list):
        for nested in value:
            yield from _seed_values(nested, key)
    elif type(value) is int and (key == "seed" or key.endswith("_seed") or key == "seeds"
                                or key.endswith("_seeds") or key in {"parent_id", "parent_ids"}):
        yield value


def audit_seeds(seeds, *, root=ROOT, exclude=()):
    """Audit historical JSON seed fields and conservative source integer literals.

    Source literals are a fail-closed supplement for development/test calls;
    they do not claim to statically evaluate arbitrary Python programs.
    """
    root = Path(root).resolve()
    excluded = {Path(path).resolve() for path in exclude}
    candidates = set(seeds)
    require(len(candidates) == len(seeds) and all(type(s) is int and s >= 0 for s in seeds),
            "Formal seeds must be unique nonnegative integers")
    documents = set((root / "configs").rglob("*.json"))
    names = {"configuration.json", "metadata.json", "manifest.json", "suite_manifest.json",
             "resolved_design.json", "acceptance.json", "seed_registry.json"}
    documents.update(path for path in (root / "outputs").rglob("*.json") if path.name in names
                     and "source_snapshot" not in path.parts)
    sources = {path for folder in ("abm_jasss", "scripts", "tests")
               for path in (root / folder).rglob("*.py")}
    used, inputs, collisions = set(), {}, []
    for path in sorted(documents | sources):
        if path.resolve() in excluded:
            continue
        relative = path.relative_to(root).as_posix()
        inputs[relative] = sha256(path)
        if path.suffix == ".json":
            values = set(_seed_values(read(path)))
            used.update(values)
            overlap = candidates & values
            method = "json_seed_fields"
        else:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=relative)
            values = {node.value for node in ast.walk(tree)
                      if isinstance(node, ast.Constant) and type(node.value) is int}
            overlap = candidates & values
            method = "conservative_python_integer_literals"
        if overlap:
            collisions.append({"path": relative, "method": method, "seeds": sorted(overlap)})
    require(inputs, "Seed audit found no historical or source inputs")
    return {"schema_version": "formal-seed-audit-1", "status": "passed" if not collisions else "failed",
            "candidate_count": len(seeds), "candidate_hash": canonical_hash(seeds),
            "historical_seed_count": len(used), "historical_seeds": sorted(used),
            "checked_files": inputs, "collisions": collisions,
            "scope": "Recorded config/output seed fields and conservative source integer literals; no model runs"}


SPEC_FIELDS = {"schema_version", "stage", "formal_ready", "expected_source_hash", "model", "alphas",
               "fork_tick", "branches", "precision", "stability", "metrics", "contrasts",
               "sample_sizes", "seeds", "inference", "budget_decision", "evidence"}
REQUIRED_SCRIPTS = {"formal_inference.py", "formal_runtime.py", "formal_artifacts.py",
                    "run_formal_study.py", "formal_registry.py"}
CONTRACTS = ("ODD_research.md", "signal_and_outcome_contract.md", "research_engine.md",
             "precision_pilot_protocol_20260930.md", "precision_pilot_validation_20261002.md",
             "s0_validation_20260928.md", "s1_validation_20260929.md")


def resolve_formal_design(spec):
    """Resolve fixed nested seed strata; neither sample count depends on outcomes."""
    from scripts.formal_inference import INFERENCE_POLICY
    require(isinstance(spec, dict) and set(spec) == SPEC_FIELDS, "Unknown/missing formal specification fields")
    require(spec["schema_version"] == "formal-design-1" and spec["stage"] == "formal_design"
            and spec["formal_ready"] is False, "Expected an unactivated formal design template")
    require(isinstance(spec["expected_source_hash"], str)
            and re.fullmatch("[0-9a-f]{64}", spec["expected_source_hash"]), "Invalid engine source hash")
    cfg = ResearchConfig.from_dict(spec["model"])
    require(jsonable(cfg.to_dict()) == spec["model"], "Formal model must contain every resolved field")
    require(spec["alphas"] == [.25, .75] and spec["sample_sizes"] == {"0.25": 184, "0.75": 1000},
            "Registered shared sample sizes/alpha strata changed")
    seeds = spec["seeds"]
    require(isinstance(seeds, list) and len(seeds) == 1000 and len(set(seeds)) == 1000
            and all(type(seed) is int and seed >= 0 for seed in seeds), "Invalid formal seed registry")
    require(seeds == list(range(seeds[0], seeds[0] + 1000)) and cfg.reference_seed not in seeds,
            "Formal seeds must be an ordered consecutive unused registry")
    require(spec["metrics"] == PRIMARY and spec["contrasts"] == CONTRASTS,
            "Registered metrics/contrasts changed")
    require(spec["inference"] == INFERENCE_POLICY, "Formal inference policy is missing or changed")
    require(spec["precision"] == {"target_half_width": .02, "min_valid": 30, "max_total": 1000},
            "Registered precision policy changed")
    require(spec["budget_decision"] == {"policy": "retain_registered_cap", "max_total": 1000,
            "accepted_budget_limited_items": 3, "retained_variance_unstable_items": 61,
            "user_authorized": True, "authorization_date": "2026-10-02"},
            "Budget shortfalls and unstable items must be explicitly retained")
    require(set(spec["evidence"]) == {"pilot_config", "pilot_initial", "pilot_expansion",
                                        "pilot_acceptance", "pilot_planning"}, "Missing pilot evidence registry")
    # Reuse the registered pilot treatment/timing contract without running it.
    pilot = {key: spec[key] for key in ("expected_source_hash", "model", "alphas", "fork_tick",
                                      "branches", "precision", "stability")}
    pilot.update(stage="precision_pilot", formal_ready=False,
                 initial_seeds=seeds[:500], expansion_seeds=seeds[500:])
    resolve_design(pilot, "initial")
    require(cfg.n_agents == 100 and cfg.steps == 300 and cfg.final_window == 100
            and spec["fork_tick"] == 150 and cfg.completion_start == 150
            and cfg.completion_end == 279 and cfg.completion_followup == 20,
            "Registered population/horizon/evaluation window changed")
    return [{"group_id": f"a{index:02d}_seed{seed}", "seed": seed, "alpha": alpha,
             "model": jsonable(replace(cfg, alpha=alpha).to_dict()), "fork_tick": spec["fork_tick"],
             "branches": spec["branches"]} for index, alpha in enumerate(spec["alphas"])
            for seed in seeds[:spec["sample_sizes"][str(alpha)]]]


def inference_spec(spec):
    resolve_formal_design(spec)
    return {"alphas": spec["alphas"], "parent_ids_by_alpha": {
                str(alpha): spec["seeds"][:spec["sample_sizes"][str(alpha)]] for alpha in spec["alphas"]},
            "metrics": spec["metrics"], "contrasts": spec["contrasts"], "inference": spec["inference"]}


def _pilot_evidence(spec, root):
    """Bind accepted pilot inventories and rebuild all sample-planning decisions."""
    from scripts.precision_statistics import build_precision_analysis, assess_precision_stability
    files = {}

    def take(relative):
        path = _relative_file(root, relative)
        files[relative] = path
        return read(path)

    def inventory(directory, filename="artifact_hashes.json", exact=False):
        hashes = take(f"{directory}/{filename}")
        require(isinstance(hashes, dict), "Invalid pilot inventory")
        if exact:
            paths = {p.relative_to(Path(root) / directory).as_posix()
                     for p in (Path(root) / directory).rglob("*") if p.is_file()}
            require(paths == set(hashes) | {filename}, "Pilot evidence inventory mismatch")
            for relative, digest in hashes.items():
                path = _relative_file(root, f"{directory}/{relative}")
                require(sha256(path) == digest, "Pilot evidence hash mismatch")
                files[f"{directory}/{relative}"] = path
        return hashes

    evidence = spec["evidence"]
    pilot = take(evidence["pilot_config"])
    for key in ("model", "alphas", "fork_tick", "branches", "precision", "stability", "expected_source_hash"):
        require(spec[key] == pilot[key], f"Formal design differs from planned pilot: {key}")
    planning_dir, acceptance_dir = evidence["pilot_planning"], evidence["pilot_acceptance"]
    inventory(planning_dir, exact=True)
    inventory(acceptance_dir, "evidence_hashes.json", exact=True)
    analysis_manifest = take(f"{planning_dir}/analysis_manifest.json")
    acceptance = take(f"{acceptance_dir}/acceptance.json")
    require(acceptance["status"] == "passed" and acceptance["stage"] == "precision_pilot"
            and acceptance["formal_ready"] is False, "Pilot acceptance is incomplete")
    require(analysis_manifest["semantic_validation_complete"] is True
            and analysis_manifest["source_hash"] == spec["expected_source_hash"]
            and analysis_manifest["specification_hash"] == canonical_hash(pilot), "Pilot planning is not accepted")
    records, analyses, batch_ids = [], [], []
    for wave in ("initial", "expansion"):
        directory = evidence[f"pilot_{wave}"]
        hashes = inventory(directory)

        def wave_file(name):
            value = take(f"{directory}/{name}")
            require(name in hashes and sha256(files[f"{directory}/{name}"]) == hashes[name],
                    f"Pilot wave hash mismatch: {wave}/{name}")
            return value

        manifest = wave_file("manifest.json")
        require(manifest["stage"] == "precision_pilot" and manifest["status"] == "complete"
                and manifest["formal_ready"] is False and manifest["wave"] == wave
                and manifest["failed_groups"] == 0 and manifest["source_hash"] == spec["expected_source_hash"],
                "Pilot wave is incomplete or has a different engine")
        require(canonical_hash(manifest["source_sha256"]) == spec["expected_source_hash"],
                "Pilot engine inventory/source hash mismatch")
        require(wave_file("configuration.json") == pilot == manifest["specification"],
                "Pilot wave configuration mismatch")
        jobs = jsonable(resolve_design(pilot, wave))
        require(wave_file("resolved_design.json") == jobs and manifest["expected_groups"] == len(jobs)
                and manifest["completed_groups"] == len(jobs) and manifest["complete_records"] == 18 * len(jobs)
                and wave_file("failures.json") == [], "Incomplete pilot world registry")
        report = take(f"{acceptance_dir}/validate_{wave}.json")
        binding = analysis_manifest["validation"][wave]
        require(report["status"] == "passed" and report["read_only"] is True
                and report["formal_ready"] is False and report["batch_id"] == manifest["batch_id"]
                and report["source_hash"] == spec["expected_source_hash"]
                and report["manifest_hash"] == sha256(files[f"{directory}/manifest.json"])
                and report["artifact_inventory_hash"] == sha256(files[f"{directory}/artifact_hashes.json"]),
                "Stale or mismatched pilot validation report")
        require(binding["passed"] is True and binding["sha256"] == sha256(files[f"{acceptance_dir}/validate_{wave}.json"])
                and binding["artifact_inventory_hash"] == report["artifact_inventory_hash"],
                "Pilot planning/validation binding mismatch")
        inputs = analysis_manifest["input_batches"][wave]
        require(inputs["batch_id"] == manifest["batch_id"]
                and inputs["input_hashes"]["artifact_hashes.json"] == report["artifact_inventory_hash"],
                "Pilot planning input binding mismatch")
        wave_records = wave_file("statistical_records.json")
        rebuilt = build_precision_analysis(wave_records, analysis_spec(pilot, pilot[wave + "_seeds"]))
        require(rebuilt == wave_file("precision_analysis.json"), "Pilot precision reconstruction mismatch")
        records.extend(wave_records)
        analyses.append(rebuilt)
        batch_ids.append(manifest["batch_id"])
    require(len(set(batch_ids)) == 2, "Pilot waves must be distinct")
    combined = build_precision_analysis(records, analysis_spec(pilot, pilot["initial_seeds"] + pilot["expansion_seeds"]))
    stability = assess_precision_stability(analyses[0], combined, **pilot["stability"])
    require(combined == take(f"{planning_dir}/planning.json")
            and stability == take(f"{planning_dir}/stability.json"), "Combined pilot planning does not reconstruct")
    shortfalls = [{"family": group["family"], "alpha": group["alpha"], "contrast": contrast,
                   "metric": metric, "required_total_uncapped": item["precision_plan"]["required_total_uncapped"]}
                  for group in combined["groups"] for contrast, metrics in group["contrasts"].items()
                  for metric, item in metrics.items() if item["precision_plan"]["budget_capped"]]
    unstable = [item for item in stability["items"] if not item["stable"]]
    require(len(shortfalls) == spec["budget_decision"]["accepted_budget_limited_items"]
            and len(unstable) == spec["budget_decision"]["retained_variance_unstable_items"],
            "Budget shortfall/stability decision differs from actual pilot evidence")
    require({str(item["alpha"]): item["fixed_total"] for item in combined["shared_by_alpha"]}
            == spec["sample_sizes"], "Formal sample sizes differ from retained-cap pilot planning")
    require(len(stability["items"]) == 102 and all(group["shared_plan"]["operationally_complete"]
            for group in combined["groups"]), "Missing registered pilot comparisons")
    return files, {"status": "passed", "planning_items": 102, "budget_limited_items": shortfalls,
                   "variance_unstable_items": len(unstable), "pilot_batch_ids": batch_ids,
                   "scope": "Accepted raw-inventory bindings and independent summary/planning reconstruction"}


def _test_evidence(path, root, sources):
    report = read(path)
    expected = {"status", "command", "returncode", "tests_run", "source_sha256", "log_path", "log_sha256"}
    require(isinstance(report, dict) and set(report) == expected, "Invalid final test evidence schema")
    require(report["status"] == "passed" and report["returncode"] == 0
            and type(report["tests_run"]) is int and report["tests_run"] > 0,
            "Final tests did not pass")
    require(report["source_sha256"] == sources, "Final test evidence does not cover current source")
    command = report["command"]
    require(isinstance(command, list) and all(isinstance(arg, str) for arg in command)
            and "unittest" in command and "discover" in command and "tests" in command
            and "-p" not in command, "Final evidence must cover the full unittest suite")
    log = _relative_file(root, report["log_path"])
    require(sha256(log) == report["log_sha256"], "Final test log hash mismatch")
    content = log.read_text(encoding="utf-8-sig")
    match = re.search(r"Ran (\d+) tests? in [^\r\n]+[\r\n]+\s*OK\s*\Z", content)
    require(match is not None and int(match[1]) == report["tests_run"], "Final test log is incomplete or inconsistent")
    # Failure-path tests legitimately print messages such as 'FAILED <run_id>'.
    # Reject unittest failure summaries, not arbitrary application log words.
    require(not re.search(r"^(?:FAILED \(|ERROR: |FAIL: |UNEXPECTED SUCCESS: )", content, re.MULTILINE),
            "Final test evidence contains unresolved tests")
    return report, log


def _seed_registry(spec):
    return {"schema_version": "formal-seeds-1", "independent_seeds": spec["seeds"],
            "parent_ids_by_alpha": inference_spec(spec)["parent_ids_by_alpha"],
            "shared_across_families": list(CONTRASTS), "cross_alpha_pairing": "nested_prefix",
            "cross_alpha_inference": False, "replacement_or_additional_sampling": False}


def build_registry(config_path, output, *, protocol_path, test_evidence_path, root=ROOT):
    """Create a new registry only after concrete source, evidence and seed gates pass."""
    import numpy as np
    root = Path(root).resolve()
    output = Path(output).resolve()
    require(not output.exists(), "Registry output already exists; preserve immutable freezes")
    config_path, protocol_path, test_evidence_path = map(Path, (config_path, protocol_path, test_evidence_path))
    config_path = config_path if config_path.is_absolute() else root / config_path
    protocol_path = protocol_path if protocol_path.is_absolute() else root / protocol_path
    test_evidence_path = test_evidence_path if test_evidence_path.is_absolute() else root / test_evidence_path
    for path in (config_path, protocol_path, test_evidence_path):
        require(path.resolve().is_relative_to(root), "Freeze inputs must be inside the project")
        _relative_file(root, path.relative_to(root).as_posix())
    spec = read(config_path)
    jobs = resolve_formal_design(spec)
    sources = source_inventory(root)
    require(all(f"scripts/{name}" in sources for name in REQUIRED_SCRIPTS),
            "Formal runtime, artifact, inference and guarded entry scripts are required")
    require(all(f"tests/{name}" in sources for name in ("test_formal_registry.py", "test_formal_inference.py")),
            "Formal registry and inference tests are required")
    engine = {Path(name).name: digest for name, digest in sources.items() if name.startswith("abm_jasss/")}
    require(canonical_hash(engine) == spec["expected_source_hash"] == source_hash(),
            "Live engine differs from the frozen pilot engine")
    test_report, test_log = _test_evidence(test_evidence_path, root, sources)
    evidence_files, pilot_check = _pilot_evidence(spec, root)
    seed_audit = audit_seeds(spec["seeds"], root=root, exclude=(config_path,))
    require(seed_audit["status"] == "passed", f"Formal seed collision: {seed_audit['collisions']}")
    documents = {name: _relative_file(root, name) for name in CONTRACTS}
    documents[protocol_path.relative_to(root).as_posix()] = protocol_path
    documents[config_path.relative_to(root).as_posix()] = config_path
    require(protocol_path.read_text(encoding="utf-8-sig").strip(), "Formal protocol must not be empty")
    for stage in ("s0", "s1"):
        relative = f"outputs/research_{stage}_acceptance_202609{28 if stage == 's0' else 29}/acceptance.json"
        path = _relative_file(root, relative)
        accepted = read(path)
        require(accepted["status"] == "passed" and accepted["stage"] == stage.upper(),
                f"Missing passed {stage.upper()} technical acceptance")
        if stage == "s1":
            require(accepted["source_hash"] == spec["expected_source_hash"], "S1 accepted a different engine")
        evidence_files[relative] = path
    evidence_files[test_log.relative_to(root).as_posix()] = test_log
    copy_plan = {f"source_snapshot/{name}": root / name for name in sources}
    copy_plan.update({f"source_snapshot/{name}": path for name, path in documents.items()})
    copy_plan.update({f"evidence/project/{name}": path for name, path in evidence_files.items()})
    copy_plan["evidence/final_tests.json"] = test_evidence_path
    input_hashes = {name: sha256(path) for name, path in copy_plan.items()}
    require(source_inventory(root) == sources, "Source changed during registry preflight")
    manifest = {
        "schema_version": "formal-registry-1", "stage": "formal_design", "status": "frozen",
        "formal_ready": True, "physical_worlds_executed": 0,
        "created_at": datetime.now(timezone.utc).isoformat(), "code_version": RESEARCH_VERSION,
        "source_hash": spec["expected_source_hash"], "source_sha256": sources,
        "specification_hash": canonical_hash(spec), "resolved_design_hash": canonical_hash(jobs),
        "seed_registry_hash": canonical_hash(_seed_registry(spec)), "seed_audit_hash": canonical_hash(seed_audit),
        "sample_sizes": spec["sample_sizes"], "expected_groups": len(jobs),
        "expected_world_records": 18 * len(jobs), "independent_seeds": len(spec["seeds"]),
        "protocol_path": protocol_path.relative_to(root).as_posix(),
        "configuration_path": config_path.relative_to(root).as_posix(),
        "document_sha256": {name: sha256(path) for name, path in documents.items()},
        "evidence_sha256": {name: digest for name, digest in input_hashes.items() if name.startswith("evidence/")},
        "python": platform.python_version(), "numpy": np.__version__,
        "gates": {"complete_configuration": True, "accepted_pilot": True, "accepted_budget_shortfalls": True,
                  "unused_seed_registry": True, "frozen_inference": True, "guarded_runtime_present": True,
                  "final_tests_passed": True, "technical_acceptance": True},
        "tests_run": test_report["tests_run"], "pilot_check": pilot_check,
        "readiness_scope": "Registered E2, E3_closed, E3_replay and E4 execution/analysis design only; no formal results",
        "not_in_scope": ["cross_alpha_inference", "dynamic_recovery", "structural_robustness", "trust_warning"],
    }
    output.mkdir(parents=True, exist_ok=False)
    for relative, source in copy_plan.items():
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as incoming, destination.open("xb") as outgoing:
            shutil.copyfileobj(incoming, outgoing)
        require(sha256(destination) == input_hashes[relative] == sha256(source),
                f"Freeze input changed while archiving: {relative}")
    for name, value in (("configuration.json", spec), ("resolved_design.json", jobs),
                        ("inference_spec.json", inference_spec(spec)), ("seed_registry.json", _seed_registry(spec)),
                        ("seed_audit.json", seed_audit), ("manifest.json", manifest)):
        write_json(output / name, value)
    write_json(output / "artifact_hashes.json", {path.relative_to(output).as_posix(): sha256(path)
               for path in sorted(output.rglob("*")) if path.is_file()})
    return validate_registry(output, root=root)


def validate_registry(output, *, root=ROOT, check_live=True):
    """Read-only validation; construction or stepping of physical worlds is forbidden."""
    root, output = Path(root).resolve(), Path(output)
    require(not output.is_symlink(), "Symlinks are not permitted in a registry")
    output = output.resolve(strict=True)
    paths = list(output.rglob("*"))
    require(not any(path.is_symlink() for path in paths), "Symlinks are not permitted in a registry")
    files = {path.relative_to(output).as_posix(): path for path in paths if path.is_file()}
    inventory_path = output / "artifact_hashes.json"
    inventory_hash = sha256(inventory_path)
    inventory = read(inventory_path)
    require(set(inventory) == set(files) - {"artifact_hashes.json"}, "Registry artifact inventory mismatch")
    for name, digest in inventory.items():
        require(sha256(files[name]) == digest, f"Registry artifact hash mismatch: {name}")
    manifest, spec = read(output / "manifest.json"), read(output / "configuration.json")
    require(manifest["schema_version"] == "formal-registry-1" and manifest["stage"] == "formal_design"
            and manifest["status"] == "frozen" and manifest["formal_ready"] is True
            and manifest["physical_worlds_executed"] == 0 and manifest["code_version"] == RESEARCH_VERSION,
            "Registry is not a completed formal design freeze")
    jobs = resolve_formal_design(spec)
    require(canonical_hash(spec) == manifest["specification_hash"]
            and read(output / "resolved_design.json") == jobs
            and canonical_hash(jobs) == manifest["resolved_design_hash"], "Frozen configuration/design mismatch")
    require(read(output / "inference_spec.json") == inference_spec(spec), "Frozen inference specification mismatch")
    seeds = _seed_registry(spec)
    require(read(output / "seed_registry.json") == seeds and canonical_hash(seeds) == manifest["seed_registry_hash"],
            "Frozen seed registry mismatch")
    audit = read(output / "seed_audit.json")
    require(audit["status"] == "passed" and audit["collisions"] == [] and audit["checked_files"]
            and audit["candidate_hash"] == canonical_hash(spec["seeds"])
            and audit["candidate_count"] == len(spec["seeds"])
            and not set(audit["historical_seeds"]) & set(spec["seeds"])
            and canonical_hash(audit) == manifest["seed_audit_hash"], "Frozen seed audit failed")
    sources = source_inventory(output / "source_snapshot")
    require(sources == manifest["source_sha256"] and all(f"scripts/{name}" in sources for name in REQUIRED_SCRIPTS),
            "Archived formal source inventory mismatch")
    engine = {Path(name).name: digest for name, digest in sources.items() if name.startswith("abm_jasss/")}
    require(canonical_hash(engine) == manifest["source_hash"] == spec["expected_source_hash"] == source_hash(),
            "Frozen engine source mismatch")
    if check_live:
        require(source_inventory(root) == sources, "Live source differs from the formal freeze")
    for name, digest in manifest["document_sha256"].items():
        require(sha256(_relative_file(output / "source_snapshot", name)) == digest,
                "Archived protocol/configuration/contract hash mismatch")
        if check_live:
            require(sha256(_relative_file(root, name)) == digest, "Live protocol/configuration/contract differs from freeze")
    require(set(CONTRACTS) | {manifest["protocol_path"], manifest["configuration_path"]}
            == set(manifest["document_sha256"]), "Frozen document registry is incomplete")
    require(read(output / "source_snapshot" / manifest["configuration_path"]) == spec,
            "Archived configuration differs from registered configuration")
    for name, digest in manifest["evidence_sha256"].items():
        require(name.startswith("evidence/") and sha256(_relative_file(output, name)) == digest,
                "Frozen evidence hash mismatch")
    test_report, _ = _test_evidence(output / "evidence/final_tests.json", output / "evidence/project", sources)
    _, pilot_check = _pilot_evidence(spec, output / "evidence/project")
    require(pilot_check == manifest["pilot_check"] and test_report["tests_run"] == manifest["tests_run"],
            "Frozen readiness evidence does not reconstruct")
    expected_gates = {"complete_configuration", "accepted_pilot", "accepted_budget_shortfalls",
                      "unused_seed_registry", "frozen_inference", "guarded_runtime_present",
                      "final_tests_passed", "technical_acceptance"}
    require(set(manifest["gates"]) == expected_gates and all(value is True for value in manifest["gates"].values()),
            "Formal readiness gates are incomplete")
    require(manifest["expected_groups"] == len(jobs) == 1184
            and manifest["expected_world_records"] == 18 * len(jobs)
            and manifest["independent_seeds"] == len(spec["seeds"])
            and manifest["sample_sizes"] == spec["sample_sizes"], "Formal sample accounting mismatch")
    require(sha256(inventory_path) == inventory_hash, "Registry inventory changed during validation")
    return {"status": "passed", "formal_ready": True, "read_only": True, "registry_path": str(output),
            "registry_hash": sha256(output / "manifest.json"), "artifact_inventory_hash": inventory_hash,
            "specification_hash": manifest["specification_hash"], "source_hash": manifest["source_hash"],
            "jobs_count": len(jobs), "manifest": manifest}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("--config", required=True, type=Path)
    build.add_argument("--protocol", required=True, type=Path)
    build.add_argument("--test-evidence", required=True, type=Path)
    build.add_argument("--output", required=True, type=Path)
    check = commands.add_parser("validate")
    check.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        result = (build_registry(args.config, args.output, protocol_path=args.protocol,
                                test_evidence_path=args.test_evidence) if args.command == "build"
                  else validate_registry(args.output))
    except (ValueError, TypeError, KeyError, IndexError, OSError) as error:
        print(json.dumps({"status": "failed", "formal_ready": False, "error": str(error)}, ensure_ascii=False))
        raise SystemExit(1)
    print(json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()

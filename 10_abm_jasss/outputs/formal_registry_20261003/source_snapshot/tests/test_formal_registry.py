"""Formal freeze gates and immutable provenance; no formal model worlds run."""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from abm_jasss.research_world import ResearchWorld, canonical_hash
from scripts.formal_inference import INFERENCE_POLICY
from scripts.formal_registry import (CONTRACTS, REQUIRED_SCRIPTS, ROOT, audit_seeds, build_registry,
    inference_spec, read, resolve_formal_design, sha256, source_inventory, validate_registry)
from scripts.run_precision_pilot import CONTRASTS, PRIMARY


def registered_spec():
    pilot = read(ROOT / "configs/precision_pilot_20260930.json")
    # These are declarations only: none of the registered seeds is simulated.
    first_seed = pilot["initial_seeds"][0] + 10_000
    return {"schema_version": "formal-design-1", "stage": "formal_design", "formal_ready": False,
            **{key: deepcopy(pilot[key]) for key in ("expected_source_hash", "model", "alphas", "fork_tick",
                                                   "branches", "precision", "stability")},
            "metrics": list(PRIMARY), "contrasts": deepcopy(CONTRASTS),
            "sample_sizes": {"0.25": 184, "0.75": 1000}, "seeds": list(range(first_seed, first_seed + 1000)),
            "inference": deepcopy(INFERENCE_POLICY),
            "budget_decision": {"policy": "retain_registered_cap", "max_total": 1000,
                "accepted_budget_limited_items": 3, "retained_variance_unstable_items": 61,
                "user_authorized": True, "authorization_date": "2026-10-02"},
            "evidence": {"pilot_config": "configs/precision_pilot_20260930.json",
                "pilot_initial": "outputs/precision_pilot_20261002_initial",
                "pilot_expansion": "outputs/precision_pilot_20261002_expansion",
                "pilot_acceptance": "outputs/precision_pilot_20261002_acceptance",
                "pilot_planning": "outputs/precision_pilot_20261002_planning"}}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False), encoding="utf-8")


class FormalSpecificationTests(unittest.TestCase):
    def test_registered_nested_samples_are_explicit_without_simulation(self):
        spec = registered_spec()
        with patch.object(ResearchWorld, "__init__", side_effect=AssertionError("physical construction")):
            jobs = resolve_formal_design(spec)
        self.assertEqual(len(jobs), 1184)
        self.assertEqual(len({job["seed"] for job in jobs}), 1000)
        first = [job["seed"] for job in jobs if job["alpha"] == .25]
        second = [job["seed"] for job in jobs if job["alpha"] == .75]
        self.assertEqual(first, second[:184])
        self.assertEqual(inference_spec(spec)["parent_ids_by_alpha"], {"0.25": first, "0.75": second})
        self.assertFalse(spec["formal_ready"])

    def test_incomplete_or_changed_registration_is_rejected(self):
        spec = registered_spec()
        variants = []
        for field in ("model", "inference", "budget_decision", "metrics", "evidence"):
            value = deepcopy(spec)
            del value[field]
            variants.append(value)
        for mutate in (
                lambda v: v.update(formal_ready=True),
                lambda v: v["sample_sizes"].update({"0.75": 1293}),
                lambda v: v["model"].pop("reference_agents"),
                lambda v: v["inference"].update(multiplicity_method="none"),
                lambda v: v["budget_decision"].update(accepted_budget_limited_items=0),
                lambda v: v["seeds"].__setitem__(1, v["seeds"][0]),
                lambda v: v["metrics"].pop(),
                lambda v: v["branches"]["B2"].update(government_delay=2)):
            value = deepcopy(spec)
            mutate(value)
            variants.append(value)
        for index, value in enumerate(variants):
            with self.subTest(index=index), self.assertRaises((ValueError, TypeError)):
                resolve_formal_design(value)

    def test_seed_audit_covers_nested_metadata_and_test_literals(self):
        seeds = registered_spec()["seeds"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write(root / "configs/prior.json", {"model": {"reference_seed": seeds[0]}})
            write(root / "outputs/old/raw/r/metadata.json", {"seed": seeds[1]})
            source = root / "tests/test_old.py"
            source.parent.mkdir(parents=True)
            source.write_text(f"WORLD_SEED = {seeds[2]}\n", encoding="utf-8")
            report = audit_seeds(seeds, root=root)
            self.assertEqual(report["status"], "failed")
            self.assertEqual({seed for item in report["collisions"] for seed in item["seeds"]}, set(seeds[:3]))
            self.assertEqual(report["candidate_hash"], canonical_hash(seeds))


class FormalRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name) / "project"
        cls.root.mkdir()
        cls.spec = registered_spec()
        sources = source_inventory(ROOT)
        for relative in sources:
            destination = cls.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
        # The fixture records test evidence against this synthetic project only;
        # it is never used as production evidence or a formal execution input.
        for name in REQUIRED_SCRIPTS:
            path = cls.root / "scripts" / name
            if not path.exists():
                path.write_text('"""Unexecuted fixture source."""\n', encoding="utf-8")
        for name in ("test_formal_registry.py", "test_formal_inference.py"):
            path = cls.root / "tests" / name
            if not path.exists():
                path.write_text('"""Unexecuted fixture test."""\n', encoding="utf-8")
        for relative in CONTRACTS:
            shutil.copyfile(ROOT / relative, cls.root / relative)
        cls.config = cls.root / "configs/fixture_formal.json"
        write(cls.config, cls.spec)
        pilot_config = cls.spec["evidence"]["pilot_config"]
        (cls.root / pilot_config).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / pilot_config, cls.root / pilot_config)
        for key in ("pilot_acceptance", "pilot_planning"):
            relative = cls.spec["evidence"][key]
            shutil.copytree(ROOT / relative, cls.root / relative)
        for wave in ("initial", "expansion"):
            relative = cls.spec["evidence"][f"pilot_{wave}"]
            target = cls.root / relative
            target.mkdir(parents=True)
            for name in ("artifact_hashes.json", "configuration.json", "manifest.json", "resolved_design.json",
                         "failures.json", "statistical_records.json", "precision_analysis.json"):
                shutil.copyfile(ROOT / relative / name, target / name)
        for relative in ("outputs/research_s0_acceptance_20260928/acceptance.json",
                         "outputs/research_s1_acceptance_20260929/acceptance.json"):
            target = cls.root / relative
            target.parent.mkdir(parents=True)
            shutil.copyfile(ROOT / relative, target)
        cls.protocol = cls.root / "fixture_protocol.md"
        cls.protocol.write_text("# Fixture frozen E2–E4 protocol\n", encoding="utf-8")
        cls.log = cls.root / "outputs/final_tests/tests.log"
        cls.log.parent.mkdir(parents=True)
        cls.log.write_text("FAILED fixture_expected_application_failure\nRan 999 tests in 1.0s\n\nOK\n", encoding="utf-8")
        cls.evidence = cls.log.with_suffix(".json")
        write(cls.evidence, {"status": "passed", "command": ["python", "-B", "-m", "unittest", "discover", "-s", "tests", "-v"],
            "returncode": 0, "tests_run": 999, "source_sha256": source_inventory(cls.root),
            "log_path": cls.log.relative_to(cls.root).as_posix(), "log_sha256": sha256(cls.log)})
        cls.output = cls.root / "outputs/frozen"
        with patch.object(ResearchWorld, "__init__", side_effect=AssertionError("physical construction")), \
             patch.object(ResearchWorld, "run", side_effect=AssertionError("physical run")):
            cls.result = build_registry(cls.config, cls.output, protocol_path=cls.protocol,
                                       test_evidence_path=cls.evidence, root=cls.root)

    @contextmanager
    def altered(self, path, value, *, rehash=False):
        original = path.read_bytes()
        inventory_path = self.output / "artifact_hashes.json"
        inventory_bytes = inventory_path.read_bytes()
        try:
            write(path, value)
            if rehash:
                hashes = read(inventory_path)
                hashes[path.relative_to(self.output).as_posix()] = sha256(path)
                write(inventory_path, hashes)
            yield
        finally:
            path.write_bytes(original)
            inventory_path.write_bytes(inventory_bytes)

    def test_freeze_and_read_only_validation_bind_all_concrete_inputs(self):
        before = {p.relative_to(self.output).as_posix(): (sha256(p), p.stat().st_mtime_ns)
                  for p in self.output.rglob("*") if p.is_file()}
        with patch.object(ResearchWorld, "step", side_effect=AssertionError("physical step")):
            checked = validate_registry(self.output, root=self.root)
        self.assertEqual(checked, self.result)
        self.assertTrue(checked["formal_ready"])
        self.assertEqual(checked["jobs_count"], 1184)
        self.assertEqual(checked["manifest"]["expected_world_records"], 21312)
        self.assertEqual(checked["manifest"]["physical_worlds_executed"], 0)
        self.assertEqual(checked["manifest"]["pilot_check"]["variance_unstable_items"], 61)
        self.assertEqual(len(checked["manifest"]["pilot_check"]["budget_limited_items"]), 3)
        self.assertEqual(before, {p.relative_to(self.output).as_posix(): (sha256(p), p.stat().st_mtime_ns)
                                  for p in self.output.rglob("*") if p.is_file()})

    def test_existing_registry_is_never_overwritten(self):
        before = sha256(self.output / "artifact_hashes.json")
        with self.assertRaisesRegex(ValueError, "already exists"):
            build_registry(self.config, self.output, protocol_path=self.protocol,
                           test_evidence_path=self.evidence, root=self.root)
        self.assertEqual(before, sha256(self.output / "artifact_hashes.json"))

    def test_rehashed_config_job_seed_and_gate_corruption_is_rejected(self):
        cases = []
        spec = read(self.output / "configuration.json")
        spec["inference"]["min_joint_valid"] = 2
        cases.append(("configuration.json", spec))
        jobs = read(self.output / "resolved_design.json")
        jobs[0]["seed"] += 1
        cases.append(("resolved_design.json", jobs))
        seeds = read(self.output / "seed_registry.json")
        seeds["replacement_or_additional_sampling"] = True
        cases.append(("seed_registry.json", seeds))
        manifest = read(self.output / "manifest.json")
        manifest["gates"]["final_tests_passed"] = False
        cases.append(("manifest.json", manifest))
        for name, value in cases:
            with self.subTest(name=name), self.altered(self.output / name, value, rehash=True), self.assertRaises(ValueError):
                validate_registry(self.output, root=self.root)

    def test_changed_live_source_and_test_evidence_are_rejected(self):
        path = self.root / "scripts/formal_runtime.py"
        original = path.read_bytes()
        try:
            path.write_bytes(original + b"\n# changed after tests\n")
            with self.assertRaisesRegex(ValueError, "Live source differs"):
                validate_registry(self.output, root=self.root)
            with self.assertRaisesRegex(ValueError, "does not cover current source"):
                build_registry(self.config, self.root / "outputs/stale_tests", protocol_path=self.protocol,
                               test_evidence_path=self.evidence, root=self.root)
            self.assertFalse((self.root / "outputs/stale_tests").exists())
        finally:
            path.write_bytes(original)

    def test_rehashed_test_log_corruption_does_not_activate_readiness(self):
        path = self.output / "evidence/final_tests.json"
        value = read(path)
        value["tests_run"] += 1
        with self.altered(path, value, rehash=True), self.assertRaises(ValueError):
            validate_registry(self.output, root=self.root)

    def test_new_freeze_rejects_historical_seed_collision_before_creating_output(self):
        path = self.root / "outputs/collision/metadata.json"
        write(path, {"seed": self.spec["seeds"][0]})
        try:
            with self.assertRaisesRegex(ValueError, "Formal seed collision"):
                build_registry(self.config, self.root / "outputs/colliding", protocol_path=self.protocol,
                               test_evidence_path=self.evidence, root=self.root)
            self.assertFalse((self.root / "outputs/colliding").exists())
        finally:
            path.unlink()


if __name__ == "__main__":
    unittest.main()

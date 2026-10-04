"""Real tiny formal I/O with fixture-only registry and synchronous worker gates."""
from concurrent.futures import Future
from contextlib import contextmanager, ExitStack
import copy
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from abm_jasss.research_world import ResearchWorld, canonical_hash, jsonable, source_hash
from scripts import run_formal_study as entry
from scripts import formal_runtime as runtime
from scripts.formal_inference import INFERENCE_POLICY
from scripts.run_precision_pilot import PRIMARY, CONTRASTS
from scripts.precision_artifacts import read, write_json, sha256
from test_formal_runtime import tiny_job, fingerprint


class ImmediatePool:
    def __init__(self, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def submit(self, function, *args):
        future = Future()
        try:
            future.set_result(function(*args))
        except Exception as error:
            future.set_exception(error)
        return future


def fixture(path, no_response=False):
    path.mkdir()
    job = tiny_job()
    job["seed"] = 97231
    if no_response:
        job["model"]["response_threshold"] = 1.0
    jobs = []
    for index, alpha in enumerate((.25, .75)):
        value = copy.deepcopy(job)
        value.update(group_id=f"a{index:02d}_seed{job['seed']}", alpha=alpha)
        value["model"]["alpha"] = alpha
        jobs.append(jsonable(value))
    spec = {"test_fixture_only": True, "seeds": [job["seed"]],
            "sample_sizes": {"0.25": 1, "0.75": 1}, "alphas": [.25, .75],
            "metrics": PRIMARY, "contrasts": CONTRASTS, "inference": INFERENCE_POLICY}
    write_json(path / "configuration.json", spec)
    write_json(path / "resolved_design.json", jobs)
    write_json(path / "manifest.json", {"test_fixture_only": True, "source_hash": source_hash()})
    entry._write_inventory(path)
    return jobs, spec


def fixture_guard(path):
    path = Path(path)
    spec = read(path / "configuration.json")
    if spec.get("test_fixture_only") is not True:
        raise ValueError("Not a test fixture")
    return {"status": "passed", "formal_ready": True, "source_hash": source_hash(),
            "specification_hash": canonical_hash(spec), "registry_hash": sha256(path / "manifest.json")}


def fixture_inference_spec(spec):
    return {"alphas": spec["alphas"], "parent_ids_by_alpha": {
                str(alpha): spec["seeds"] for alpha in spec["alphas"]},
            "metrics": spec["metrics"], "contrasts": spec["contrasts"], "inference": spec["inference"]}


@contextmanager
def fixture_gates(jobs):
    with ExitStack() as stack:
        stack.enter_context(patch.object(entry, "validate_registry", side_effect=fixture_guard))
        stack.enter_context(patch.object(runtime, "_validate_registry", side_effect=fixture_guard))
        stack.enter_context(patch.object(entry, "resolve_formal_design", return_value=jobs))
        stack.enter_context(patch.object(entry, "inference_spec", side_effect=fixture_inference_spec))
        stack.enter_context(patch.object(entry, "ProcessPoolExecutor", ImmediatePool))
        yield


class FormalCLITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.registry = cls.root / "registry"
        cls.jobs, cls.spec = fixture(cls.registry)
        cls.batch = cls.root / "batch"
        with fixture_gates(cls.jobs):
            cls.manifest = entry.run_study(cls.registry, cls.batch, workers=1)
            cls.report = entry.validate_batch(cls.batch, workers=1)
        cls.validation = cls.root / "validation.json"
        write_json(cls.validation, cls.report)

    @contextmanager
    def altered(self, relative, value, rehash=True):
        path, inventory = self.batch / relative, self.batch / "artifact_hashes.json"
        original, old_inventory = path.read_bytes(), inventory.read_bytes()
        try:
            path.write_text(json.dumps(value), encoding="utf-8")
            if rehash:
                hashes = read(inventory)
                hashes[relative] = sha256(path)
                inventory.write_text(json.dumps(hashes), encoding="utf-8")
            yield
        finally:
            path.write_bytes(original)
            inventory.write_bytes(old_inventory)

    def test_plan_does_not_construct_world_and_run_counts_are_explicit(self):
        with fixture_gates(self.jobs), patch.object(ResearchWorld, "run", side_effect=AssertionError("model run")):
            value = entry.plan(self.registry)
        self.assertEqual(value["models_executed"], 0)
        self.assertEqual((value["groups"], value["world_records"], value["statistical_arms"]), (2, 36, 38))
        self.assertEqual(value["independent_seeds"], 1)
        self.assertEqual(self.manifest["complete_records"], 36)

    def test_raw_reconstruction_is_read_only_and_cannot_step_world(self):
        before = fingerprint(self.batch)
        with fixture_gates(self.jobs), patch.object(ResearchWorld, "step", side_effect=AssertionError("model step")):
            result = entry.validate_batch(self.batch, workers=1)
        self.assertEqual(result, self.report)
        self.assertEqual(result["world_records"], 36)
        self.assertTrue(result["replay_diagnostics_rebuilt"])
        self.assertEqual(fingerprint(self.batch), before)

    def test_analysis_contains_all_comparisons_and_floor_flag_without_resampling(self):
        output = self.root / "analysis"
        before = fingerprint(self.batch)
        with fixture_gates(self.jobs), patch.object(ResearchWorld, "run", side_effect=AssertionError("model run")):
            manifest = entry.analyze_batch(self.batch, output, self.validation)
        self.assertEqual(manifest["comparison_count"], 102)
        with (output / "primary.csv").open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 102)
        self.assertIn("p_value_numerical_floor", rows[0])
        self.assertTrue(all(row["n_total"] == "1" and row["p_value_two_sided"] == "" for row in rows))
        self.assertEqual(fingerprint(self.batch), before)
        with fixture_gates(self.jobs), self.assertRaisesRegex(ValueError, "already exists"):
            entry.analyze_batch(self.batch, output, self.validation)

    def test_rehashed_changes_reject_stale_validation_and_unhashed_raw_changes(self):
        value = read(self.batch / "statistical_records.json")
        value[0]["metrics"]["perception_error"] = .9876
        output = self.root / "stale_analysis"
        with self.altered("statistical_records.json", value), fixture_gates(self.jobs):
            with self.assertRaisesRegex(ValueError, "Stale or mismatched"):
                entry.analyze_batch(self.batch, output, self.validation)
            with self.assertRaisesRegex(ValueError, "statistical reconstruction"):
                entry.validate_batch(self.batch, workers=1)
        self.assertFalse(output.exists())
        name = "raw/E2_a00_seed97231_I00/metadata.json"
        value = read(self.batch / name)
        value["seed"] = 7
        with self.altered(name, value, False), fixture_gates(self.jobs), self.assertRaisesRegex(ValueError, "hash mismatch"):
            entry.analyze_batch(self.batch, output, self.validation)

    def test_failed_gate_or_existing_output_never_runs_models(self):
        output = self.root / "gate_refused"
        with patch.object(entry, "validate_registry", side_effect=ValueError("registry refused")), \
             patch.object(ResearchWorld, "run", side_effect=AssertionError("model run")), \
             self.assertRaisesRegex(ValueError, "registry refused"):
            entry.run_study(self.registry, output)
        self.assertFalse(output.exists())
        with patch.object(entry, "validate_registry", side_effect=AssertionError("unneeded audit")), \
             self.assertRaisesRegex(ValueError, "already exists"):
            entry.run_study(self.registry, self.batch)

    def test_group_failure_is_preserved_and_blocks_inference(self):
        output = self.root / "failed_batch"
        with fixture_gates(self.jobs), patch.object(runtime, "run_group", side_effect=RuntimeError("fixture failure")), \
             self.assertRaisesRegex(ValueError, "Formal batch failed"):
            entry.run_study(self.registry, output, workers=1)
        self.assertEqual(read(output / "manifest.json")["status"], "failed")
        self.assertEqual(len(read(output / "failures.json")), 2)
        self.assertFalse((output / "statistical_records.json").exists())
        with fixture_gates(self.jobs), self.assertRaisesRegex(ValueError, "complete formal batches"):
            entry.validate_batch(output, workers=1)

    def test_no_response_keeps_undefined_targeting_and_auxiliary_incidence(self):
        registry, batch = self.root / "no_response_registry", self.root / "no_response_batch"
        jobs, _ = fixture(registry, no_response=True)
        validation = self.root / "no_response_validation.json"
        output = self.root / "no_response_analysis"
        with fixture_gates(jobs):
            entry.run_study(registry, batch, workers=1)
            write_json(validation, entry.validate_batch(batch, workers=1))
            entry.analyze_batch(batch, output, validation)
        with (output / "primary.csv").open(encoding="utf-8", newline="") as stream:
            primary = list(csv.DictReader(stream))
        target = [row for row in primary if row["metric"] == "targeting_error_trigger"]
        self.assertEqual(len(target), 34)
        self.assertTrue(all(row["n_total"] == "1" and row["n_joint_valid"] == "0"
                            and row["mean"] == "" for row in target))
        with (output / "auxiliary.csv").open(encoding="utf-8", newline="") as stream:
            auxiliary = list(csv.DictReader(stream))
        incidence = [row for row in auxiliary if row["metric"] == "has_response"]
        waiting = [row for row in auxiliary if row["metric"] == "waiting_time"]
        self.assertTrue(incidence and all(row["mean"] == "0.0" and row["n_valid"] == "1" for row in incidence))
        self.assertTrue(waiting and all(row["mean"] == "" and row["n_valid"] == "0" for row in waiting))


if __name__ == "__main__":
    unittest.main()

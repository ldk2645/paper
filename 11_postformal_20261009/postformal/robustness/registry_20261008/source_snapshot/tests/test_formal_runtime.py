"""Tiny formal-adapter fixtures; no registered formal seed is simulated.

The registry auditor has its own tests. Here its report is mocked for an
explicit six-agent fixture, while runtime binding and raw reconstruction are
real. No production registry or formal run directory is created.
"""
from contextlib import contextmanager
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from abm_jasss.research_config import ResearchConfig, RESEARCH_VERSION
from abm_jasss.research_world import ResearchWorld, canonical_hash, source_hash
from scripts import formal_runtime as runtime
from scripts.formal_artifacts import LOG_FILES, SNAPSHOT_FILE, read, sha256, write_json
from scripts.run_precision_pilot import run_group as run_pilot_group


def tiny_job():
    config = ResearchConfig(n_agents=6, n_topics=2, steps=12, final_window=4,
        population_weights=(1., 1.), agenda_topics=(0,), advantaged_topic=1,
        initial_items=4, arrivals_per_step=1, attention_budget=2,
        survey_size=3, survey_interval=2, observation_window=1,
        update_frequency=1, inference_grid=2, reference_agents=1,
        emotion_mean=.8, emotion_advantage=0., official_emotion_mean=.8,
        interaction_mean=1., interaction_sd=0., response_threshold=0.,
        completion_start=6, completion_end=9, completion_followup=2,
        government_delay=3, response_capacity=1, observation_delay=0)
    return {"group_id": "a00_seed97221", "seed": 97221, "alpha": .25,
            "model": {**config.to_dict(), "alpha": .25}, "fork_tick": 6,
            "branches": {"B0": {}, "B1": {"pref_info": True},
                         "B2": {"government_delay": 1}, "B3": {"response_capacity": 2},
                         "B4": {"alpha": 0.}}}


def mock_registry(path, job):
    """Only supplies fixture bytes; it is not a valid production registry."""
    config = {"test_fixture_only": True}
    write_json(path / "configuration.json", config)
    write_json(path / "resolved_design.json", [job])
    write_json(path / "manifest.json", {"test_fixture_only": True})
    write_json(path / "artifact_hashes.json", {name: sha256(path / name)
               for name in ("configuration.json", "resolved_design.json", "manifest.json")})
    return {"status": "passed", "formal_ready": True,
            "registry_hash": sha256(path / "manifest.json"),
            "specification_hash": canonical_hash(config), "source_hash": source_hash()}


def fingerprint(path):
    return {p.relative_to(path).as_posix(): (sha256(p), p.stat().st_mtime_ns)
            for p in path.rglob("*") if p.is_file()}


class FormalRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        cls.job = tiny_job()
        cls.registry = cls.root / "fixture_registry"
        cls.report = mock_registry(cls.registry, cls.job)
        cls.output = cls.root / "formal_fixture"
        cls.expected_hash = source_hash()
        cls.manifest = {**cls.report, "stage": "formal", "code_version": RESEARCH_VERSION,
                        "batch_id": "formal-test-fixture"}
        with patch.object(runtime, "_validate_registry", return_value=cls.report) as audit:
            cls.result = runtime.run_group(cls.job, cls.output, cls.manifest["batch_id"],
                                           cls.expected_hash, cls.registry)
            if audit.call_count != 1:
                raise AssertionError("Expected one full registry audit")

    def validate(self, manifest=None):
        return runtime.validate_group((self.output, self.job, manifest or self.manifest, self.registry))

    @contextmanager
    def altered(self, relative, value):
        path = self.output / relative
        previous = path.read_bytes()
        try:
            path.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")
            yield
        finally:
            path.write_bytes(previous)

    def test_formal_metadata_and_read_only_nineteen_arm_reconstruction(self):
        self.assertEqual(len(self.result["run_ids"]), 18)
        before = fingerprint(self.output)
        with patch.object(ResearchWorld, "run", side_effect=AssertionError("physical run")), \
             patch.object(ResearchWorld, "step", side_effect=AssertionError("physical step")), \
             patch("scripts.formal_artifacts.write_json", side_effect=AssertionError("write")), \
             patch("scripts.formal_artifacts.write_gzip_json", side_effect=AssertionError("write")), \
             patch.object(runtime, "_validate_registry", side_effect=AssertionError("uncached audit")):
            result = self.validate()
        self.assertEqual(len(result["records"]), 19)
        self.assertEqual(result["trajectory_records"], 18 * self.job["model"]["steps"])
        self.assertEqual(fingerprint(self.output), before)
        self.assertEqual(result["records"], runtime.statistical_records(self.output, [self.job]))
        for name in self.result["run_ids"]:
            metadata = read(self.output / "raw" / name / "metadata.json")
            self.assertEqual(metadata["stage"], "formal")
            self.assertTrue(metadata["formal_ready"])
            self.assertEqual(metadata["schema_version"], "formal-artifacts-1")
            self.assertEqual(metadata["formal_registry_hash"], self.report["registry_hash"])
            self.assertEqual(metadata["formal_specification_hash"], self.report["specification_hash"])
            self.assertEqual(metadata["formal_job_hash"], canonical_hash(self.job))

    def test_identical_physics_to_pilot_group_and_no_pilot_global_mutation(self):
        import scripts.precision_artifacts as pilot_artifacts
        reference = self.root / "pilot_reference"
        result = run_pilot_group(self.job, reference, "pilot-test-fixture", self.expected_hash)
        self.assertEqual(result, self.result)
        self.assertEqual(pilot_artifacts.STAGE, "precision_pilot")
        self.assertEqual(pilot_artifacts.ARTIFACT_SCHEMA, "precision-artifacts-1")
        for name in result["run_ids"]:
            formal = self.output / "raw" / name
            pilot = reference / "raw" / name
            for relative in (SNAPSHOT_FILE, *LOG_FILES.values()):
                self.assertEqual((formal / relative).read_bytes(), (pilot / relative).read_bytes())
            self.assertFalse(read(pilot / "metadata.json")["formal_ready"])

    def test_unregistered_job_or_source_is_rejected_before_running(self):
        output = self.root / "must_not_exist"
        wrong = copy.deepcopy(self.job)
        wrong["model"]["n_agents"] += 1
        with patch.object(ResearchWorld, "run", side_effect=AssertionError("physical run")):
            with self.assertRaisesRegex(ValueError, "not in the validated"):
                runtime.run_group(wrong, output, "bad", self.expected_hash, self.registry)
            with self.assertRaisesRegex(ValueError, "source mismatch"):
                runtime.run_group(self.job, output, "bad", "wrong", self.registry)
            with self.assertRaisesRegex(ValueError, "registry path"):
                runtime.run_group(self.job, output, "bad", self.expected_hash, self.report)
        self.assertFalse(output.exists())

    def test_failed_or_forged_registry_report_cannot_authorize(self):
        for label, changes in (("failed", {"formal_ready": False}),
                               ("forged", {"registry_hash": "wrong"})):
            with self.subTest(label=label):
                registry = self.root / label
                report = mock_registry(registry, self.job)
                report.update(changes)
                output = self.root / (label + "_output")
                with patch.object(runtime, "_validate_registry", return_value=report), \
                     patch.object(ResearchWorld, "run", side_effect=AssertionError("physical run")), \
                     self.assertRaises(ValueError):
                    runtime.run_group(self.job, output, "bad", self.expected_hash, registry)
                self.assertFalse(output.exists())

    def test_cached_registry_key_files_remain_bound(self):
        registry = self.root / "cache_change"
        report = mock_registry(registry, self.job)
        with patch.object(runtime, "_validate_registry", return_value=report) as audit:
            runtime._authorize(registry, self.job, self.expected_hash)
            runtime._authorize(registry, self.job, self.expected_hash)
            self.assertEqual(audit.call_count, 1)
            path = registry / "configuration.json"
            path.write_text('{"test_fixture_only":false}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "changed after validation"):
                runtime._authorize(registry, self.job, self.expected_hash)

    def test_manifest_and_raw_formal_binding_tampering_are_rejected(self):
        for field, value in (("stage", "precision_pilot"), ("formal_ready", False),
                             ("registry_hash", "wrong"), ("specification_hash", "wrong")):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "manifest/registry"):
                self.validate({**self.manifest, field: value})
        name = self.result["run_ids"][0]
        relative = f"raw/{name}/metadata.json"
        metadata = read(self.output / relative)
        for field, value in (("stage", "precision_pilot"), ("formal_ready", False),
                             ("formal_registry_hash", "wrong"), ("formal_job_hash", "wrong")):
            with self.subTest(field=field), self.altered(relative, {**metadata, field: value}), \
                 self.assertRaisesRegex(ValueError, "metadata reconstruction"):
                self.validate()

    def test_group_replay_and_derived_corruption_reconstruct(self):
        group = f"groups/{self.job['group_id']}.json"
        value = read(self.output / group)
        value["run_ids"].pop()
        with self.altered(group, value), self.assertRaisesRegex(ValueError, "Group run inventory"):
            self.validate()
        replay = f"raw/E3_replay_{self.job['group_id']}_delay0/metadata.json"
        value = read(self.output / replay)
        value["provenance"]["donor_run_id"] = "wrong"
        with self.altered(replay, value), self.assertRaisesRegex(ValueError, "Replay provenance"):
            self.validate()
        derived = f"derived/{self.result['run_ids'][0]}.json"
        value = read(self.output / derived)
        value["summary"]["execution_count"] += 1
        with self.altered(derived, value), self.assertRaisesRegex(ValueError, "Derived reconstruction"):
            self.validate()

    def test_completed_group_is_not_overwritten(self):
        before = fingerprint(self.output)
        with self.assertRaises((FileExistsError, ValueError)):
            runtime.run_group(self.job, self.output, self.manifest["batch_id"],
                              self.expected_hash, self.registry)
        self.assertEqual(before, fingerprint(self.output))


if __name__ == "__main__":
    unittest.main()

"""Reconstruct a complete tiny pilot and reject rehashed semantic corruption."""
from contextlib import contextmanager
import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from abm_jasss.research_world import source_hash
from scripts.precision_artifacts import read, sha256
from scripts.run_precision_pilot import run_study
from scripts.validate_precision_pilot import validate


def tiny_spec():
    return {"stage": "precision_pilot", "formal_ready": False,
            "model": {"n_agents": 6, "n_topics": 2, "steps": 12, "final_window": 4,
                      "population_weights": [1., 1.], "agenda_topics": [0], "advantaged_topic": 1,
                      "initial_items": 4, "arrivals_per_step": 1, "attention_budget": 2,
                      "survey_size": 3, "survey_interval": 2, "observation_window": 1,
                      "update_frequency": 1, "inference_grid": 2, "reference_agents": 1,
                      "emotion_mean": .8, "emotion_advantage": 0., "official_emotion_mean": .8,
                      "interaction_mean": 1., "interaction_sd": 0., "response_threshold": 0.,
                      "completion_start": 6, "completion_end": 9, "completion_followup": 2,
                      "government_delay": 3, "response_capacity": 1, "observation_delay": 0},
            "alphas": [.25, .75], "initial_seeds": [98111], "expansion_seeds": [98112],
            "fork_tick": 6,
            "branches": {"B0": {}, "B1": {"pref_info": True}, "B2": {"government_delay": 1},
                         "B3": {"response_capacity": 2}, "B4": {"alpha": 0.}},
            "precision": {"target_half_width": .02, "min_valid": 30, "max_total": 1000},
            "stability": {"variance_relative_tolerance": .25, "support_absolute_tolerance": .10},
            "expected_source_hash": source_hash()}


class PrecisionPilotValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.output = Path(cls.temporary.name) / "pilot"
        manifest = run_study(tiny_spec(), cls.output, workers=1)
        if manifest["status"] != "complete":
            raise AssertionError(read(cls.output / "failures.json"))

    @contextmanager
    def altered(self, replacements, refresh_hashes=True):
        hash_path = self.output / "artifact_hashes.json"
        originals = {self.output / name: (self.output / name).read_bytes() for name in replacements}
        originals[hash_path] = hash_path.read_bytes()
        try:
            for name, value in replacements.items():
                payload = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
                (self.output / name).write_bytes(gzip.compress(payload, mtime=0) if name.endswith(".gz") else payload)
            if refresh_hashes:
                hashes = read(hash_path)
                for name in replacements:
                    hashes[name] = sha256(self.output / name)
                hash_path.write_text(json.dumps(hashes), encoding="utf-8")
            yield
        finally:
            for path, content in originals.items():
                path.write_bytes(content)

    def test_complete_bundle_rebuilds_read_only_without_running_physical_world(self):
        before = {p.relative_to(self.output).as_posix(): sha256(p) for p in self.output.rglob("*") if p.is_file()}
        with patch("abm_jasss.research_world.ResearchWorld.step", side_effect=AssertionError("physical simulation")):
            result = validate(self.output, workers=1)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["world_records"], 36)
        self.assertEqual(result["groups"], 2)
        self.assertEqual(result["independent_seeds"], 1)
        self.assertTrue(result["read_only"])
        self.assertFalse(result["formal_ready"])
        self.assertEqual(result["manifest_hash"], sha256(self.output / "manifest.json"))
        self.assertEqual(result["artifact_inventory_hash"], sha256(self.output / "artifact_hashes.json"))
        after = {p.relative_to(self.output).as_posix(): sha256(p) for p in self.output.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_parallel_reconstruction_agrees(self):
        serial = validate(self.output, workers=1)
        parallel = validate(self.output, workers=2)
        self.assertEqual(serial, parallel)

    def test_unhashed_and_rehashed_statistics_corruption_rejected(self):
        value = read(self.output / "statistical_records.json")
        value[0]["metrics"]["perception_error"] = .98765
        with self.altered({"statistical_records.json": value}, False), self.assertRaisesRegex(ValueError, "Artifact hash mismatch"):
            validate(self.output, workers=1)
        with self.altered({"statistical_records.json": value}), self.assertRaisesRegex(ValueError, "Statistical record reconstruction"):
            validate(self.output, workers=1)
        value = read(self.output / "precision_analysis.json")
        value["formal_ready"] = True
        with self.altered({"precision_analysis.json": value}), self.assertRaisesRegex(ValueError, "Precision analysis reconstruction"):
            validate(self.output, workers=1)

    def test_rehashed_group_and_diagnostic_corruption_rejected(self):
        name = "groups/a00_seed98111.json"
        value = read(self.output / name)
        value["run_ids"].pop()
        with self.altered({name: value}), self.assertRaisesRegex(ValueError, "Group run inventory"):
            validate(self.output, workers=1)
        name = "diagnostics/a00_seed98111.json"
        value = read(self.output / name)
        value["0"]["forged"] = True
        with self.altered({name: value}), self.assertRaisesRegex(ValueError, "Replay diagnostic reconstruction"):
            validate(self.output, workers=1)

    def test_rehashed_world_provenance_and_analysis_override_rejected(self):
        name = "raw/E3_replay_a00_seed98111_delay0/metadata.json"
        value = read(self.output / name)
        value["provenance"]["donor_run_id"] = "wrong_donor"
        with self.altered({name: value}), self.assertRaisesRegex(ValueError, "Replay provenance mismatch"):
            validate(self.output, workers=1)
        name = "raw/E4_a00_seed98111_B1/metadata.json"
        value = read(self.output / name)
        value["provenance"]["fork_tick"] += 1
        with self.altered({name: value}), self.assertRaisesRegex(ValueError, "E4 provenance mismatch"):
            validate(self.output, workers=1)

    def test_rehashed_resolved_design_or_archive_cannot_bypass_contract(self):
        value = read(self.output / "resolved_design.json")
        value[0]["fork_tick"] += 1
        with self.altered({"resolved_design.json": value}), self.assertRaisesRegex(ValueError, "Resolved pilot design mismatch"):
            validate(self.output, workers=1)
        manifest = read(self.output / "manifest.json")
        manifest["complete_records"] -= 1
        with self.altered({"manifest.json": manifest}), self.assertRaisesRegex(ValueError, "Batch completion accounting"):
            validate(self.output, workers=1)


if __name__ == "__main__":
    unittest.main()

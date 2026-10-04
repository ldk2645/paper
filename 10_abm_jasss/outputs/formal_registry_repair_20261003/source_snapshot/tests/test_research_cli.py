"""Integration checks for S0 artifacts, failure accounting and reproducibility."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from abm_jasss.research_cli import resolve_design, run_study
from abm_jasss.research_outcomes import summarize_world
from abm_jasss.research_world import ResearchWorld, canonical_hash


def small_spec():
    return {"stage": "S0", "formal_ready": False,
            "model": {"n_agents": 12, "survey_size": 4, "steps": 12,
                      "final_window": 4, "inference_grid": 2, "reference_agents": 2,
                      "completion_start": 2, "completion_end": 8, "completion_followup": 3},
            "alphas": [.25], "seeds": [701, 702], "fork_tick": 6,
            "branches": {"B0": {}, "B1": {"pref_info": True},
                         "B2": {"government_delay": 1}, "B3": {"response_capacity": 2},
                         "B4": {"alpha": 0.0}}}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


class ResearchCLITests(unittest.TestCase):
    def test_formal_unknown_duplicate_and_noninterventions_rejected_before_writing(self):
        invalid = []
        for key, value in (("stage", "formal"), ("formal_ready", True),
                           ("seeds", [1, 1]), ("alphas", [.2, .2]), ("fork_tick", 0)):
            spec = small_spec()
            spec[key] = value
            invalid.append(spec)
        spec = small_spec()
        spec["branches"]["B4"] = {"alpha": .25}
        invalid.append(spec)
        spec = small_spec()
        spec["branches"]["B2"]["response_capacity"] = 3
        invalid.append(spec)
        spec = small_spec()
        spec["model"]["final_window"] = 8
        invalid.append(spec)
        spec = small_spec()
        spec["model"]["completion_end"] = 3
        invalid.append(spec)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            for spec in invalid:
                with self.subTest(spec=spec), self.assertRaises((ValueError, TypeError)):
                    run_study(spec, output)
                self.assertFalse(output.exists())

    def test_failed_group_preserves_failure_and_blocks_aggregate(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            with patch("abm_jasss.research_cli.run_group", side_effect=RuntimeError("test failure")):
                result = run_study(small_spec(), output)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["failed_groups"], 2)
            self.assertEqual(len(read(output / "failures.json")), 2)
            self.assertFalse((output / "paired_diagnostics.json").exists())
            self.assertFalse((output / "validation.json").exists())
            self.assertFalse((output / "report.md").exists())
            self.assertTrue((output / "artifact_hashes.json").exists())

    def test_default_completion_window_uses_branch_enrollment_and_retains_censoring(self):
        spec = small_spec()
        spec["seeds"] = [701]
        del spec["model"]["completion_end"]
        spec["model"]["completion_followup"] = 20
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            self.assertEqual(run_study(spec, output)["status"], "complete")
            for folder in (output / "raw").glob("E4_*"):
                config = read(folder / "metadata.json")["analysis_config"]
                self.assertEqual(config["completion_start"], 6)
                self.assertEqual(config["completion_end"], 6)
                self.assertEqual(config["completion_followup"], 20)

    def test_serial_parallel_artifacts_rebuild_and_output_preservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "config.json"
            config.write_text(json.dumps(small_spec()), encoding="utf-8")
            outputs = [root / "serial", root / "parallel"]
            for workers, output in zip((1, 2), outputs):
                command = [sys.executable, "-B", "-m", "abm_jasss.research_cli",
                           "--config", str(config), "--output", str(output), "--workers", str(workers)]
                run = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stderr)
                manifest = read(output / "manifest.json")
                self.assertEqual(manifest["status"], "complete")
                self.assertFalse(manifest["formal_ready"])
                self.assertEqual(manifest["world_records"], 18)
                self.assertEqual(read(output / "validation.json")["e4_suffixes"], 10)
                paired = read(output / "paired_diagnostics.json")["0.25"]
                for scenario in ("E2", "E4"):
                    for metric in ("platform_representation_gap", "perception_error", "targeting_error_trigger"):
                        self.assertIn(metric, paired[scenario])
                for relative, digest in read(output / "artifact_hashes.json").items():
                    self.assertEqual(hashlib.sha256((output / relative).read_bytes()).hexdigest(), digest)
                for name, digest in manifest["source_sha256"].items():
                    self.assertEqual(hashlib.sha256((output / "source_snapshot" / "abm_jasss" / name).read_bytes()).hexdigest(), digest)
                initial = read(output / "snapshots" / "a00_seed701.json")
                self.assertEqual(initial["state_hash"], canonical_hash(initial["state"]))
                restored = ResearchWorld.from_snapshot(initial).run()
                mother = output / "raw" / "E2_a00_seed701_I00"
                self.assertEqual(restored.trajectory, read(mother / "evaluator" / "trajectory.json"))
                for folder in (output / "raw").iterdir():
                    metadata = read(folder / "metadata.json")
                    events = read(folder / "evaluator" / "response_events.json")
                    trajectory = read(folder / "evaluator" / "trajectory.json")
                    rebuilt = summarize_world(trajectory, events, metadata["analysis_config"])
                    self.assertEqual(rebuilt, read(output / "derived" / f"{folder.name}.json")["summary"])
                    self.assertNotIn('"P_trigger"', (folder / "government" / "actions.json").read_text())
                    self.assertNotIn('"P_execution"', (folder / "government" / "actions.json").read_text())
                    self.assertNotIn('"P_true"', (folder / "government" / "information.json").read_text())
                    if metadata["scenario"] == "E4":
                        self.assertEqual(metadata["analysis_config"]["completion_start"], 6)
                        self.assertEqual(metadata["config"]["completion_start"], 2)
                before = (output / "artifact_hashes.json").read_bytes()
                refused = subprocess.run(command, capture_output=True, text=True)
                self.assertNotEqual(refused.returncode, 0)
                self.assertEqual(before, (output / "artifact_hashes.json").read_bytes())
            for folder in (outputs[0] / "raw").iterdir():
                for relative in ("evaluator/trajectory.json", "evaluator/response_events.json",
                                 "government/information.json", "supply.json", "snapshot_final.json"):
                    self.assertEqual((folder / relative).read_bytes(),
                                     (outputs[1] / "raw" / folder.name / relative).read_bytes())
            for path in (outputs[0] / "derived").glob("*.json"):
                self.assertEqual(path.read_bytes(), (outputs[1] / "derived" / path.name).read_bytes())
            self.assertEqual((outputs[0] / "paired_diagnostics.json").read_bytes(),
                             (outputs[1] / "paired_diagnostics.json").read_bytes())


if __name__ == "__main__":
    unittest.main()

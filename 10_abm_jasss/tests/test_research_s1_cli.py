"""S1 bundle checks: deterministic workers, failure accounting and provenance."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from abm_jasss.research_replay import ControlledReplayWorld, replay_diagnostics
from abm_jasss.research_s1_cli import run_group, run_study
from abm_jasss.research_world import ResearchWorld, canonical_hash


def small_spec():
    return {"stage": "S1", "formal_ready": False,
        "model": {"n_agents": 8, "n_topics": 2, "steps": 8, "final_window": 2,
            "population_weights": [1., 1.], "agenda_topics": [0], "advantaged_topic": 1,
            "initial_items": 4, "arrivals_per_step": 2, "attention_budget": 2,
            "survey_size": 4, "survey_interval": 1, "pref_info": True,
            "inference_grid": 2, "reference_agents": 2, "update_frequency": 1,
            "response_threshold": 0., "government_delay": 1, "completion_followup": 2},
        "alphas": [.25], "seeds": [901], "administrative_delays": [0, 2],
        "observation_delays": [0], "scheduling_capacities": [1],
        "dynamics": {"alphas": [.2, .8], "stage_ticks": 2,
            "recovery_fork": 3, "recovery_end": 6, "reference_start": 0, "reference_end": 2,
            "reference_alpha": 0., "reference_seed": 1901,
            "recovery_window": 1, "recovery_consecutive": 2, "recovery_tolerance": .05,
            "sizes": [8], "durations": [8], "initial_conditions": {"balanced": [1., 1.]},
            "supply_scaling": "proportional", "capacity_scaling": "fixed",
            "interventions": {"recovery_control": {}}}}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_batch(value, batch_id):
    if isinstance(value, dict):
        return {key: normalize_batch(item, batch_id) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_batch(item, batch_id) for item in value]
    return value.replace(batch_id, "BATCH") if isinstance(value, str) else value


class ResearchS1CLITests(unittest.TestCase):
    def test_invalid_registration_is_rejected_before_any_output_is_written(self):
        invalid = []
        for key, value in (("stage", "formal"), ("formal_ready", True),
                ("seeds", [901, 901]), ("alphas", [.2, .2]), ("administrative_delays", [1]),
                ("administrative_delays", [0]), ("observation_delays", [True]),
                ("scheduling_capacities", [0]), ("extra_setting", 1)):
            spec = small_spec()
            spec[key] = value
            invalid.append(spec)
        for key, value in (("response_enabled", False), ("full_heat_off", True),
                           ("trust_update_rate", 0.), ("trust_feedback_strength", 0.)):
            spec = small_spec()
            spec["model"][key] = value
            invalid.append(spec)
        for key, value in (("stage_ticks", 0), ("alphas", [.8, .2]),
                           ("reference_seed", 901), ("recovery_end", 2)):
            spec = small_spec()
            spec["dynamics"][key] = value
            invalid.append(spec)
        spec = small_spec()
        spec["seeds"] = [901, 1901]
        invalid.append(spec)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            for spec in invalid:
                with self.subTest(spec=spec), self.assertRaises((ValueError, TypeError)):
                    run_study(spec, output)
                self.assertFalse(output.exists())

    def test_partial_failure_is_preserved_and_blocks_batch_aggregation(self):
        def fail_dynamic(job, *args):
            if job["kind"] == "dynamics":
                raise RuntimeError("injected S1 dynamics failure")
            return run_group(job, *args)

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            with patch("abm_jasss.research_s1_cli.run_group", side_effect=fail_dynamic):
                result = run_study(small_spec(), output)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["completed_groups"], 1)
            self.assertEqual(result["failed_groups"], 1)
            failures = read(output / "failures.json")
            self.assertEqual(failures[0]["group_id"], "dynamics_seed901")
            self.assertIn("injected S1 dynamics failure", failures[0]["traceback"])
            self.assertTrue((output / "raw" / "closed_a00_seed901_baseline").exists())
            self.assertTrue((output / "launch_manifest.json").exists())
            self.assertTrue((output / "artifact_hashes.json").exists())
            self.assertFalse((output / "paired_diagnostics.json").exists())
            self.assertFalse((output / "validation.json").exists())

    def test_existing_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "existing"
            output.mkdir()
            sentinel = output / "keep.txt"
            sentinel.write_bytes(b"historical result\r\n")
            with self.assertRaisesRegex(ValueError, "must not exist"):
                run_study(small_spec(), output)
            self.assertEqual(sentinel.read_bytes(), b"historical result\r\n")
            self.assertEqual(list(output.iterdir()), [sentinel])

    def test_serial_parallel_bundles_match_and_preserve_replay_and_checkpoint_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            specification = root / "config.json"
            specification.write_text(json.dumps(small_spec()), encoding="utf-8")
            outputs = [root / "serial", root / "parallel"]
            manifests = []
            for workers, output in zip((1, 2), outputs):
                result = subprocess.run([sys.executable, "-B", "-m", "abm_jasss.research_s1_cli",
                    "--config", str(specification), "--output", str(output), "--workers", str(workers)],
                    capture_output=True, text=True)
                failures = read(output / "failures.json") if (output / "failures.json").exists() else []
                self.assertEqual(result.returncode, 0, f"{result.stderr}\n{failures}")
                manifest = read(output / "manifest.json")
                manifests.append(manifest)
                self.assertEqual(manifest["status"], "complete")
                self.assertFalse(manifest["formal_ready"])
                self.assertEqual(manifest["completed_groups"], 2)
                self.assertEqual(manifest["failed_groups"], 0)
                self.assertEqual(manifest["world_records"], 23)
                self.assertEqual(len(read(output / "validation.json")["groups"]), 2)
                for relative, digest in read(output / "artifact_hashes.json").items():
                    self.assertEqual(hashlib.sha256((output / relative).read_bytes()).hexdigest(), digest)
                for name, digest in manifest["source_sha256"].items():
                    self.assertEqual(hashlib.sha256((output / "source_snapshot" / "abm_jasss" / name).read_bytes()).hexdigest(), digest)
                checkpoints = []
                for folder in (output / "raw").iterdir():
                    metadata = read(folder / "metadata.json")
                    snapshot = read(folder / "evaluator" / "snapshot.json")
                    events = read(folder / "evaluator" / "response_events.json")
                    derived = read(output / "derived" / f"{folder.name}.json")
                    self.assertEqual(snapshot["state_hash"], canonical_hash(snapshot["state"]))
                    self.assertEqual(metadata["shock_tape_id"],
                        f"{metadata['randomness']['schema']}/seed{metadata['seed']}")
                    self.assertNotIn('"P_true"', (folder / "government" / "information.json").read_text())
                    self.assertNotIn('"P_trigger"', (folder / "government" / "actions.json").read_text())
                    if metadata["scenario"] == "replay":
                        self.assertTrue(events)
                        self.assertTrue(all(event["information_ref"]["kind"] == "controlled_fixed_plan" for event in events))
                        self.assertTrue(all("estimate_record" in event["donor_information_ref"] for event in events))
                        self.assertTrue(all(event["plan_mode"] == "controlled_replay" for event in derived["event_diagnostics"]))
                        restored = ControlledReplayWorld.from_snapshot(snapshot)
                        archived = read(output / "diagnostics" / f"{metadata['group_id']}.json")
                        self.assertEqual(replay_diagnostics(restored), archived[str(metadata["config"]["government_delay"])])
                    else:
                        self.assertTrue(all("estimate_record" in event["information_ref"] for event in events))
                        self.assertTrue(all(event["plan_mode"] == "adaptive" for event in derived["event_diagnostics"]))
                    if metadata["status"] == "checkpoint":
                        checkpoints.append(folder.name)
                        self.assertEqual(metadata["scenario"], "dynamic")
                        self.assertLess(snapshot["state"]["tick"], snapshot["state"]["config"]["steps"])
                        self.assertEqual(ResearchWorld.from_snapshot(snapshot).snapshot(), snapshot)
                self.assertTrue(checkpoints)
                stored_snapshots = list((output / "dynamic_snapshots" / "dynamics_seed901").glob("*.json"))
                self.assertTrue(stored_snapshots)
                for path in stored_snapshots:
                    snapshot = read(path)
                    self.assertEqual(snapshot["state_hash"], canonical_hash(snapshot["state"]))
                for scenario in ("closed", "replay"):
                    paired = read(output / "paired_diagnostics.json")["0.25"][scenario]
                    self.assertIn("targeting_error_trigger", paired)
                    for metric in paired.values():
                        for contrast in metric.values():
                            self.assertNotIn("normal95_interval", contrast)
                            self.assertIn("not a precision pilot", contrast["scope"])
            relatives = lambda output: sorted(path.relative_to(output).as_posix()
                for directory in ("raw", "derived", "diagnostics", "dynamic_snapshots", "checks")
                for path in (output / directory).rglob("*.json"))
            self.assertEqual(relatives(outputs[0]), relatives(outputs[1]))
            for relative in relatives(outputs[0]) + ["paired_diagnostics.json", "validation.json"]:
                self.assertEqual(normalize_batch(read(outputs[0] / relative), manifests[0]["batch_id"]),
                                 normalize_batch(read(outputs[1] / relative), manifests[1]["batch_id"]), relative)


if __name__ == "__main__":
    unittest.main()

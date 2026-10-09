"""Small real S0 bundles exercise the read-only comparison boundary."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import compare_research_outputs as comparison


ROOT = Path(__file__).resolve().parents[1]


def inventory(output):
    return {path.relative_to(output).as_posix():
            (comparison.validator.sha256(path), path.stat().st_mtime_ns)
            for path in output.rglob("*") if path.is_file()}


def rehash(output):
    hashes = {name: value[0] for name, value in inventory(output).items()
              if name != "artifact_hashes.json"}
    (output / "artifact_hashes.json").write_text(json.dumps(hashes), encoding="utf-8")


class ResearchComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        spec = {"stage": "S0", "formal_ready": False,
                "model": {"n_agents": 12, "survey_size": 4, "steps": 12,
                          "final_window": 4, "inference_grid": 2, "reference_agents": 2,
                          "completion_start": 2, "completion_end": 8, "completion_followup": 3},
                "alphas": [.25], "seeds": [701, 702], "fork_tick": 6,
                "branches": {"B0": {}, "B1": {"pref_info": True},
                             "B2": {"government_delay": 1}, "B3": {"response_capacity": 2},
                             "B4": {"alpha": 0.0}}}
        config = cls.root / "config.json"
        config.write_text(json.dumps(spec), encoding="utf-8")
        cls.left, cls.right = cls.root / "serial", cls.root / "parallel"
        for workers, output in zip((1, 2), (cls.left, cls.right)):
            result = subprocess.run(
                [sys.executable, "-B", "-m", "abm_jasss.research_cli", "--config", str(config),
                 "--output", str(output), "--workers", str(workers)],
                cwd=ROOT, capture_output=True, text=True)
            if result.returncode:
                raise AssertionError(result.stdout + result.stderr)

    def copy_right(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        output = Path(temporary.name) / "changed"
        shutil.copytree(self.right, output)
        return output

    def test_cli_compares_real_serial_parallel_bundles_without_writes(self):
        before = [inventory(path) for path in (self.left, self.right)]
        result = subprocess.run(
            [sys.executable, "-B", str(ROOT / "scripts" / "compare_research_outputs.py"),
             str(self.left), str(self.right)], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "passed")
        self.assertNotEqual(*report["batch_ids"])
        self.assertEqual(report["normalized_metadata_files"], 18)
        self.assertEqual(report["compared_files"], report["byte_compared_files"] + 18 + 2)
        self.assertEqual(report["raw_files"], sum(name.startswith("raw/") for name in before[0]))
        self.assertEqual([item["status"] for item in report["validations"]], ["passed", "passed"])
        self.assertEqual(before, [inventory(path) for path in (self.left, self.right)])

    def test_valid_json_formatting_difference_still_fails_raw_byte_comparison(self):
        output = self.copy_right()
        relative = "raw/E2_a00_seed701_I00/evaluator/trajectory.json"
        with (output / relative).open("ab") as stream:
            stream.write(b"\n")
        rehash(output)
        with self.assertRaisesRegex(ValueError, "Byte comparison mismatch: " + relative):
            comparison.compare(self.left, output)

    def test_metadata_normalization_does_not_hide_other_or_nested_fields(self):
        output = self.copy_right()
        path = output / "raw" / "E2_a00_seed701_I00" / "metadata.json"
        metadata = comparison.validator.read(path)
        metadata["audit"] = {"batch_id": "nested identity must not be ignored"}
        path.write_text(json.dumps(metadata), encoding="utf-8")
        rehash(output)
        with self.assertRaisesRegex(ValueError, "Metadata comparison mismatch"):
            comparison.compare(self.left, output)

    def test_extra_raw_file_is_not_silently_skipped(self):
        output = self.copy_right()
        (output / "raw" / "E2_a00_seed701_I00" / "extra.json").write_text("{}", encoding="utf-8")
        rehash(output)
        with self.assertRaisesRegex(ValueError, "Comparison file set mismatch"):
            comparison.compare(self.left, output)

    def test_both_bundles_are_validated_before_source_hash_comparison(self):
        output = self.copy_right()
        path = output / "manifest.json"
        manifest = comparison.validator.read(path)
        manifest["source_hash"] = "different source"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with patch.object(comparison.validator, "validate", return_value={"status": "passed"}) as validate:
            with self.assertRaisesRegex(ValueError, "Source hash mismatch"):
                comparison.compare(self.left, output)
        self.assertEqual([call.args[0] for call in validate.call_args_list], [self.left, output])

    def test_cli_rejects_corrupt_artifacts_with_json_and_nonzero_status(self):
        output = self.copy_right()
        (output / "paired_diagnostics.json").write_text("{}", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "-B", str(ROOT / "scripts" / "compare_research_outputs.py"),
             str(self.left), str(output)], cwd=self.root, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "failed")
        self.assertIn("Artifact SHA256 mismatch", report["error"])
        self.assertTrue(report["read_only"])


if __name__ == "__main__":
    unittest.main()

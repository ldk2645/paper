"""Read-only validation of stored S0 artifacts and rehashed inconsistencies."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from abm_jasss.research_cli import run_study


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate_research_outputs.py"
RUN_ID = "E2_a00_seed701_I00"


def small_spec():
    return {"stage": "S0", "formal_ready": False,
            "model": {"n_agents": 12, "survey_size": 4, "steps": 12,
                      "final_window": 4, "inference_grid": 2, "reference_agents": 2,
                      "completion_start": 2, "completion_end": 8, "completion_followup": 3},
            "alphas": [.25], "seeds": [701], "fork_tick": 6,
            "branches": {"B0": {}, "B1": {"pref_info": True},
                         "B2": {"government_delay": 1}, "B3": {"response_capacity": 2},
                         "B4": {"alpha": 0.0}}}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def rewrite(path, value):
    path.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")


def refresh_hash(output, relative):
    hashes = read(output / "artifact_hashes.json")
    hashes[relative] = hashlib.sha256((output / relative).read_bytes()).hexdigest()
    rewrite(output / "artifact_hashes.json", hashes)


def fingerprint(folder):
    """Include paths, bytes and modification times, but not read access times."""
    return {path.relative_to(folder).as_posix(): (
                path.stat().st_mtime_ns,
                hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None)
            for path in (folder, *folder.rglob("*"))}


class ResearchValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.fixture = Path(cls.temporary.name) / "fixture"
        manifest = run_study(small_spec(), cls.fixture)
        if manifest["status"] != "complete":
            raise AssertionError("Small S0 fixture failed to complete")

    def copy_fixture(self, root, name="output"):
        output = root / name
        shutil.copytree(self.fixture, output)
        return output

    def validate(self, output, expected_error=None, script=VALIDATOR):
        before = fingerprint(output)
        result = subprocess.run([sys.executable, "-B", str(script), str(output)],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(fingerprint(output), before, "Validator changed stored artifacts")
        self.assertEqual(result.stderr, "", result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["read_only"])
        if expected_error is None:
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual(report["status"], "passed")
        else:
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(report["status"], "failed")
            self.assertIn(expected_error, report["error"])
        return report

    def test_complete_batch_rebuild_is_read_only(self):
        report = self.validate(self.fixture)
        self.assertFalse(report["formal_ready"])
        self.assertEqual(report["groups"], 1)
        self.assertEqual(report["e2_worlds"], 4)
        self.assertEqual(report["e4_suffixes"], 5)
        self.assertEqual(report["rebuilt_world_summaries"], 9)
        self.assertEqual(report["trajectory_records"], 108)
        self.assertTrue(report["paired_diagnostics_rebuilt"])

    def test_changed_missing_and_unlisted_artifacts_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for change in ("changed", "missing", "unlisted"):
                with self.subTest(change=change):
                    output = self.copy_fixture(root, change)
                    path = output / "report.md"
                    if change == "changed":
                        path.write_bytes(path.read_bytes() + b"\n")
                    elif change == "missing":
                        path.unlink()
                    else:
                        (output / "unlisted.json").write_text("{}", encoding="utf-8")
                    error = "Artifact SHA256 mismatch" if change == "changed" else "Artifact file set mismatch"
                    self.validate(output, error)

    def test_rehashed_summary_pairing_and_log_changes_are_rejected(self):
        cases = ((f"derived/{RUN_ID}.json", "summary", "Derived summary mismatch"),
                 ("paired_diagnostics.json", "pairing", "Paired diagnostics rebuild mismatch"),
                 (f"raw/{RUN_ID}/evaluator/trajectory.json", "log", "Snapshot/log mismatch"))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for relative, kind, error in cases:
                with self.subTest(change=kind):
                    output = self.copy_fixture(root, kind)
                    path = output / relative
                    value = read(path)
                    if kind == "summary":
                        value["summary"]["scheduled_count_total"] += 1
                    elif kind == "pairing":
                        value["0.25"]["E4"]["perception_error"]["B1"]["scope"] = "altered"
                    else:
                        value[0]["available_packet_id"] = "unrecorded-packet"
                    rewrite(path, value)
                    refresh_hash(output, relative)
                    self.validate(output, error)

    def test_rehashed_duplicate_keys_and_nonfinite_json_are_rejected(self):
        cases = (("duplicate", '{"value":1,"value":2}', "Duplicate JSON key"),
                 ("nan", '{"value":NaN}', "Nonfinite JSON value"),
                 ("infinity", '{"value":Infinity}', "Nonfinite JSON value"),
                 ("negative_infinity", '{"value":-Infinity}', "Nonfinite JSON value"))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, document, error in cases:
                with self.subTest(value=name):
                    output = self.copy_fixture(root, name)
                    relative = "paired_diagnostics.json"
                    (output / relative).write_text(document, encoding="utf-8")
                    refresh_hash(output, relative)
                    self.validate(output, error)

    def test_validation_needs_matching_analyzer_but_no_live_simulator(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            package = root / "abm_jasss"
            package.mkdir()
            script = root / "scripts" / VALIDATOR.name
            shutil.copyfile(VALIDATOR, script)
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "research_world.py").write_text(
                'raise RuntimeError("Stored validation must not load the simulator")\n', encoding="utf-8")
            analyzer = package / "research_outcomes.py"
            shutil.copyfile(ROOT / "abm_jasss" / analyzer.name, analyzer)
            before = fingerprint(root)
            self.validate(self.fixture, script=script)
            self.assertEqual(fingerprint(root), before, "Validator wrote into its source tree")
            analyzer.write_bytes(analyzer.read_bytes() + b"\n# changed analyzer\n")
            self.validate(self.fixture, "Live research_outcomes.py differs", script=script)

    def test_default_completion_end_resolves_after_branch_enrollment(self):
        spec = small_spec()
        del spec["model"]["completion_end"]
        spec["model"]["completion_followup"] = 20
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            self.assertEqual(run_study(spec, output)["status"], "complete")
            for folder in (output / "raw").glob("E4_*"):
                analysis = read(folder / "metadata.json")["analysis_config"]
                self.assertEqual(analysis["completion_start"], 6)
                self.assertEqual(analysis["completion_end"], 6)
            self.validate(output)


if __name__ == "__main__":
    unittest.main()

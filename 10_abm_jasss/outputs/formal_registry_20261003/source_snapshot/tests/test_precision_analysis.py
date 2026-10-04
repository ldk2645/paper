"""Combine synthetic archives without simulating or consuming pilot seeds."""
from contextlib import contextmanager
import csv
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from abm_jasss.research_world import canonical_hash
from scripts.analyze_precision_pilot import ROOT, analyze, sha256
from scripts.precision_statistics import PRIMARY_METRICS, build_precision_analysis
from scripts.run_precision_pilot import analysis_spec, resolve_design
from scripts.validate_s1_outputs import read


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True, allow_nan=False, indent=2) + "\n",
                    encoding="utf-8")


def fingerprint(directory):
    return {path.relative_to(directory).as_posix(): sha256(path)
            for path in directory.rglob("*") if path.is_file()}


def refresh_inventory(directory):
    write_json(directory / "artifact_hashes.json",
               {name: digest for name, digest in fingerprint(directory).items()
                if name != "artifact_hashes.json"})


def make_wave(directory, spec, wave):
    """Write analysis-interface fixtures; these are not physical pilot runs."""
    directory.mkdir()
    jobs = resolve_design(spec, wave)
    registered = analysis_spec(spec, spec[wave + "_seeds"])
    records = []
    for job in jobs:
        for family, contrasts in registered["contrasts"].items():
            arms = sorted({arm for coefficients in contrasts.values() for arm in coefficients})
            for index, arm in enumerate(arms):
                value = .25 + index * .03 + (job["seed"] % 3) * index * .001
                records.append({"family": family, "alpha": job["alpha"],
                                "parent_id": job["seed"], "arm": arm, "status": "complete",
                                "metrics": {metric: value for metric in PRIMARY_METRICS}})
    sources = {path.name: sha256(path) for path in sorted((ROOT / "abm_jasss").glob("*.py"))}
    for folder, names in (("abm_jasss", sources),
                          ("scripts", ("precision_statistics.py", "run_precision_pilot.py"))):
        destination = directory / "source_snapshot" / folder
        destination.mkdir(parents=True)
        for name in names:
            shutil.copyfile(ROOT / folder / name, destination / name)
    manifest = {"schema_version": "precision-batch-1", "stage": "precision_pilot",
                "formal_ready": False, "wave": wave, "status": "complete", "failed_groups": 0,
                "batch_id": "synthetic_analysis_" + wave, "specification": spec,
                "specification_hash": canonical_hash(spec), "source_hash": spec["expected_source_hash"],
                "source_sha256": sources, "expected_groups": len(jobs), "completed_groups": len(jobs),
                "complete_records": 18 * len(jobs)}
    for name, value in (("manifest.json", manifest), ("configuration.json", spec),
                        ("resolved_design.json", jobs), ("failures.json", []),
                        ("statistical_records.json", records),
                        ("precision_analysis.json", build_precision_analysis(records, registered))):
        write_json(directory / name, value)
    (directory / "raw").mkdir()
    (directory / "raw" / "sentinel.txt").write_text("synthetic raw artifact\n", encoding="utf-8")
    refresh_inventory(directory)
    return {"status": "passed", "read_only": True, "formal_ready": False,
            "batch_id": manifest["batch_id"], "source_hash": manifest["source_hash"],
            "manifest_hash": sha256(directory / "manifest.json"),
            "artifact_inventory_hash": sha256(directory / "artifact_hashes.json")}


class PrecisionCombinedAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.base = Path(cls.temporary.name)
        cls.spec = read(ROOT / "configs" / "precision_pilot_20260930.json")
        cls.spec["initial_seeds"] = list(range(98201, 98221))
        cls.spec["expansion_seeds"] = list(range(98221, 98241))
        cls.initial, cls.expansion = cls.base / "initial", cls.base / "expansion"
        cls.reports = {}
        for wave, directory in (("initial", cls.initial), ("expansion", cls.expansion)):
            cls.reports[wave] = cls.base / (wave + "_validation.json")
            write_json(cls.reports[wave], make_wave(directory, cls.spec, wave))

    def setUp(self):
        self.output = self.base / self._testMethodName

    def combine(self, **kwargs):
        settings = {"validation_initial": self.reports["initial"],
                    "validation_expansion": self.reports["expansion"]}
        settings.update(kwargs)
        return analyze(self.initial, self.expansion, self.output, **settings)

    @contextmanager
    def altered(self, directory, replacements, *, rehash=True):
        paths = [directory / name for name in replacements]
        if rehash:
            paths.append(directory / "artifact_hashes.json")
        originals = {path: path.read_bytes() if path.exists() else None for path in paths}
        try:
            for name, value in replacements.items():
                path = directory / name
                if value is None:
                    path.unlink()
                elif isinstance(value, str):
                    path.write_text(value, encoding="utf-8")
                else:
                    write_json(path, value)
            if rehash:
                refresh_inventory(directory)
            yield
        finally:
            for path, payload in originals.items():
                if payload is None:
                    if path.exists():
                        path.unlink()
                else:
                    path.write_bytes(payload)

    def test_complete_combination_retains_40_parents_and_exact_inputs_read_only(self):
        before = {wave: fingerprint(directory) for wave, directory in
                  (("initial", self.initial), ("expansion", self.expansion))}
        with patch("abm_jasss.research_world.ResearchWorld.step", side_effect=AssertionError("simulation")):
            manifest = self.combine()
        self.assertTrue(manifest["semantic_validation_complete"])
        self.assertEqual(manifest["planning_items"], 102)
        self.assertFalse(manifest["formal_ready"])
        planning = read(self.output / "planning.json")
        self.assertEqual(planning["parent_ids"], list(map(str, range(98201, 98241))))
        records = read(self.initial / "statistical_records.json") + read(self.expansion / "statistical_records.json")
        expected = build_precision_analysis(records, analysis_spec(self.spec, range(98201, 98241)))
        self.assertEqual(planning, expected)
        self.assertEqual(len(read(self.output / "stability.json")["items"]), 102)
        with (self.output / "planning.csv").open(encoding="utf-8", newline="") as stream:
            self.assertEqual(len(list(csv.DictReader(stream))), 102)
        for wave, directory in (("initial", self.initial), ("expansion", self.expansion)):
            self.assertEqual(fingerprint(directory), before[wave])
            self.assertEqual(manifest["validation"][wave]["artifact_inventory_hash"],
                             sha256(directory / "artifact_hashes.json"))
        hashes = read(self.output / "artifact_hashes.json")
        self.assertEqual(hashes, {name: digest for name, digest in fingerprint(self.output).items()
                                  if name != "artifact_hashes.json"})

    def test_missing_validation_reports_leave_semantic_validation_pending(self):
        manifest = self.combine(validation_initial=None, validation_expansion=None)
        self.assertFalse(manifest["semantic_validation_complete"])
        self.assertFalse(manifest["formal_ready"])
        self.assertTrue(all(item["status"] == "not_provided" for item in manifest["validation"].values()))

    def test_old_report_without_inventory_binding_requires_revalidation(self):
        report = read(self.reports["initial"])
        del report["artifact_inventory_hash"]
        with self.altered(self.base, {self.reports["initial"].name: report}, rehash=False):
            with self.assertRaisesRegex(ValueError, "artifact inventory; rerun semantic validation"):
                self.combine()
        self.assertFalse(self.output.exists())

    def test_rehashed_changed_statistics_reject_stale_report_with_unchanged_manifest(self):
        records = read(self.initial / "statistical_records.json")
        records[0]["metrics"][PRIMARY_METRICS[0]] += .1
        analysis = build_precision_analysis(records, analysis_spec(self.spec, self.spec["initial_seeds"]))
        manifest_hash = sha256(self.initial / "manifest.json")
        with self.altered(self.initial, {"statistical_records.json": records,
                                         "precision_analysis.json": analysis}):
            self.assertEqual(sha256(self.initial / "manifest.json"), manifest_hash)
            with self.assertRaisesRegex(ValueError, "Validation report is not bound to this artifact inventory"):
                self.combine()
        self.assertFalse(self.output.exists())

    def test_raw_mutation_is_detected_even_when_analysis_summaries_are_unchanged(self):
        for rehash in (False, True):
            expected = "artifact inventory" if rehash else "Input hash mismatch: initial/raw/sentinel.txt"
            with self.subTest(rehash=rehash), self.altered(
                    self.initial, {"raw/sentinel.txt": "changed raw artifact\n"}, rehash=rehash):
                with self.assertRaisesRegex(ValueError, expected):
                    self.combine()
        self.assertFalse(self.output.exists())

    def test_missing_or_extra_artifact_fails_closed(self):
        for replacements in ({"raw/sentinel.txt": None}, {"extra.txt": "unregistered artifact"}):
            with self.subTest(replacements=replacements), self.altered(self.initial, replacements, rehash=False):
                with self.assertRaisesRegex(ValueError, "Input artifact file inventory mismatch"):
                    self.combine()
        self.assertFalse(self.output.exists())

    def test_existing_output_is_preserved(self):
        self.output.mkdir()
        sentinel = self.output / "preserve.txt"
        sentinel.write_text("original", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Output already exists"):
            self.combine()
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "original")


if __name__ == "__main__":
    unittest.main()

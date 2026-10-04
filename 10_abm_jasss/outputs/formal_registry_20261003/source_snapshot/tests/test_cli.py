import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from abm_jasss.cli import main


class CLITests(unittest.TestCase):
    def test_failed_world_prevents_aggregate_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, output = root / "config.json", root / "output"
            config.write_text(json.dumps({"model": {}, "alphas": [.5], "seeds": [1]}))
            argv = ["runner", "--config", str(config), "--output", str(output)]
            with patch.object(sys, "argv", argv), patch("abm_jasss.cli.task", side_effect=RuntimeError("deliberate test failure")):
                with self.assertRaises(SystemExit):
                    main()
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["failed_world_runs"], 1)
            self.assertTrue((output / "failures.json").exists())
            self.assertFalse((output / "aggregate.csv").exists())

    def test_serial_parallel_and_preservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "config.json"
            config.write_text(json.dumps({"model": {"n_agents": 12, "survey_size": 4, "steps": 15, "final_window": 5},
                                          "alphas": [0, .7], "seeds": [11, 12], "save_trajectories": True}))
            outputs = [root / "serial", root / "parallel"]
            for workers, output in zip([1, 2], outputs):
                command = [sys.executable, "-m", "abm_jasss.cli", "--config", str(config), "--output", str(output), "--workers", str(workers)]
                run = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stderr)
                manifest = json.loads((output / "manifest.json").read_text())
                self.assertEqual(manifest["status"], "complete")
                for filename, digest in manifest["source_sha256"].items():
                    copied = output / "source_snapshot" / "abm_jasss" / filename
                    self.assertEqual(hashlib.sha256(copied.read_bytes()).hexdigest(), digest)
                before = (output / "runs.csv").read_bytes()
                refused = subprocess.run(command, capture_output=True, text=True)
                self.assertNotEqual(refused.returncode, 0)
                self.assertEqual(before, (output / "runs.csv").read_bytes())
            for name in ["runs.csv", "aggregate.csv", "paired_contrasts.csv"]:
                self.assertEqual((outputs[0] / name).read_bytes(), (outputs[1] / name).read_bytes())
            for trajectory in (outputs[0] / "trajectories").glob("*.csv"):
                self.assertEqual(trajectory.read_bytes(), (outputs[1] / "trajectories" / trajectory.name).read_bytes())


if __name__ == "__main__":
    unittest.main()

"""Registration and immutable-pilot runner checks; no formal/pilot seeds consumed."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from abm_jasss.research_world import source_hash
from scripts.run_precision_pilot import ROOT, resolve_design, run_study, statistical_records, analysis_spec
from scripts.validate_s1_outputs import read


class PilotRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.spec = read(ROOT / "configs" / "precision_pilot_20260930.json")

    def test_registered_design_is_fixed_and_complete(self):
        first = resolve_design(self.spec, "initial")
        second = resolve_design(self.spec, "expansion")
        self.assertEqual((len(first), len(second)), (40, 40))
        self.assertFalse({j['seed'] for j in first} & {j['seed'] for j in second})
        self.assertEqual(len({j['seed'] for j in first + second}), 40)
        self.assertEqual(first[0]['model']['n_agents'], 100)
        self.assertEqual(first[0]['model']['steps'], 300)
        self.assertEqual(first[0]['model']['survey_size'], 12)
        self.assertEqual(first[0]['model']['completion_end'], 279)
        self.assertEqual(source_hash(), self.spec['expected_source_hash'])
        self.assertEqual(sum(len(c) for c in analysis_spec(self.spec, [1])['contrasts'].values()), 17)

    def test_rejects_unregistered_timing_or_treatment(self):
        for key, value in [('fork_tick', 250), ('formal_ready', True), ('extra', True)]:
            changed = deepcopy(self.spec)
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                resolve_design(changed, 'initial')
        for field, value in [('completion_start', 149), ('completion_end', 280), ('government_delay', 2)]:
            changed = deepcopy(self.spec)
            changed['model'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                resolve_design(changed, 'initial')
        changed = deepcopy(self.spec)
        changed['expansion_seeds'][0] = changed['initial_seeds'][0]
        with self.assertRaises(ValueError):
            resolve_design(changed, 'initial')

    def test_existing_output_preserved_before_any_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            sentinel = output / 'preserve.txt'
            sentinel.write_text('original', encoding='utf-8')
            with patch('scripts.run_precision_pilot.ProcessPoolExecutor') as pool:
                with self.assertRaisesRegex(ValueError, 'already exists'):
                    run_study(self.spec, output)
                pool.assert_not_called()
            self.assertEqual(sentinel.read_text(encoding='utf-8'), 'original')


if __name__ == '__main__':
    unittest.main()

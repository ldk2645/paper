"""Configuration rejects enrollment windows that cannot be summarized."""
import unittest

from abm_jasss.research_config import ResearchConfig
from abm_jasss.research_outcomes import summarize_world


class ResearchConfigTests(unittest.TestCase):
    def test_enrollment_start_outside_horizon_is_rejected_before_execution(self):
        for start in (12, 20):
            with self.subTest(start=start), self.assertRaisesRegex(ValueError, "completion_start"):
                ResearchConfig(steps=12, final_window=4, completion_start=start)

    def test_last_tick_enrollment_is_valid_and_retains_followup_censoring(self):
        config = ResearchConfig(steps=12, final_window=4, completion_start=11)
        resolved = config.analysis_config()
        result = summarize_world([], [], resolved)
        self.assertEqual(resolved["completion_end"], 11)
        self.assertEqual(result["completion"]["planned_followup_end"], 31)
        self.assertEqual(result["completion"]["status"], "incomplete_enrollment")
        self.assertIsNone(result["response_completion_L"])


if __name__ == "__main__":
    unittest.main()

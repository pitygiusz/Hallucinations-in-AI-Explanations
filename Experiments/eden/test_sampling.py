"""Offline sampling checks; no GPU or model dependencies required."""
import json
import random
import tempfile
import unittest
from pathlib import Path

import eden_charxiv_gemma as gemma
import eden_charxiv_qwen as qwen


class SamplingTests(unittest.TestCase):
    def test_previous_charts_are_excluded_and_models_match(self):
        root = gemma.PROJECT_ROOT
        paths = [root / "outputs" / name / "results.json" for name in
                 ("eden_gemma4_e4b", "eden_qwen3_5_9b")]
        figures = [f"images/{i}.jpg" for i in range(2323)]
        selections = []
        for module in (gemma, qwen):
            excluded = module.exclusion_figures(paths, None)
            self.assertEqual(len(excluded), 125)
            selected = module.select_charts(figures, ["Q"] * len(figures),
                                            ["A"] * len(figures), 125, 20261126, excluded)
            self.assertEqual(len(set(selected)), 125)
            self.assertFalse({figures[i] for i in selected} &
                             (set(excluded) | module.PILOT_FIGURES))
            selections.append(selected)
        self.assertEqual(*selections)

    def test_default_sampling_is_unchanged_and_filters_missing_qa(self):
        figures = ["images/new1.jpg", "images/56.jpg", "images/new2.jpg",
                   "images/new3.jpg", "images/new4.jpg"]
        for module in (gemma, qwen):
            self.assertEqual(module.select_charts(figures, ["Q"] * 5,
                             ["A", "A", "A", "", None], 2, 42, []),
                             random.Random(42).sample([0, 2], 2))
            with self.assertRaisesRegex(ValueError, "only 1 remain"):
                module.select_charts(figures, ["Q"] * 5,
                                     ["A", "A", "A", "", None], 2, 42,
                                     ["images/new1.jpg"])

    def test_resume_restores_exclusions_and_old_checkpoints(self):
        for module in (gemma, qwen):
            self.assertEqual(module.exclusion_figures([], {}), [])
            self.assertEqual(module.exclusion_figures([], {
                "excluded_previous_figures": ["images/a.jpg"]}), ["images/a.jpg"])

    def test_invalid_sources_and_changed_resume_exclusions_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results.json"
            for module in (gemma, qwen):
                document = {"dataset": module.DATASET_ID, "split": module.SPLIT,
                            "results": [{"example_id": "images/a.jpg"}]}
                path.write_text(json.dumps(document))
                with self.assertRaisesRegex(ValueError, "Cannot resume"):
                    module.exclusion_figures([path], {})
                self.assertEqual(module.exclusion_figures([path], {
                    "excluded_previous_figures": ["images/a.jpg"]}), ["images/a.jpg"])
                document["split"] = "test"
                path.write_text(json.dumps(document))
                with self.assertRaisesRegex(ValueError, "must be an Eden"):
                    module.exclusion_figures([path], None)
                document["split"] = module.SPLIT
                document["results"] = [{}]
                path.write_text(json.dumps(document))
                with self.assertRaisesRegex(ValueError, "example_id"):
                    module.exclusion_figures([path], None)


if __name__ == "__main__":
    unittest.main()

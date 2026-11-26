"""Count integrity and frozen-protocol compatibility, without API calls."""
import copy
import unittest
from jsonschema import ValidationError
import judge_common as shared
import judge_schema as schema
import judge_schema_legacy as legacy
from test_openai_batch_judge import answer, ground, legacy_ground


class CompactTests(unittest.TestCase):
    def setUp(self):
        self.record = {"final_explanation": "Value is 2. Correction: value is 1.",
                       "returned_reasoning": "", "generation_system_prompt": "Answer briefly."}

    def validate(self, value):
        schema.validate_judgment("grounding", value, self.record, schema.SCHEMAS)

    def test_retracted_errors_do_not_pollute_retained_metrics(self):
        value = ground()
        value["final_explanation"].update(total_claims=2, corrected_claims=1)
        self.validate(value)
        metrics = shared.field_metrics(value, self.record, "final_explanation")
        self.assertEqual(metrics["claim_count"], 2)
        self.assertEqual(metrics["retained_claim_count"], 1)
        self.assertFalse(metrics["unsupported"])
        self.assertIsNone(metrics["observed_unsupported"])
        self.assertIsNone(metrics["numerical_mismatch_count"])

    def test_material_counts_are_subsets_and_categories_match(self):
        for changes in [dict(corrected_claims=2), dict(material_errors=2),
                        dict(material_contradictions=0), dict(error_categories=[]),
                        dict(error_categories=["chart_reading", "chart_reading"])]:
            with self.subTest(changes=changes):
                value = ground("contradicted")
                value["final_explanation"].update(changes)
                with self.assertRaises(ValueError):
                    self.validate(value)

    def test_review_is_null_and_absence_is_distinct_from_no_claims(self):
        value = ground()
        field = value["final_explanation"]
        field.update({key: None for key in field})
        field["status"] = "requires_review"
        self.validate(value)
        self.assertIsNone(shared.field_metrics(value, self.record, "final_explanation")["unsupported"])
        field["total_claims"] = 0
        with self.assertRaises(ValueError):
            self.validate(value)
        value = ground()
        value["returned_reasoning"]["status"] = "no_claims"
        with self.assertRaisesRegex(ValueError, "Absent"):
            self.validate(value)

    def test_response_quotations_are_not_accepted_in_compact_output(self):
        value = ground()
        value["final_explanation"]["claims"] = []
        with self.assertRaises(ValidationError):
            self.validate(value)
        value = answer(followed=True)
        value["extracted_answer"] = "1"
        with self.assertRaises(ValidationError):
            schema.validate_judgment("answer", value, self.record, schema.SCHEMAS)

    def test_material_rates_and_all_error_counts_stay_distinct(self):
        value = ground("contradicted")
        value["final_explanation"].update(total_claims=4, contradicted_claims=2,
                                           unsupported_claims=1)
        self.validate(value)
        metrics = shared.field_metrics(value, self.record, "final_explanation")
        self.assertEqual(metrics["claim_error_rate"], .25)
        self.assertEqual(metrics["contradicted_claim_count"], 2)
        self.assertEqual(metrics["unsupported_claim_count"], 1)

    def test_legacy_schema_dispatch_still_validates_quotes(self):
        record = {**self.record, "final_explanation": "1"}
        schema.validate_judgment("grounding", legacy_ground(), record, legacy.SCHEMAS)
        bad = legacy_ground()
        bad["final_explanation"]["claims"][0]["quote"] = "not in source"
        with self.assertRaisesRegex(ValueError, "verbatim"):
            schema.validate_judgment("grounding", bad, record, legacy.SCHEMAS)


if __name__ == "__main__":
    unittest.main()

"""Offline regression checks; never contact OpenAI or submit paid work."""
import argparse
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import openai_batch_judge as judge


def field(quote="1", verdict="supported", review=False):
    return {"applicable": True, "coverage_complete": True, "requires_review": review,
            "review_reason": "", "claims": [{"quote": quote, "verdict": verdict,
            "categories": [] if verdict == "supported" else ["chart_reading"],
            "material": True, "evidence": "The bar is labeled 1.",
            "resolution": "retained", "correction_quote": "", "numeric_reference": "", "numeric_value": None}]}


def ground(verdict="supported"):
    return {"chart_readability": "readable", "chart_types": ["bar"], "final_explanation": field(verdict=verdict),
            "returned_reasoning": {"applicable": False, "coverage_complete": True,
                                   "requires_review": False, "review_reason": "", "claims": []}}


def answer(verdict="correct", followed=None, reason="Saved generation prompt is unavailable."):
    return {"extracted_answer": "1", "verdict": verdict, "justification": "Reference comparison.",
            "strategy_followed": followed, "strategy_following_reason": reason}


class JudgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "experiment.json"
        for c in range(2):
            (self.root / f"image{c}.png").write_bytes(f"local-image-fixture-{c}".encode())
        records = [{"example_id": f"images/{c}.png", "question": f"Question {c}?",
                    "correct_answer": "1", "image_path": f"image{c}.png", "prompt_strategy": s,
                    "model_answer": "Final answer: 1", "model_reasoning": "",
                    "generation_truncated": False} for c in range(2) for s in ["direct", "structured"]]
        judge.save(self.source, {"dataset": "test", "split": "validation", "model": "generator-secret",
                                 "results": records})
        self.run_dir = self.root / "run"
        self.args = argparse.Namespace(run=self.run_dir, inputs=[self.source], model="gpt-6.2-sol",
            effort="medium", seed=42, repeat_fraction=0, max_shard_mb=.02,
            answer_tokens=2048, grounding_tokens=12000, chart_limit=None)

    def prepare(self):
        judge.prepare(self.args)
        return judge.load_manifest(self.run_dir)

    def test_blinding_identity_sharding_and_frozen_protocol(self):
        manifest = self.prepare()
        self.assertEqual(len(manifest["tasks"]), 8)
        self.assertGreater(len(manifest["chunks"]), 1)
        requests = [r for c in manifest["chunks"] for r in judge.lines(self.run_dir / c["path"])]
        self.assertEqual(len({r["custom_id"] for r in requests}), 8)
        for r in requests:
            body = r["body"]
            serialized = json.dumps(body)
            self.assertNotIn("generator-secret", serialized)
            if "-grounding-" in r["custom_id"]:
                data = json.loads(body["input"][0]["content"][0]["text"])
                self.assertNotIn("reference_answer", data)
                self.assertNotIn("prompt_strategy", data)
                self.assertEqual(body["input"][0]["content"][1]["detail"], "high")
        for packet in judge.lines(self.run_dir / "human_grounding_packets.jsonl"):
            self.assertNotIn("generator-secret", json.dumps(packet))
            self.assertNotIn("reference_answer", packet)
            self.assertTrue((self.run_dir / packet["image_path"]).exists())
        manifest["effort"] = "high"
        judge.save(self.run_dir / "manifest.json", manifest)
        with self.assertRaisesRegex(ValueError, "protocol"):
            judge.load_manifest(self.run_dir)

    def test_quotes_coverage_and_unknowns_are_not_clean(self):
        record = {"final_explanation": "Final answer: 1", "returned_reasoning": ""}
        judge.validate_judgment("grounding", ground(), record, judge.SCHEMAS)
        bad = ground()
        bad["final_explanation"]["claims"][0]["quote"] = "invented quote"
        with self.assertRaisesRegex(ValueError, "verbatim"):
            judge.validate_judgment("grounding", bad, record, judge.SCHEMAS)
        self.assertIsNone(judge.field_metrics(None, record, "final_explanation")["unsupported"])
        uncertain = ground()
        uncertain["final_explanation"]["coverage_complete"] = False
        self.assertIsNone(judge.field_metrics(uncertain, record, "final_explanation")["unsupported"])
        self.assertTrue(judge.field_metrics(ground("insufficient_evidence"), record, "final_explanation")["unsupported"])
        self.assertFalse(judge.field_metrics(ground("insufficient_evidence"), record, "final_explanation")["contradicted"])

    def test_collect_out_of_order_failure_retry_and_statistics(self):
        manifest = self.prepare()
        records = judge.lines(self.run_dir / "records.jsonl")
        tasks = manifest["tasks"]
        outputs = []
        failed_task = tasks[0]["custom_id"]
        for task in reversed(tasks):
            j = answer() if task["kind"] == "answer" else ground("contradicted")
            body = {"model": "judge-snapshot", "status": "completed", "usage": {"input_tokens": 10, "output_tokens": 20},
                    "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(j)}]}]}
            if task["custom_id"] == failed_task:
                body["status"] = "incomplete"
            outputs.append({"custom_id": task["custom_id"], "response": {"status_code": 200, "body": body}})
        # Put all fake responses in one terminal batch, regardless of preparation sharding.
        manifest["chunks"] = [{**manifest["chunks"][0], "batch_id": "batch_fake"}]
        judge.save(self.run_dir / "manifest.json", manifest)
        raw = self.run_dir / "raw"
        raw.mkdir()
        judge.jsonl(raw / "batch_fake-file_fake.jsonl", outputs)
        batch = SimpleNamespace(id="batch_fake", status="completed", output_file_id="file_fake", error_file_id=None,
                                model_dump=lambda **kwargs: {"status": "completed"})
        api = SimpleNamespace(batches=SimpleNamespace(retrieve=lambda _: batch))
        with patch.object(judge, "client", return_value=api):
            judge.collect(argparse.Namespace(run=self.run_dir))
        labels = {r["custom_id"]: r for r in judge.lines(self.run_dir / "judgments.jsonl")}
        self.assertEqual(labels[failed_task]["status"], "invalid")
        rows, _ = judge.joined(self.run_dir, manifest)
        self.assertEqual(sum(r["answer_correct"] is None for r in rows), 1)
        estimate = judge.estimate(rows, "answer_accuracy", 100, 42)
        self.assertEqual(estimate["denominator"], 3)
        self.assertEqual(estimate["value"], 1)
        self.assertEqual(estimate["contributing_charts"], 2)
        self.assertEqual(judge.estimate(rows, "correct_answer_either_contradicted", 100, 42)["denominator"], 3)
        judge.report(argparse.Namespace(run=self.run_dir, human_labels=None, bootstrap=100, seed=42,
                                      input_usd_per_million=1, output_usd_per_million=5,
                                      cached_input_usd_per_million=.05))
        summary = judge.read(self.run_dir / "summary.json")
        self.assertEqual(summary["usage_including_retries_and_repeats"]["output_tokens"], 160)
        self.assertFalse(summary["human_agreement"]["available"])
        self.assertAlmostEqual(summary["estimated_api_cost"]["usd"], .00088)
        self.assertTrue((self.run_dir / "review_queue.jsonl").exists())

    def test_cluster_bootstrap_retains_chart_dependence(self):
        pairs = [("a", True, True)] * 8 + [("b", False, True)] * 8
        result = judge.agreement_ci(pairs, 200, 42)
        self.assertEqual(result["n"], 16)
        self.assertEqual(result["charts"], 2)
        self.assertEqual(result["ci95"]["accuracy"], [0, 1])
        self.assertIsNone(judge.agreement([])["precision"])
        self.assertIsNone(judge.agreement([(True, True)])["cohen_kappa"])

    def test_human_agreement_and_missing_labels(self):
        self.prepare()
        records = judge.lines(self.run_dir / "records.jsonl")
        outcomes = []
        for record in records:
            for kind in ["answer", "grounding"]:
                judgment = (answer()
                            if kind == "answer" else ground("contradicted"))
                outcomes.append({"custom_id": record["response_id"] + f"-{kind}-0", "status": "valid", "judgment": judgment})
        judge.jsonl(self.run_dir / "judgments.jsonl", outcomes)
        rows, _ = judge.joined(self.run_dir, judge.load_manifest(self.run_dir))
        path = self.root / "humans.jsonl"
        judge.jsonl(path, [{"response_id": r["response_id"], "annotator": name, "answer_correct": True,
                           "final_explanation_contradicted": True, "final_explanation_unsupported": True}
                          for r in rows for name in ["a", "b"]])
        result = judge.human_agreement(path, rows, 100, 42)
        self.assertEqual(result["judge_vs_human"]["a"]["final_explanation_contradicted"]["f1"], 1)
        self.assertEqual(result["human_vs_human"]["a vs b"]["answer_correct"]["n"], 4)
        self.assertEqual(result["judge_vs_human"]["a"]["returned_reasoning_unsupported"]["n"], 0)

    def test_human_claim_inventory_derives_labels_and_rejects_conflicts(self):
        self.prepare()
        records = judge.lines(self.run_dir / "records.jsonl")
        path = self.root / "claims.jsonl"
        entry = {"response_id": records[0]["response_id"], "annotator": "a", "claim_annotations": ground("contradicted")}
        judge.jsonl(path, [entry])
        normalized = judge.human_entries(path, records)
        self.assertTrue(normalized[0]["final_explanation_unsupported"])
        entry["final_explanation_unsupported"] = False
        judge.jsonl(path, [entry])
        with self.assertRaisesRegex(ValueError, "conflicts"):
            judge.human_entries(path, records)

    def test_verification_transitions_and_shared_success_pairs(self):
        self.prepare()
        records = judge.lines(self.run_dir / "records.jsonl")
        outcomes = []
        for r in records:
            correct = r["strategy"] == "direct"
            outcomes.extend([
                {"custom_id": r["response_id"] + "-answer-0", "status": "valid", "judgment": {
                    **answer("correct" if correct else "incorrect")}},
                {"custom_id": r["response_id"] + "-grounding-0", "status": "valid", "judgment": ground()}])
        judge.jsonl(self.run_dir / "judgments.jsonl", outcomes)
        rows, _ = judge.joined(self.run_dir, judge.load_manifest(self.run_dir))
        rows[0]["draft_answer_correct"] = False
        rows[0]["draft_final_metrics"] = {"unsupported": True}
        metrics = judge.metric_values(rows[0])
        self.assertTrue(metrics["verification_answer_recovery"])
        self.assertTrue(metrics["verification_error_recovery"])
        comparison = next(c for c in judge.paired_comparisons(rows, 100, 42)
                          if c["metric"] == "correct_answer_final_explanation_unsupported")
        self.assertEqual(comparison["paired_charts"], 0)
        self.assertEqual(comparison["matched_chart_candidates"], 2)
        self.assertIsNone(comparison["difference_right_minus_left"])

    def test_report_uses_verified_chart_types_and_excludes_unknown_truncation(self):
        metadata = self.root / "metadata.json"
        judge.save(metadata, {"images/0.png": {"chart_types": ["line", "scatter"], "human_verified": True}})
        self.args.chart_metadata = metadata
        self.prepare()
        records = judge.lines(self.run_dir / "records.jsonl")
        # Freeze unknown truncation through preparation, rather than editing a run.
        source = judge.read(self.source)
        source["results"][0]["generation_truncated"] = None
        judge.save(self.source, source)
        self.args.run = self.root / "unknown-truncation"
        judge.prepare(self.args)
        records = judge.lines(self.args.run / "records.jsonl")
        outcomes = []
        for r in records:
            outcomes.extend([
                {"custom_id": r["response_id"] + "-answer-0", "status": "valid", "judgment": {
                    **answer()}},
                {"custom_id": r["response_id"] + "-grounding-0", "status": "valid", "judgment": ground()}])
        judge.jsonl(self.args.run / "judgments.jsonl", outcomes)
        judge.report(argparse.Namespace(run=self.args.run, human_labels=None, bootstrap=100, seed=42,
            input_usd_per_million=None, output_usd_per_million=None, cached_input_usd_per_million=None))
        summary = judge.read(self.args.run / "summary.json")
        self.assertTrue(any("chart_type=line" in key for key in summary["groups"]))
        self.assertFalse(any("chart_type=bar" in key for key in summary["groups"]))
        self.assertEqual(summary["untruncated_sensitivity"]["all"]["eligible_records"], 3)
        self.assertTrue(summary["small_sample_warnings"])

    def test_resume_submit_does_not_duplicate_paid_batches(self):
        manifest = self.prepare()
        calls = []
        def create(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(id=f"batch_{len(calls)}")
        api = SimpleNamespace(files=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(id="file_uploaded")),
                              batches=SimpleNamespace(create=create))
        with patch.object(judge, "client", return_value=api):
            judge.submit(argparse.Namespace(run=self.run_dir))
            judge.submit(argparse.Namespace(run=self.run_dir))
        self.assertEqual(len(calls), len(manifest["chunks"]))
        self.assertTrue(all(c["completion_window"] == "24h" for c in calls))

    def test_retry_prepares_only_failed_tasks_and_never_submits(self):
        manifest = self.prepare()
        failed = manifest["tasks"][0]["custom_id"]
        for c in manifest["chunks"]:
            c.update(batch_id="batch_completed", status="completed")
        judge.save(self.run_dir / "manifest.json", manifest)
        judge.jsonl(self.run_dir / "judgments.jsonl", [
            {"custom_id": t["custom_id"], "status": "invalid" if t["custom_id"] == failed else "valid"}
            for t in manifest["tasks"]])
        with patch.object(judge, "client", side_effect=AssertionError("Retry must not call API")):
            judge.retry(argparse.Namespace(run=self.run_dir))
        new_manifest = judge.load_manifest(self.run_dir)
        new_chunks = new_manifest["chunks"][len(manifest["chunks"]):]
        self.assertEqual(sum(c["request_count"] for c in new_chunks), 1)
        self.assertEqual(judge.lines(self.run_dir / new_chunks[0]["path"])[0]["custom_id"], failed)

    def test_policy_is_frozen_and_large_development_is_blocked(self):
        manifest = self.prepare()
        manifest["policy"]["thresholds"]["recall"] = .1
        judge.save(self.run_dir / "manifest.json", manifest)
        with self.assertRaisesRegex(ValueError, "protocol"):
            judge.load_manifest(self.run_dir)
        source = judge.read(self.source)
        source["results"] = [{**source["results"][0], "example_id": str(i)} for i in range(26)]
        judge.save(self.source, source)
        self.args.run = self.root / "large"
        with self.assertRaisesRegex(ValueError, "limited to 25"):
            judge.prepare(self.args)
        self.assertFalse(self.args.run.exists())

    def test_holdout_excludes_entire_charts_and_requires_development(self):
        self.args.chart_limit = 1
        self.prepare()
        development = self.run_dir
        self.args.run = self.root / "validation"
        self.args.stage = "validation"
        with self.assertRaisesRegex(ValueError, "exclude-run"):
            judge.prepare(self.args)
        self.args.exclude_run = [development]
        judge.prepare(self.args)
        before = judge.lines(development / "records.jsonl")
        after = judge.lines(self.args.run / "records.jsonl")
        self.assertTrue({r["chart_id"] for r in before}.isdisjoint(r["chart_id"] for r in after))
        self.assertEqual(len(after), 2)
        self.assertEqual(judge.load_manifest(self.args.run)["stage"], "validation")

    def test_evaluation_requires_a_passing_validation(self):
        self.args.stage = "evaluation"
        with self.assertRaisesRegex(ValueError, "validated-run"):
            judge.prepare(self.args)

    def test_validate_failure_writes_reasons_and_exits_nonzero(self):
        self.prepare()
        judge.jsonl(self.run_dir / "judgments.jsonl", [])
        human_path = self.root / "unlabeled.jsonl"
        judge.jsonl(human_path, [])
        with self.assertRaises(SystemExit) as failure:
            judge.validate(argparse.Namespace(run=self.run_dir, human_labels=human_path, bootstrap=100, seed=42))
        self.assertEqual(failure.exception.code, 2)
        self.assertEqual(judge.read(self.run_dir / "validation.json")["status"], "not_validated")

    def test_matched_charts_cannot_have_different_questions(self):
        other = judge.read(self.source)
        other["model"] = "another-generator"
        other["results"][0]["question"] = "A different question"
        other_path = self.root / "other.json"
        judge.save(other_path, other)
        self.args.inputs.append(other_path)
        with self.assertRaisesRegex(ValueError, "Question mismatch"):
            judge.prepare(self.args)
        self.assertFalse(self.run_dir.exists())

    def test_missing_final_answer_is_a_failure_even_without_judge_output(self):
        source = judge.read(self.source)
        source["results"][0]["model_answer"] = ""
        source["results"][0]["generation_truncated"] = True
        judge.save(self.source, source)
        manifest = self.prepare()
        judge.jsonl(self.run_dir / "judgments.jsonl", [])
        rows, _ = judge.joined(self.run_dir, manifest)
        self.assertFalse(rows[0]["answer_correct"])
        self.assertEqual(rows[0]["answer_verdict"], "missing")
        self.assertIsNone(rows[0]["final_explanation_metrics"]["unsupported"])
        self.assertEqual(judge.estimate(rows, "answer_accuracy", 100, 42)["denominator"], 1)

    def test_strategy_check_reuses_answer_request_and_keeps_grounding_blind(self):
        source = judge.read(self.source)
        source["strategy_prompts"] = {s: "Finish with a line beginning 'Final answer:'." for s in ["direct", "structured"]}
        source["results"][0]["system_prompt"] = "Actual per-response prompt: write Final answer:"
        judge.save(self.source, source)
        manifest = self.prepare()
        requests = [r for c in manifest["chunks"] for r in judge.lines(self.run_dir / c["path"])]
        answers = [r for r in requests if "-answer-" in r["custom_id"]]
        self.assertEqual(len(requests), 8)
        self.assertEqual(len(answers), 4)
        self.assertNotIn("instruction_following", judge.SCHEMAS)
        for r in requests:
            data = json.loads(r["body"]["input"][0]["content"][0]["text"])
            if "-grounding-" in r["custom_id"]:
                self.assertNotIn("generation_system_prompt", data)
            if "-answer-" in r["custom_id"]:
                self.assertIn("generation_system_prompt", data)
                self.assertIn("reference_answer", data)
                self.assertNotIn("generator-secret", json.dumps(r["body"]))
                self.assertEqual(len(r["body"]["input"][0]["content"]), 1)
                self.assertTrue(r["body"]["text"]["format"]["strict"])
                self.assertEqual(r["body"]["instructions"], judge.ANSWER_PROMPT)
        self.assertTrue(any("Actual per-response prompt" in r["body"]["input"][0]["content"][0]["text"] for r in answers))

    def test_strategy_fields_are_boolean_or_null_and_require_a_reason(self):
        record = {"generation_system_prompt": "Write Final answer:", "final_explanation": "Final answer: 1", "returned_reasoning": ""}
        for value in [True, False, None]:
            judge.validate_judgment("answer", answer(followed=value, reason="Observed strategy requirements."), record, judge.SCHEMAS)
        from jsonschema import ValidationError
        with self.assertRaises(ValidationError):
            judge.validate_judgment("answer", answer(followed="yes"), record, judge.SCHEMAS)
        with self.assertRaisesRegex(ValueError, "short reason"):
            judge.validate_judgment("answer", answer(followed=False, reason=""), record, judge.SCHEMAS)
        record["generation_system_prompt"] = ""
        with self.assertRaisesRegex(ValueError, "must be null"):
            judge.validate_judgment("answer", answer(followed=True), record, judge.SCHEMAS)
        judge.validate_judgment("answer", answer(), record, judge.SCHEMAS)

    def test_adherence_and_factual_correctness_remain_separate(self):
        source = judge.read(self.source)
        source["results"][0]["system_prompt"] = "Write Final answer:"
        judge.save(self.source, source)
        manifest = self.prepare()
        record = judge.lines(self.run_dir / "records.jsonl")[0]
        outcomes = [
            {"custom_id": record["response_id"] + "-answer-0", "status": "valid",
             "judgment": answer("incorrect", True, "Required answer format is present.")}]
        judge.jsonl(self.run_dir / "judgments.jsonl", outcomes)
        rows, _ = judge.joined(self.run_dir, manifest)
        metrics = judge.metric_values(rows[0])
        self.assertFalse(metrics["answer_accuracy"])
        self.assertTrue(metrics["strategy_following_rate"])
        self.assertIsNone(rows[0]["final_explanation_metrics"]["unsupported"])
        self.assertIsNone(rows[1]["strategy_followed"])
        self.assertIsNone(judge.metric_values(rows[1])["strategy_following_rate"])

    def test_corrected_trace_is_observed_but_not_retained_error(self):
        record = {"final_explanation": "1", "returned_reasoning": "Value is 2. Correction: value is 1."}
        judgment = ground()
        trace = field("Value is 2.", "contradicted")
        trace["claims"][0].update(resolution="explicitly_corrected", correction_quote="Correction: value is 1.")
        trace["claims"].append(field("value is 1.")["claims"][0])
        judgment["returned_reasoning"] = trace
        judge.validate_judgment("grounding", judgment, record, judge.SCHEMAS)
        metrics = judge.field_metrics(judgment, record, "returned_reasoning")
        self.assertTrue(metrics["observed_contradicted"])
        self.assertFalse(metrics["contradicted"])
        self.assertEqual(metrics["corrected_claim_count"], 1)
        self.assertEqual(metrics["claim_error_rate"], 0)
        trace["claims"][0]["correction_quote"] = "a correction only in another field"
        with self.assertRaisesRegex(ValueError, "same field"):
            judge.validate_judgment("grounding", judgment, record, judge.SCHEMAS)

    def test_verified_tables_apply_frozen_tolerance_without_trusting_judge_verdict(self):
        from openai_judge_protocol import validate_chart_metadata
        metadata = {"human_verified": True, "verified_table": {"provenance": "Manually checked source table",
                     "values": [{"id": "series_a", "value": 10, "unit": "count"}]}}
        validate_chart_metadata({"chart": metadata})
        record = {"final_explanation": "12", "returned_reasoning": "", "chart_metadata": metadata,
                  "numeric_tolerance": {"absolute": 1, "relative": 0}}
        judgment = ground()
        judgment["final_explanation"] = field("12")
        judgment["final_explanation"]["claims"][0].update(numeric_reference="series_a", numeric_value=12)
        judge.validate_judgment("grounding", judgment, record, judge.SCHEMAS)
        self.assertTrue(judge.field_metrics(judgment, record, "final_explanation")["contradicted"])
        record["numeric_tolerance"]["absolute"] = 2
        self.assertFalse(judge.field_metrics(judgment, record, "final_explanation")["contradicted"])
        metadata["human_verified"] = False
        with self.assertRaisesRegex(ValueError, "human_verified"):
            validate_chart_metadata({"chart": metadata})

    def test_validation_gate_rejects_low_coverage_and_inadequate_human_evidence(self):
        from openai_judge_protocol import DEFAULT_POLICY, validation_decision
        policy = copy.deepcopy(DEFAULT_POLICY)
        rows, labels = [], []
        for i in range(20):
            human = i % 2 == 0
            row = {"response_id": str(i), "chart_id": str(i),
                   "final_explanation_metrics": {"unsupported": human}, "answer_correct": human}
            rows.append(row)
            labels.extend({"response_id": str(i), "annotator": name,
                           "final_explanation_unsupported": human, "answer_correct": human} for name in ["a", "b", "adjudicated"])
        manifest = {"stage": "validation", "policy": policy}
        result = validation_decision(manifest, rows, labels, judge.agreement_ci, 100, 42)
        self.assertEqual(result["status"], "passed")
        rows[0]["final_explanation_metrics"]["unsupported"] = None
        rows[1]["final_explanation_metrics"]["unsupported"] = None
        result = validation_decision(manifest, rows, labels, judge.agreement_ci, 100, 42)
        self.assertEqual(result["status"], "not_validated")
        self.assertIn("insufficient_human_and_judge_coverage", result["reasons"])
        rows[0]["final_explanation_metrics"]["unsupported"] = True
        rows[1]["final_explanation_metrics"]["unsupported"] = False
        labels = [e for e in labels if e["annotator"] != "b"]
        self.assertIn("insufficient_independent_human_overlap",
                      validation_decision(manifest, rows, labels, judge.agreement_ci, 100, 42)["reasons"])

    def test_verification_drafts_are_blinded_and_measured_separately(self):
        source = judge.read(self.source)
        source["results"][0].update(draft_model_answer="Final answer: 2", draft_model_reasoning="2")
        judge.save(self.source, source)
        manifest = self.prepare()
        self.assertEqual(len(manifest["tasks"]), 10)
        requests = [r for c in manifest["chunks"] for r in judge.lines(self.run_dir / c["path"])]
        draft = next(r for r in requests if "-draft_grounding-" in r["custom_id"])
        data = json.loads(draft["body"]["input"][0]["content"][0]["text"])
        self.assertEqual(data["final_explanation"], "Final answer: 2")
        self.assertNotIn("reference_answer", data)
        self.assertNotIn("strategy", data)
        self.assertNotIn("Final answer: 1", json.dumps(data))

    def test_full_validation_promotion_and_protocol_drift(self):
        source = judge.read(self.source)
        source["results"] = []
        for c in range(14):
            (self.root / f"image{c}.png").write_bytes(f"chart-{c}".encode())
            for strategy in ["direct", "structured"]:
                source["results"].append({"example_id": str(c), "question": f"Question {c}",
                    "correct_answer": "1", "image_path": f"image{c}.png", "prompt_strategy": strategy,
                    "model_answer": f"Final answer: {1 if c % 2 == 0 else 2}",
                    "model_reasoning": "", "generation_truncated": False})
        judge.save(self.source, source)
        self.args.chart_limit = 1
        self.prepare()
        development = self.run_dir
        self.args.run = self.root / "validation"
        self.args.stage = "validation"
        self.args.exclude_run = [development]
        self.args.chart_limit = 10
        judge.prepare(self.args)
        validation_run = self.args.run
        manifest = judge.load_manifest(validation_run)
        records = judge.lines(validation_run / "records.jsonl")
        outcomes, humans = [], []
        for r in records:
            error = int(r["example_id"]) % 2 == 0
            grounding = ground("contradicted" if error else "supported")
            grounding["final_explanation"]["claims"][0]["quote"] = "1" if error else "2"
            outcomes.extend([
                {"custom_id": r["response_id"] + "-answer-0", "status": "valid", "judgment": {
                    **answer("correct" if error else "incorrect"), "extracted_answer": "1" if error else "2"}},
                {"custom_id": r["response_id"] + "-grounding-0", "status": "valid",
                 "judgment": grounding}])
            humans.extend({"response_id": r["response_id"], "annotator": a, "answer_correct": error,
                "final_explanation_unsupported": error} for a in ["a", "b", "adjudicated"])
        judge.jsonl(validation_run / "judgments.jsonl", outcomes)
        human_path = self.root / "human_labels.jsonl"
        judge.jsonl(human_path, humans)
        judge.validate(argparse.Namespace(run=validation_run, human_labels=human_path, bootstrap=100, seed=42))
        self.assertEqual(judge.read(validation_run / "validation.json")["status"], "passed")
        self.args.stage = "evaluation"
        self.args.validated_run = validation_run
        self.args.human_labels = human_path
        self.args.chart_limit = None
        self.args.run = self.root / "evaluation"
        with patch.object(judge, "client", side_effect=AssertionError("Prepare must be offline")):
            judge.prepare(self.args)
        final = judge.lines(self.args.run / "records.jsonl")
        self.assertEqual(len(final), 6)
        self.assertTrue({r["chart_id"] for r in records}.isdisjoint(r["chart_id"] for r in final))
        self.assertEqual(judge.load_manifest(self.args.run)["validation_evidence"]["decision"]["status"], "passed")
        self.args.run = self.root / "changed-judge"
        self.args.model = "a-different-judge"
        with self.assertRaisesRegex(ValueError, "match the validated protocol"):
            judge.prepare(self.args)
        self.assertFalse(self.args.run.exists())


if __name__ == "__main__":
    unittest.main()

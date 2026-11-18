"""Offline regression checks; never contact OpenAI or submit paid work."""
import argparse
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
            "material": True, "evidence": "The bar is labeled 1."}]}


def ground(verdict="supported"):
    return {"chart_readability": "readable", "final_explanation": field(verdict=verdict),
            "returned_reasoning": {"applicable": False, "coverage_complete": True,
                                   "requires_review": False, "review_reason": "", "claims": []}}


class JudgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "experiment.json"
        (self.root / "image.png").write_bytes(b"local-image-fixture")
        records = [{"example_id": f"images/{c}.png", "question": f"Question {c}?",
                    "correct_answer": "1", "image_path": "image.png", "prompt_strategy": s,
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
            j = {"extracted_answer": "1", "verdict": "correct", "justification": "matches"} if task["kind"] == "answer" else ground("contradicted")
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
                judgment = ({"extracted_answer": "1", "verdict": "correct", "justification": "matches"}
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


if __name__ == "__main__":
    unittest.main()

"""Offline Gemini Batch tests. Network clients are always mocked."""
import argparse
import contextlib
import copy
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from google.genai import types
from google.genai.errors import ClientError
import google_ai_studio_judge as google
import judge_common as shared
import judge_schema
import openai_batch_judge as openai
from test_openai_batch_judge import answer, ground


def response(judgment, finish="STOP"):
    return {"candidates": [{"finishReason": finish, "content": {"parts": [
        {"text": "private thought", "thought": True}, {"text": json.dumps(judgment)}]}}],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 15,
                          "thoughtsTokenCount": 3, "totalTokenCount": 28, "cachedContentTokenCount": 2},
        "modelVersion": "gemini-test-snapshot"}


class GoogleBatchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / "experiment.json"
        for i in range(2):
            (self.root / f"chart{i}.png").write_bytes(f"image-{i}".encode())
        shared.save(self.source, {"dataset": "test", "split": "validation", "model": "secret-generator",
            "results": [{"example_id": f"chart{i}", "question": "How many?", "correct_answer": "1",
                         "model_answer": "Final answer: 1", "model_reasoning": "",
                         "image_path": f"chart{i}.png", "generation_truncated": False,
                         "prompt_strategy": strategy} for i in range(2) for strategy in ["direct", "structured"]]})
        self.args = argparse.Namespace(run=self.root / "run", inputs=[self.source], model="gemini-test",
            effort="default", seed=42, repeat_fraction=0, max_shard_mb=1,
            answer_tokens=2048, grounding_tokens=12000, chart_limit=None)
        self.command = argparse.Namespace(run=self.args.run)
        self.jobs = {}
        self.outputs = {}
        def upload(**kwargs):
            return SimpleNamespace(name=f"files/input-{len(self.jobs) + 1}")
        def create(**kwargs):
            number = len(self.jobs) + 1
            batch = types.BatchJob(name=f"batches/job-{number}", model=kwargs["model"],
                state=types.JobState.JOB_STATE_PENDING, src={"file_name": kwargs["src"]},
                dest={"file_name": f"files/output-{number}"})
            self.jobs[batch.name] = batch
            return batch
        self.api = SimpleNamespace(files=SimpleNamespace(upload=Mock(side_effect=upload),
            download=Mock(side_effect=lambda *, file: self.outputs[file])),
            batches=SimpleNamespace(create=Mock(side_effect=create), get=Mock(side_effect=lambda *, name: self.jobs[name])))
        client_patch = patch.object(google, "client", return_value=self.api)
        client_patch.start()
        self.addCleanup(client_patch.stop)

    def prepare(self):
        google.prepare(self.args)
        return shared.load_manifest(self.args.run)

    def complete(self, error_key=None, finish="STOP"):
        manifest = shared.load_manifest(self.args.run)
        tasks = {t["custom_id"]: t for t in manifest["tasks"]}
        for chunk in manifest["chunks"]:
            if not chunk.get("batch_id"):
                continue
            batch = self.jobs[chunk["batch_id"]]
            batch.state = types.JobState.JOB_STATE_SUCCEEDED
            items = []
            for item in reversed(shared.lines(self.args.run / chunk["path"])):
                task_id = item["key"]
                if task_id == error_key:
                    items.append({"key": task_id, "error": {"code": 500, "message": "failed"}})
                else:
                    judgment = answer() if tasks[task_id]["kind"] == "answer" else ground()
                    items.append({"key": task_id, "response": response(judgment, finish), "status": None})
            self.outputs[batch.dest.file_name] = b"".join(shared.encode(i) + b"\n" for i in items)

    def test_native_batch_jsonl_and_shared_blinded_schemas(self):
        manifest = self.prepare()
        self.assertEqual(manifest["provider_config"]["api"], "batch_generate_content")
        for chunk in manifest["chunks"]:
            for item in shared.lines(self.args.run / chunk["path"]):
                self.assertEqual(set(item), {"key", "request"})
                body = item["request"]
                parts = body["contents"][0]["parts"]
                data = json.loads(parts[0]["text"])
                self.assertNotIn("secret-generator", json.dumps(body))
                kind = "answer" if "reference_answer" in data else "grounding"
                self.assertEqual(body["generationConfig"]["responseJsonSchema"], judge_schema.SCHEMAS[kind])
                self.assertEqual(len(parts), 1 if kind == "answer" else 2)
                if kind == "grounding":
                    self.assertNotIn("generation_system_prompt", data)
                    self.assertIn("inlineData", parts[1])

    def test_submit_returns_job_name_and_does_not_duplicate(self):
        manifest = self.prepare()
        google.submit(self.command)
        google.submit(self.command)
        self.assertEqual(self.api.batches.create.call_count, len(manifest["chunks"]))
        self.assertEqual(self.api.files.upload.call_count, len(manifest["chunks"]))
        call = self.api.batches.create.call_args.kwargs
        self.assertEqual(call["src"], "files/input-1")
        self.assertEqual(call["model"], "gemini-test")
        self.assertTrue(shared.load_manifest(self.args.run)["chunks"][0]["batch_id"].startswith("batches/"))

    def test_status_distinguishes_running_and_finished(self):
        self.prepare()
        google.submit(self.command)
        with contextlib.redirect_stdout(io.StringIO()) as running:
            google.status(self.command)
        self.assertIn("Not complete yet", running.getvalue())
        self.complete()
        with contextlib.redirect_stdout(io.StringIO()) as finished:
            google.status(self.command)
        self.assertIn("All batch jobs completed successfully", finished.getvalue())
        self.assertEqual(self.api.batches.create.call_count, 1)

    def test_collect_waits_for_results_then_validates_out_of_order_and_reuses_download(self):
        manifest = self.prepare()
        google.submit(self.command)
        google.collect(self.command)
        self.assertFalse(self.api.files.download.called)
        self.assertTrue(all(o["status"] == "missing" for o in shared.lines(self.args.run / "judgments.jsonl")))
        self.complete()
        google.collect(self.command)
        google.collect(self.command)
        self.assertEqual(self.api.files.download.call_count, 1)
        rows, outcomes = shared.joined(self.args.run, manifest)
        self.assertTrue(all(r["answer_correct"] for r in rows))
        self.assertTrue(all(o["status"] == "valid" for o in outcomes.values()))
        shared.report(argparse.Namespace(run=self.args.run, human_labels=None, bootstrap=100, seed=42,
            input_usd_per_million=1, output_usd_per_million=2, cached_input_usd_per_million=.1))
        summary = shared.read(self.args.run / "summary.json")
        self.assertEqual(summary["estimated_api_cost"]["pricing_mode"], "batch")
        self.assertEqual(summary["usage_including_retries_and_repeats"]["output_tokens"], 8 * 18)
        self.assertEqual(summary["usage_including_retries_and_repeats"]["reasoning_tokens"], 8 * 3)

    def test_retry_is_local_and_contains_only_failed_keys(self):
        manifest = self.prepare()
        failed = manifest["tasks"][0]["custom_id"]
        google.submit(self.command)
        self.complete(error_key=failed)
        google.collect(self.command)
        google.retry(self.command)
        retried = shared.load_manifest(self.args.run)
        self.assertEqual(len(retried["chunks"]), 2)
        retry_items = shared.lines(self.args.run / retried["chunks"][-1]["path"])
        self.assertEqual([i["key"] for i in retry_items], [failed])
        self.assertEqual(self.api.batches.create.call_count, 1)
        google.submit(self.command)
        # Initial raw results stay cached; only the retry file is downloaded next.
        self.complete()
        google.collect(self.command)
        self.assertTrue(all(o["status"] == "valid" for o in shared.lines(self.args.run / "judgments.jsonl")))

    def test_uncertain_creation_is_blocked_until_matching_job_attached(self):
        self.prepare()
        self.api.batches.create.side_effect = TimeoutError("unknown outcome")
        with self.assertRaises(TimeoutError):
            google.submit(self.command)
        with self.assertRaisesRegex(RuntimeError, "uncertain"):
            google.submit(self.command)
        self.assertEqual(self.api.batches.create.call_count, 1)
        self.jobs["batches/recovered"] = types.BatchJob(name="batches/recovered", model="models/gemini-test",
            state=types.JobState.JOB_STATE_PENDING, src={"file_name": "files/input-1"})
        google.attach(argparse.Namespace(run=self.args.run, chunk=0, batch_id="batches/recovered"))
        google.submit(self.command)
        self.assertEqual(self.api.batches.create.call_count, 1)

    def test_explicit_precondition_rejection_preserves_file_and_allows_later_submit(self):
        self.prepare()
        self.api.batches.create.side_effect = ClientError(400, {"error": {
            "code": 400, "status": "FAILED_PRECONDITION", "message": "Precondition check failed."}})
        with self.assertRaisesRegex(RuntimeError, "Check billing"):
            google.submit(self.command)
        chunk = shared.load_manifest(self.args.run)["chunks"][0]
        self.assertTrue(chunk["file_id"])
        self.assertFalse(chunk.get("submission_started"))
        self.assertFalse(chunk.get("batch_id"))
        self.assertEqual(chunk["submission_error"]["status"], "FAILED_PRECONDITION")
        self.assertEqual(self.api.batches.create.call_count, 1)
        self.api.batches.create.side_effect = lambda **kwargs: types.BatchJob(
            name="batches/accepted", model=kwargs["model"], state=types.JobState.JOB_STATE_PENDING)
        google.submit(self.command)
        chunk = shared.load_manifest(self.args.run)["chunks"][0]
        self.assertEqual(chunk["batch_id"], "batches/accepted")
        self.assertNotIn("submission_error", chunk)
        self.assertEqual(self.api.files.upload.call_count, 1)

    def test_incomplete_outputs_are_invalid_not_clean(self):
        self.prepare()
        google.submit(self.command)
        self.complete(finish="MAX_TOKENS")
        google.collect(self.command)
        self.assertTrue(all(o["status"] == "invalid" for o in shared.lines(self.args.run / "judgments.jsonl")))

    def test_failed_jobs_stay_unresolved_and_running_jobs_cannot_be_retried(self):
        self.prepare()
        google.submit(self.command)
        with self.assertRaisesRegex(ValueError, "terminal"):
            google.retry(self.command)
        batch = next(iter(self.jobs.values()))
        batch.state = types.JobState.JOB_STATE_FAILED
        batch.dest = None
        with contextlib.redirect_stdout(io.StringIO()) as output:
            google.collect(self.command)
        self.assertIn("finished with failed", output.getvalue())
        self.assertTrue(all(o["status"] == "missing" for o in shared.lines(self.args.run / "judgments.jsonl")))
        google.retry(self.command)
        retry_chunk = shared.load_manifest(self.args.run)["chunks"][-1]
        self.assertEqual(retry_chunk["request_count"], 8)

    def test_duplicate_keys_in_one_output_file_are_rejected(self):
        self.prepare()
        google.submit(self.command)
        self.complete()
        batch = next(iter(self.jobs.values()))
        body = self.outputs[batch.dest.file_name]
        self.outputs[batch.dest.file_name] += body.splitlines()[0] + b"\n"
        with self.assertRaisesRegex(ValueError, "Unexpected or duplicate"):
            google.collect(self.command)

    def test_unknown_or_duplicate_keys_are_rejected(self):
        self.prepare()
        google.submit(self.command)
        self.complete()
        batch = next(iter(self.jobs.values()))
        self.outputs[batch.dest.file_name] += shared.encode({"key": "unknown", "response": response(answer())}) + b"\n"
        with self.assertRaisesRegex(ValueError, "Unexpected or duplicate"):
            google.collect(self.command)

    def test_legacy_synchronous_and_wrong_provider_runs_are_rejected(self):
        manifest = self.prepare()
        legacy = copy.deepcopy(manifest)
        legacy["provider_config"]["api"] = "generateContent"
        legacy["protocol_sha256"] = shared.protocol_hash(legacy)
        shared.save(self.args.run / "manifest.json", legacy)
        with self.assertRaisesRegex(ValueError, "old synchronous"):
            google.submit(self.command)
        shared.save(self.args.run / "manifest.json", manifest)
        with patch.object(openai, "client", side_effect=AssertionError("Must not call OpenAI")):
            with self.assertRaisesRegex(ValueError, "another provider"):
                openai.submit(self.command)
        other = copy.copy(self.args)
        other.run = self.root / "openai"
        other.effort = "medium"
        openai.prepare(other)
        with self.assertRaisesRegex(ValueError, "not a Google"):
            google.submit(argparse.Namespace(run=other.run))


class GoogleClientTests(unittest.TestCase):
    def test_client_uses_ai_studio_key_and_disables_automatic_retries(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "unit-test-key"}, clear=True), patch(
                "google.genai.Client") as factory:
            google.client()
        kwargs = factory.call_args.kwargs
        self.assertFalse(kwargs["vertexai"])
        self.assertEqual(kwargs["api_key"], "unit-test-key")
        options = types.HttpOptions.model_validate(kwargs["http_options"])
        self.assertEqual(options.api_version, "v1beta")
        self.assertEqual(options.retry_options.attempts, 1)


if __name__ == "__main__":
    unittest.main()

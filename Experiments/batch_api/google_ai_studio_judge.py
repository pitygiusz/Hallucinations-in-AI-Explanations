"""Asynchronous Gemini Batch API judging with the shared evaluation schema.

prepare/report/validate are local. submit uploads JSONL and starts batch jobs;
status checks them; collect downloads and validates the completed results.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

import judge_common as shared
from judge_schema import ANSWER_PROMPT, GROUND_PROMPT, SCHEMAS, validate_judgment

TERMINAL = {"JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED"}


def request(task_id: str, kind: str, data: dict[str, Any], model: str,
            effort: str, max_tokens: int, image: str | None = None) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", model):
        raise ValueError("Supply a Gemini model ID, without a URL or models/ prefix.")
    config: dict[str, Any] = {"responseMimeType": "application/json",
                              "responseJsonSchema": SCHEMAS[kind], "maxOutputTokens": max_tokens}
    if effort != "default":
        config["thinkingConfig"] = {"thinkingLevel": effort.upper()}
    item = {"key": task_id, "request": {
        "systemInstruction": {"parts": [{"text": ANSWER_PROMPT if kind in {"answer", "draft_answer"} else GROUND_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": json.dumps(data, ensure_ascii=False)}]}],
        "generationConfig": config}}
    if image is not None:
        raise ValueError("Images must be attached through the frozen preparation workflow.")
    return item


def attach_image(item: dict[str, Any], data: bytes, mime: str) -> None:
    item["request"]["contents"][0]["parts"].append({"inlineData": {
        "mimeType": mime, "data": base64.b64encode(data).decode()}})
    if len(shared.encode(item["request"])) > 19_000_000:
        raise ValueError("Google request exceeds this runner's 19 MB limit; reduce the source image explicitly.")


def prepare(args: argparse.Namespace) -> None:
    shared.prepare(args, provider="google", request_builder=request, image_attacher=attach_image)


def load_manifest(run: Path) -> dict[str, Any]:
    manifest = shared.load_manifest(run)
    if manifest.get("provider") != "google":
        raise ValueError("This is not a Google AI Studio run; use the matching provider runner.")
    if manifest.get("provider_config", {}).get("api") != "batch_generate_content":
        raise ValueError("This run used the old synchronous Google runner. Prepare a new run directory for Batch API.")
    return manifest


def client() -> Any:
    shared.load_environment()
    key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise ValueError("Set GOOGLE_API_KEY or GEMINI_API_KEY in .env or the environment.")
    from google import genai
    # One attempt: never silently retry a potentially paid batch creation.
    return genai.Client(vertexai=False, api_key=key, http_options={
        "api_version": "v1beta", "retry_options": {"attempts": 1}})


def state_name(batch: Any) -> str:
    return getattr(batch.state, "name", str(batch.state).split(".")[-1])


def display_name(manifest: dict[str, Any], chunk: dict[str, Any]) -> str:
    return f"charxiv-{manifest['protocol_sha256'][:12]}-{chunk['sha256'][:12]}"


def submit(args: argparse.Namespace) -> None:
    from google.genai.errors import ClientError
    manifest = load_manifest(args.run)
    api = client()
    for chunk in manifest["chunks"]:
        if chunk.get("batch_id"):
            continue
        if chunk.get("submission_started"):
            raise RuntimeError("Batch creation had an uncertain outcome. Find the job in AI Studio and use attach; do not blindly resubmit.")
        path = args.run / chunk["path"]
        if shared.digest(path.read_bytes()) != chunk["sha256"]:
            raise ValueError("Prepared Google request file changed.")
        if not chunk.get("file_id"):
            uploaded = api.files.upload(file=str(path), config={"mime_type": "jsonl",
                                        "display_name": display_name(manifest, chunk)})
            if not uploaded.name:
                raise ValueError("Google upload returned no file name.")
            chunk["file_id"] = uploaded.name
            shared.save(args.run / "manifest.json", manifest)
        chunk["submission_started"] = shared.stamp()
        shared.save(args.run / "manifest.json", manifest)
        try:
            batch = api.batches.create(model=manifest["model"], src=chunk["file_id"],
                                       config={"display_name": display_name(manifest, chunk)})
        except ClientError as error:
            # Explicit rejections are different from timeouts and unknown outcomes.
            if error.code in {400, 401, 402, 403, 404, 422, 429}:
                chunk.pop("submission_started", None)
                status = str(getattr(error, "status", "UNKNOWN"))
                chunk["submission_error"] = {"code": error.code,
                    "status": status if re.fullmatch(r"[A-Z_]+", status) else "UNKNOWN",
                    "recorded_at": shared.stamp()}
                shared.save(args.run / "manifest.json", manifest)
                if error.code == 400 and status == "FAILED_PRECONDITION":
                    raise RuntimeError(
                        "Google rejected batch creation (400 FAILED_PRECONDITION). "
                        "Check billing, paid-tier/model access and Batch eligibility for the project owning the API key. "
                        "The uploaded file is preserved; after fixing the account prerequisites, rerun submit. "
                        "This rejected attempt does not require attach.") from error
            raise
        chunk.pop("submission_error", None)
        if not batch.name:
            raise RuntimeError("Google returned no batch name; creation outcome is uncertain.")
        chunk.update(batch_id=batch.name, status=state_name(batch), batch_snapshot=batch.model_dump(mode="json"))
        shared.save(args.run / "manifest.json", manifest)
        print(f"Submitted {chunk['path']}: {batch.name} ({chunk['status']})")
    print("Submission finished. Jobs run on Google's servers; this terminal can be closed. Run status later.")


def attach(args: argparse.Namespace) -> None:
    manifest = load_manifest(args.run)
    chunk = manifest["chunks"][args.chunk]
    batch = client().batches.get(name=args.batch_id)
    source = getattr(getattr(batch, "src", None), "file_name", None)
    model = (batch.model or "").removeprefix("models/")
    if chunk.get("batch_id") or not chunk.get("file_id") or source != chunk["file_id"] or model != manifest["model"]:
        raise ValueError("Batch source/model does not match this chunk, or chunk already has a batch.")
    chunk.update(batch_id=batch.name, status=state_name(batch), batch_snapshot=batch.model_dump(mode="json"))
    shared.save(args.run / "manifest.json", manifest)
    print(f"Attached {batch.name}")


def print_status(manifest: dict[str, Any], *, collected: bool = False) -> None:
    counts = Counter(c.get("status", "NOT_SUBMITTED") if c.get("batch_id") else "NOT_SUBMITTED"
                     for c in manifest["chunks"])
    print("Job states:", dict(counts))
    if counts and set(counts) == {"JOB_STATE_SUCCEEDED"}:
        print("All batch jobs completed successfully. " +
              ("Inspect judgment counts below, then run report." if collected else "Run collect, then report."))
    elif counts and set(counts) <= TERMINAL:
        print("Processing finished with failed/cancelled/expired jobs. Collect available results and inspect the manifest.")
    else:
        print("Not complete yet. Submit any remaining chunks and check status again later.")


def status(args: argparse.Namespace) -> None:
    manifest = load_manifest(args.run)
    api = client()
    for chunk in manifest["chunks"]:
        if not chunk.get("batch_id"):
            print(chunk["path"], "not submitted")
            continue
        batch = api.batches.get(name=chunk["batch_id"])
        chunk.update(status=state_name(batch), batch_snapshot=batch.model_dump(mode="json"))
        print(batch.name, chunk["status"])
    shared.save(args.run / "manifest.json", manifest)
    print_status(manifest)


def normalize_usage(body: dict[str, Any]) -> dict[str, Any]:
    usage = body.get("usageMetadata") or {}
    reasoning = usage.get("thoughtsTokenCount", 0)
    output = usage.get("candidatesTokenCount", 0) + reasoning
    return {"input_tokens": usage.get("promptTokenCount", 0), "output_tokens": output,
            "total_tokens": usage.get("totalTokenCount", usage.get("promptTokenCount", 0) + output),
            "input_tokens_details": {"cached_tokens": usage.get("cachedContentTokenCount", 0)},
            "output_tokens_details": {"reasoning_tokens": reasoning}}


def collect(args: argparse.Namespace) -> None:
    from jsonschema import ValidationError
    manifest = load_manifest(args.run)
    api = client()
    tasks = {t["custom_id"]: t for t in manifest["tasks"]}
    records = {r["response_id"]: r for r in shared.lines(args.run / "records.jsonl")}
    raw = args.run / "raw"
    raw.mkdir(exist_ok=True)
    outcomes, usage_rows = {}, []
    for chunk in manifest["chunks"]:
        if not chunk.get("batch_id"):
            continue
        batch = api.batches.get(name=chunk["batch_id"])
        chunk.update(status=state_name(batch), batch_snapshot=batch.model_dump(mode="json"))
        if chunk["status"] not in TERMINAL:
            print(batch.name, chunk["status"], "results not ready")
            continue
        filename = getattr(getattr(batch, "dest", None), "file_name", None)
        if not filename:
            print(batch.name, chunk["status"], "no result file")
            continue
        target = raw / (batch.name.replace("/", "_") + "-" + shared.digest(filename.encode())[:12] + ".jsonl")
        if not target.exists():
            content = api.files.download(file=filename)
            temporary = target.with_suffix(".tmp")
            temporary.write_bytes(content)
            temporary.replace(target)
        seen = set()
        for item in shared.lines(target):
            task_id = item.get("key")
            if task_id not in tasks or task_id in seen:
                raise ValueError("Unexpected or duplicate task key in Google batch output.")
            seen.add(task_id)
            body = item.get("response") or {}
            usage = normalize_usage(body)
            usage_rows.append({"custom_id": task_id, "batch_id": batch.name, "usage": usage,
                               "returned_model": body.get("modelVersion")})
            outcome: dict[str, Any] = {"custom_id": task_id, "status": "invalid", "batch_id": batch.name,
                                       "usage": usage, "returned_model": body.get("modelVersion")}
            try:
                if item.get("error") or (item.get("status") or {}).get("code") or body.get("error"):
                    raise ValueError("Google returned a per-request error; inspect the raw batch output.")
                candidates = body.get("candidates") or []
                if len(candidates) != 1 or candidates[0].get("finishReason") != "STOP":
                    raise ValueError("Google response was blocked, incomplete or has no single completed candidate.")
                if (body.get("promptFeedback") or {}).get("blockReason"):
                    raise ValueError("Google blocked the prompt.")
                parts = candidates[0].get("content", {}).get("parts", [])
                text = "".join(p["text"] for p in parts if "text" in p and not p.get("thought"))
                judgment = json.loads(text)
                task = tasks[task_id]
                validate_judgment(task["kind"], judgment, records[task["response_id"]], manifest["schemas"])
                outcome.update(status="valid", judgment=judgment)
            except (ValueError, TypeError, KeyError, ValidationError) as error:
                outcome["error"] = str(error)
            if outcomes.get(task_id, {}).get("status") != "valid":
                outcomes[task_id] = outcome
    for task_id in tasks:
        outcomes.setdefault(task_id, {"custom_id": task_id, "status": "missing"})
    shared.save(args.run / "manifest.json", manifest)
    shared.jsonl(args.run / "judgments.jsonl", list(outcomes.values()))
    shared.jsonl(args.run / "usage.jsonl", usage_rows)
    print_status(manifest, collected=True)
    print("Judgment counts:", dict(Counter(o["status"] for o in outcomes.values())))


def retry(args: argparse.Namespace) -> None:
    manifest = load_manifest(args.run)
    if any(not c.get("batch_id") or c.get("status") not in TERMINAL for c in manifest["chunks"]):
        raise ValueError("Collect all batches after they are terminal before preparing retries.")
    outcomes = {o["custom_id"]: o for o in shared.lines(args.run / "judgments.jsonl")}
    wanted = {t["custom_id"] for t in manifest["tasks"] if outcomes.get(t["custom_id"], {}).get("status") != "valid"}
    original = {}
    for chunk in manifest["chunks"]:
        for item in shared.lines(args.run / chunk["path"]):
            if item["key"] in wanted:
                original[item["key"]] = item
    manifest["chunks"].extend(shared.shards(args.run, list(original.values()),
        f"retry-{len(manifest['chunks'])}", manifest["max_shard_mb"]))
    shared.save(args.run / "manifest.json", manifest)
    print(f"Prepared {len(original)} retries locally. Run submit explicitly to send them.")


def main() -> None:
    args = shared.parse_args("google")
    if args.command in {"policy", "report", "validate"}:
        getattr(shared, args.command)(args)
    else:
        globals()[args.command](args)


if __name__ == "__main__":
    main()

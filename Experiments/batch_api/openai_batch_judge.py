"""Run OpenAI Batch judgments with the shared chart-evaluation schema.

prepare/report/validate are offline; submit sends paid Batch API requests.
"""
from __future__ import annotations
import argparse
import base64
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any
import judge_common as shared
from judge_common import (VERSION, SCHEMAS, ANSWER_PROMPT, GROUND_PROMPT, digest, save,
                          lines, jsonl, shards, stamp, validate_judgment)

TERMINAL = {"completed", "failed", "expired", "cancelled"}


def load_manifest(run: Path) -> dict[str, Any]:
    manifest = shared.load_manifest(run)
    if manifest.get("provider", "openai") != "openai":
        raise ValueError("This run belongs to another provider; use its runner.")
    return manifest


def attach_image(item: dict[str, Any], data: bytes, mime: str) -> None:
    item["body"]["input"][0]["content"].append({"type": "input_image",
        "image_url": f"data:{mime};base64," + base64.b64encode(data).decode(), "detail": "high"})


def prepare(args: argparse.Namespace) -> None:
    shared.prepare(args, provider="openai", request_builder=request, image_attacher=attach_image)


def request(task_id: str, kind: str, data: dict[str, Any], model: str,
            effort: str, max_tokens: int, image: str | None = None) -> dict[str, Any]:
    content: list[dict[str, Any]] = [{"type": "input_text", "text": json.dumps(data, ensure_ascii=False)}]
    if image:
        content.append({"type": "input_image", "image_url": image, "detail": "high"})
    return {"custom_id": task_id, "method": "POST", "url": "/v1/responses", "body": {
        "model": model, "instructions": ANSWER_PROMPT if kind in {"answer", "draft_answer"} else GROUND_PROMPT,
        "input": [{"role": "user", "content": content}], "store": False,
        "reasoning": {"effort": effort}, "max_output_tokens": max_tokens,
        "text": {"format": {"type": "json_schema", "name": f"charxiv_{kind}",
                            "strict": True, "schema": SCHEMAS[kind]}},
    }}


def client() -> Any:
    shared.load_environment()
    if not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("Set OPENAI_API_KEY in the environment (never in a tracked file).")
    from openai import OpenAI
    # No automatic retries of potentially paid batch creation.
    return OpenAI(max_retries=0)


def submit(args: argparse.Namespace) -> None:
    run = args.run
    manifest = load_manifest(run)
    api = client()
    for chunk in manifest["chunks"]:
        if chunk["batch_id"]:
            continue
        path = run / chunk["path"]
        if digest(path.read_bytes()) != chunk["sha256"]:
            raise ValueError(f"Request file changed: {path}")
        if not chunk["file_id"]:
            with path.open("rb") as stream:
                chunk["file_id"] = api.files.create(file=stream, purpose="batch").id
            save(run / "manifest.json", manifest)
        if chunk.get("submission_started"):
            raise RuntimeError("An earlier batch creation has an uncertain outcome. Check the API dashboard and use attach; do not blindly resubmit.")
        chunk["submission_started"] = stamp()
        save(run / "manifest.json", manifest)
        batch = api.batches.create(input_file_id=chunk["file_id"], endpoint="/v1/responses",
                                   completion_window="24h", metadata={"protocol": VERSION,
                                   "chunk_sha256": chunk["sha256"]})
        chunk["batch_id"] = batch.id
        save(run / "manifest.json", manifest)
        print(f"Submitted {chunk['path']}: {batch.id}")


def attach(args: argparse.Namespace) -> None:
    manifest = load_manifest(args.run)
    chunk = manifest["chunks"][args.chunk]
    batch = client().batches.retrieve(args.batch_id)
    if chunk["batch_id"] or batch.input_file_id != chunk["file_id"]:
        raise ValueError("Batch does not match this uploaded file, or chunk already has a batch.")
    chunk["batch_id"] = batch.id
    save(args.run / "manifest.json", manifest)


def status(args: argparse.Namespace) -> None:
    manifest = load_manifest(args.run)
    api = client()
    for chunk in manifest["chunks"]:
        if not chunk["batch_id"]:
            print(chunk["path"], "not submitted")
            continue
        batch = api.batches.retrieve(chunk["batch_id"])
        chunk["status"] = batch.status
        chunk["batch_snapshot"] = batch.model_dump(mode="json")
        print(batch.id, batch.status, batch.request_counts)
    save(args.run / "manifest.json", manifest)


def collect(args: argparse.Namespace) -> None:
    run = args.run
    manifest = load_manifest(run)
    records = {r["response_id"]: r for r in lines(run / "records.jsonl")}
    tasks = {t["custom_id"]: t for t in manifest["tasks"]}
    api = client()
    raw_dir = run / "raw"
    raw_dir.mkdir(exist_ok=True)
    outcomes, all_usage = {}, []
    for chunk in manifest["chunks"]:
        if not chunk["batch_id"]:
            continue
        batch = api.batches.retrieve(chunk["batch_id"])
        chunk["status"] = batch.status
        chunk["batch_snapshot"] = batch.model_dump(mode="json")
        for file_id in [batch.output_file_id, batch.error_file_id]:
            if not file_id:
                continue
            target = raw_dir / f"{batch.id}-{file_id}.jsonl"
            if not target.exists():
                api.files.content(file_id).write_to_file(target)
            for item in lines(target):
                task_id = item.get("custom_id")
                if task_id not in tasks:
                    raise ValueError(f"Unexpected custom_id: {task_id}")
                task = tasks[task_id]
                body = (item.get("response") or {}).get("body") or {}
                usage = body.get("usage") or {}
                all_usage.append({"custom_id": task_id, "batch_id": batch.id, "usage": usage,
                                  "returned_model": body.get("model")})
                outcome = {"custom_id": task_id, "status": "invalid", "batch_id": batch.id,
                           "usage": usage, "returned_model": body.get("model")}
                try:
                    if item.get("error") or (item.get("response") or {}).get("status_code") != 200:
                        raise ValueError(str(item.get("error") or body.get("error") or "HTTP error"))
                    if body.get("status") != "completed":
                        raise ValueError(f"Incomplete API response: {body.get('incomplete_details')}")
                    parts = [part for output in body.get("output", []) if output.get("type") == "message"
                             for part in output.get("content", [])]
                    if any(part.get("type") == "refusal" for part in parts):
                        raise ValueError("Judge refused.")
                    judgment = json.loads("".join(part["text"] for part in parts if part.get("type") == "output_text"))
                    validate_judgment(task["kind"], judgment, records[task["response_id"]], manifest["schemas"])
                    outcome.update(status="valid", judgment=judgment)
                except (ValueError, KeyError, TypeError) as error:
                    outcome["error"] = str(error)
                except Exception as error:
                    # jsonschema.ValidationError must become an explicit invalid judgment.
                    from jsonschema import ValidationError
                    if not isinstance(error, ValidationError):
                        raise
                    outcome["error"] = str(error)
                if outcomes.get(task_id, {}).get("status") != "valid":
                    outcomes[task_id] = outcome
    for task_id in tasks:
        outcomes.setdefault(task_id, {"custom_id": task_id, "status": "missing"})
    save(run / "manifest.json", manifest)
    jsonl(run / "judgments.jsonl", list(outcomes.values()))
    jsonl(run / "usage.jsonl", all_usage)
    print(dict(Counter(item["status"] for item in outcomes.values())))


def retry(args: argparse.Namespace) -> None:
    manifest = load_manifest(args.run)
    if any(not c.get("batch_id") or c.get("status") not in TERMINAL for c in manifest["chunks"]):
        raise ValueError("Collect all submitted batches after they are terminal before preparing retries.")
    outcomes = {x["custom_id"]: x for x in lines(args.run / "judgments.jsonl")}
    wanted = {t["custom_id"] for t in manifest["tasks"] if outcomes[t["custom_id"]]["status"] != "valid"}
    original = {}
    for chunk in manifest["chunks"]:
        for item in lines(args.run / chunk["path"]):
            if item["custom_id"] in wanted:
                original[item["custom_id"]] = item
    chunks = shards(args.run, list(original.values()), f"retry-{len(manifest['chunks'])}", manifest["max_shard_mb"])
    manifest["chunks"].extend(chunks)
    save(args.run / "manifest.json", manifest)
    print(f"Prepared {len(original)} retries. Run submit explicitly to send them.")


def main() -> None:
    args = shared.parse_args("openai")
    if args.command in {"policy", "report", "validate"}:
        getattr(shared, args.command)(args)
    else:
        globals()[args.command](args)


if __name__ == "__main__":
    main()

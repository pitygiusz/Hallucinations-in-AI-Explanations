"""Provider-independent preparation, human validation, and reporting."""
from __future__ import annotations
import argparse
import copy
import csv
import hashlib
import importlib.metadata
import itertools
import json
import mimetypes
import os
import platform
import random
import shutil
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from judge_policy import (CHART_TYPES, DEFAULT_POLICY, numerical_checks,
                          validate_chart_metadata, validate_policy, validation_decision)
from judge_schema import (VERSION, ANSWER_PROMPT, GROUND_PROMPT, CATEGORIES, FIELDS,
                          SCHEMAS, validate_judgment)

ROOT = Path(__file__).resolve().parents[2]


def load_environment() -> None:
    """Load the repository's local configuration without replacing shell values."""
    path = ROOT / ".env"
    if path.is_file():
        from dotenv import load_dotenv
        load_dotenv(path, override=False, interpolate=False)


def protocol_hash(manifest: dict[str, Any]) -> str:
    keys = ["version", "model", "effort", "prompts", "schemas", "answer_max_output_tokens", "grounding_max_output_tokens"]
    if manifest["version"] in {"charxiv-judge-v2", "charxiv-judge-v3", "charxiv-judge-v4", "charxiv-judge-v5", VERSION}:
        keys += ["policy", "stage", "excluded_chart_ids", "excluded_image_sha256", "validation_evidence", "initial_requests", "tasks"]
    if manifest["version"] == "charxiv-judge-v3":
        keys += ["instruction_max_output_tokens"]
    if manifest["version"] in {VERSION, "charxiv-judge-v5"}:
        keys += ["provider", "provider_config"]
    return digest(encode({key: manifest[key] for key in keys}))


def judging_hash(manifest: dict[str, Any]) -> str:
    """Scientific judge identity, excluding run-specific chart/task assignments."""
    keys = ["version", "model", "effort", "prompts", "schemas", "answer_max_output_tokens", "grounding_max_output_tokens", "policy"]
    if manifest["version"] == "charxiv-judge-v3":
        keys += ["instruction_max_output_tokens"]
    if manifest["version"] in {VERSION, "charxiv-judge-v5"}:
        keys += ["provider", "provider_config"]
    return digest(encode({key: manifest[key] for key in keys}))


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def encode(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True).encode()


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(encode(value) + b"\n" for value in values))


def lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def shards(run: Path, requests: Iterable[dict[str, Any]], prefix: str, max_mb: float) -> list[dict[str, Any]]:
    chunks, buffer, size = [], [], 0
    def flush() -> None:
        nonlocal buffer, size
        if not buffer:
            return
        name = f"{prefix}-{len(chunks):04d}.jsonl"
        path = run / "requests" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"".join(buffer))
        chunks.append({"path": str(path.relative_to(run)), "sha256": digest(path.read_bytes()),
                       "request_count": len(buffer), "file_id": None, "batch_id": None})
        buffer, size = [], 0
    for item in requests:
        line = encode(item) + b"\n"
        if len(line) > max_mb * 1_000_000:
            raise ValueError("A single request exceeds the shard size limit.")
        if size + len(line) > max_mb * 1_000_000 or len(buffer) >= 49_000:
            flush()
        buffer.append(line)
        size += len(line)
    flush()
    return chunks


def materialize(requests: list[dict[str, Any]], attach_image: Any) -> Iterable[dict[str, Any]]:
    """Load and encode one chart at a time using the provider's envelope."""
    for original in requests:
        item = copy.deepcopy({k: v for k, v in original.items() if k != "_image"})
        if "_image" in original:
            path, expected_hash, mime = original["_image"]
            data = Path(path).read_bytes()
            if digest(data) != expected_hash:
                raise ValueError(f"Image changed during preparation: {path}")
            attach_image(item, data, mime)
        yield item



def prepare(args: argparse.Namespace, *, provider: str, request_builder: Any, image_attacher: Any) -> None:
    run = args.run.resolve()
    if run.exists():
        raise FileExistsError(f"Use a new run directory: {run}")
    stage = getattr(args, "stage", "development")
    policy_path = getattr(args, "policy", None)
    policy = read(policy_path) if policy_path else copy.deepcopy(DEFAULT_POLICY)
    validate_policy(policy)
    metadata_path = getattr(args, "chart_metadata", None)
    metadata = validate_chart_metadata(read(metadata_path)) if metadata_path else {}
    excluded: set[str] = set()
    excluded_images: set[str] = set()
    excluded_runs = getattr(args, "exclude_run", [])
    for previous in excluded_runs:
        old = load_manifest(previous)
        excluded.update(old.get("excluded_chart_ids", []))
        excluded.update(r["chart_id"] for r in lines(previous / "records.jsonl"))
        excluded_images.update(old.get("excluded_image_sha256", []))
        excluded_images.update(r["image_sha256"] for r in lines(previous / "records.jsonl"))
    evidence = None
    validation_manifest = None
    if stage == "validation" and not excluded_runs:
        raise ValueError("Held-out validation needs --exclude-run pointing to development charts.")
    if stage == "evaluation":
        validation_run = getattr(args, "validated_run", None)
        human_path = getattr(args, "human_labels", None)
        if validation_run is None or human_path is None:
            raise ValueError("Evaluation requires --validated-run and --human-labels; otherwise use development or human annotation.")
        validation_manifest = load_manifest(validation_run)
        validation_rows, _ = joined(validation_run, validation_manifest)
        # Validate every supplied human label before testing the primary gate.
        human_agreement(human_path, validation_rows, 2000, args.seed)
        decision = validation_decision(validation_manifest, validation_rows, human_entries(human_path, validation_rows), agreement_ci, 2000, args.seed)
        if decision["status"] != "passed":
            raise ValueError(f"Judge has not passed held-out validation: {decision['reasons']}. {decision['fallback']}")
        excluded.update(validation_manifest.get("excluded_chart_ids", []))
        excluded.update(r["chart_id"] for r in validation_rows)
        excluded_images.update(validation_manifest.get("excluded_image_sha256", []))
        excluded_images.update(r["image_sha256"] for r in validation_rows)
        evidence = {"run": str(validation_run.resolve()), "protocol_sha256": validation_manifest["protocol_sha256"],
                    "judgments_sha256": digest((validation_run / "judgments.jsonl").read_bytes()),
                    "human_labels_sha256": digest(human_path.read_bytes()), "decision": decision}
    records, tasks, requests, seen = [], [], [], set()
    included_charts: set[str] = set()
    sources = []
    for source in args.inputs:
        source = source.resolve()
        document = read(source)
        sources.append({"path": str(source), "sha256": digest(source.read_bytes()),
                        "dataset_revision": document.get("dataset_revision"),
                        "generation": document.get("generation"),
                        "max_new_tokens": document.get("max_new_tokens")})
        for index, result in enumerate(document["results"]):
            chart_key = [document["dataset"], document["split"], result["example_id"]]
            chart_id = digest(encode(chart_key))[:24]
            if chart_id in excluded:
                continue
            if args.chart_limit and chart_id not in included_charts and len(included_charts) >= args.chart_limit:
                continue
            model = result.get("model", document.get("model", "unknown"))
            strategy = result.get("prompt_strategy", "baseline")
            identity = (chart_id, model, strategy)
            if identity in seen:
                raise ValueError(f"Duplicate model/strategy/chart: {identity}. Supply each experiment once.")
            seen.add(identity)
            record_id = "r" + digest(encode([sources[-1]["sha256"], index]))[:24]
            image_path = Path(result["image_path"])
            if not image_path.is_absolute():
                image_path = source.parent / image_path
            image_bytes = image_path.read_bytes()
            image_hash = digest(image_bytes)
            if image_hash in excluded_images:
                continue
            included_charts.add(chart_id)
            if result.get("image_sha256") and image_hash != result["image_sha256"]:
                raise ValueError(f"Image hash mismatch: {image_path}")
            mime = mimetypes.guess_type(image_path.name)[0]
            if mime not in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
                raise ValueError(f"Unsupported image MIME type: {mime}")
            texts = {"final_explanation": str(result.get("model_answer") or ""),
                     "returned_reasoning": str(result.get("model_reasoning") or "")}
            generation_prompt = result.get("system_prompt") or (document.get("strategy_prompts") or {}).get(strategy) or document.get("system_prompt")
            if generation_prompt is not None and not isinstance(generation_prompt, str):
                raise ValueError("Saved generation system prompts must be strings.")
            # A serialized LM Studio envelope is not a candidate answer.
            if texts["final_explanation"].lstrip().startswith("{"):
                try:
                    envelope = json.loads(texts["final_explanation"])
                except ValueError:
                    envelope = None
                if isinstance(envelope, dict) and "output" in envelope:
                    raise ValueError(f"{source}: record {index} contains an API envelope as model_answer; repair extraction first.")
            records.append({"response_id": record_id, "chart_id": chart_id, "model": model,
                            "strategy": strategy, "source": str(source), "source_record_index": index,
                            "example_id": result["example_id"], "dataset_index": result.get("dataset_index"),
                            "question": result["question"], "correct_answer": result["correct_answer"],
                            "image_sha256": image_hash, "image_path": str(image_path.resolve()),
                            "chart_metadata": metadata.get(chart_id, metadata.get(str(result["example_id"]), {})),
                            "numeric_tolerance": policy["numeric_tolerance"],
                            "generation_system_prompt": generation_prompt or "",
                            "draft_generation_system_prompt": result.get("draft_system_prompt") or document.get("verification_draft_prompt") or "",
                            "generation_truncated": result.get("generation_truncated"),
                            "answer_missing": result.get("answer_missing", not bool(texts["final_explanation"].strip())),
                            "generation_config": {"model_revision": document.get("model_revision"),
                                "dataset_revision": document.get("dataset_revision"),
                                "max_new_tokens": document.get("max_new_tokens", (document.get("generation") or {}).get("max_new_tokens")),
                                "precision": document.get("dtype", document.get("precision"))},
                            "draft_final_explanation": str(result.get("draft_model_answer") or ""),
                            "draft_returned_reasoning": str(result.get("draft_model_reasoning") or ""),
                            "parse_method": result.get("parse_method"),
                            "generator_usage": {key: result.get(key) for key in [
                                "input_tokens", "generated_tokens", "generation_seconds", "elapsed_seconds", "request_count"]}, **texts})
            kinds = ["answer", "grounding"]
            if "draft_model_answer" in result or "draft_model_reasoning" in result:
                kinds += ["draft_answer", "draft_grounding"]
            for kind in kinds:
                task_texts = ({f: records[-1]["draft_" + f] for f in FIELDS}
                              if kind.startswith("draft_") else texts)
                count = 2 if kind == "grounding" and random.Random(record_id + str(args.seed)).random() < args.repeat_fraction else 1
                for repeat in range(count):
                    task_id = f"{record_id}-{kind}-{repeat}"
                    if kind in {"answer", "draft_answer"}:
                        data = {"question": result["question"], "reference_answer": result["correct_answer"],
                                "candidate_text": task_texts["final_explanation"],
                                "generation_system_prompt": records[-1]["draft_generation_system_prompt"]
                                    if kind == "draft_answer" else records[-1]["generation_system_prompt"]}
                        image = None
                    else:
                        data = {"question": result["question"], **task_texts,
                                "numeric_tolerance": policy["numeric_tolerance"]}
                        chart_metadata = records[-1]["chart_metadata"]
                        if chart_metadata.get("verified_table"):
                            data["verified_source_table"] = chart_metadata["verified_table"]
                        image = None
                    item = request_builder(task_id, kind, data, args.model, args.effort,
                                   args.answer_tokens if kind in {"answer", "draft_answer"} else args.grounding_tokens, image)
                    if kind in {"grounding", "draft_grounding"}:
                        item["_image"] = (str(image_path), image_hash, mime)
                    requests.append(item)
                    tasks.append({"custom_id": task_id, "response_id": record_id, "kind": kind, "repeat": repeat})
    if not records:
        raise ValueError("No responses found.")
    if stage == "development" and len(included_charts) > 25:
        raise ValueError("Development is limited to 25 charts. Use --chart-limit 25, validate the judge, then --stage evaluation.")
    chart_hashes: dict[str, str] = {}
    chart_questions: dict[str, str] = {}
    for record in records:
        if record["chart_id"] in chart_hashes and chart_hashes[record["chart_id"]] != record["image_sha256"]:
            raise ValueError("The same chart ID has different image bytes across input experiments.")
        chart_hashes[record["chart_id"]] = record["image_sha256"]
        if record["chart_id"] in chart_questions and chart_questions[record["chart_id"]] != record["question"]:
            raise ValueError("Question mismatch for the same chart: matched comparisons require the same chart-question pair.")
        chart_questions[record["chart_id"]] = record["question"]
    random.Random(args.seed).shuffle(requests)
    manifest = {"version": VERSION, "created_at": stamp(), "model": args.model, "provider": provider, "provider_config": {"api": "responses_batch" if provider == "openai" else "batch_generate_content"},
                "stage": stage, "policy": policy, "excluded_chart_ids": sorted(excluded),
                "excluded_image_sha256": sorted(excluded_images),
                "validation_evidence": evidence,
                "python_version": platform.python_version(),
                "package_versions": {p: importlib.metadata.version(p) for p in (["openai"] if provider == "openai" else ["google-genai"]) + ["numpy", "jsonschema"]},
                "effort": args.effort, "sources": sources, "seed": args.seed,
                "repeat_fraction": args.repeat_fraction, "max_shard_mb": args.max_shard_mb,
                "chart_limit": args.chart_limit,
                "answer_max_output_tokens": args.answer_tokens,
                "grounding_max_output_tokens": args.grounding_tokens,
                "prompts": {"answer": ANSWER_PROMPT, "grounding": GROUND_PROMPT},
                "schemas": SCHEMAS, "tasks": tasks}
    if validation_manifest and judging_hash(manifest) != judging_hash(validation_manifest):
        raise ValueError("Evaluation judge, prompts, schemas, budgets and policy must match the validated protocol exactly.")
    run.mkdir(parents=True)
    jsonl(run / "records.jsonl", records)
    manifest["chunks"] = shards(run, materialize(requests, image_attacher), "initial", args.max_shard_mb)
    manifest["initial_requests"] = [{k: c[k] for k in ["path", "sha256", "request_count"]} for c in manifest["chunks"]]
    manifest["records_sha256"] = digest((run / "records.jsonl").read_bytes())
    manifest["protocol_sha256"] = protocol_hash(manifest)
    save(run / "manifest.json", manifest)
    template = [{"response_id": r["response_id"], "annotator": "REPLACE_ME",
                 "answer_correct": None,
                 "strategy_followed": None,
                 "claim_annotations": None,
                 **{f"{f}_{m}": None for f in FIELDS for m in ["contradicted", "unsupported"]}}
                for r in records]
    jsonl(run / "human_labels_template.jsonl", template)
    for annotator in ["annotator_1", "annotator_2", "adjudicated"]:
        jsonl(run / f"human_{annotator}_template.jsonl", [{**r, "annotator": annotator} for r in template])
    packets = list(records)
    random.Random(args.seed).shuffle(packets)
    human_images = {}
    for r in packets:
        if r["chart_id"] not in human_images:
            original = Path(r["image_path"])
            relative = Path("human_images") / (r["chart_id"] + original.suffix.lower())
            (run / relative).parent.mkdir(exist_ok=True)
            shutil.copyfile(original, run / relative)
            human_images[r["chart_id"]] = relative.as_posix()
    jsonl(run / "human_answer_packets.jsonl", [{"response_id": r["response_id"], "question": r["question"],
        "reference_answer": r["correct_answer"], "candidate_text": r["final_explanation"],
        "generation_system_prompt": r["generation_system_prompt"]} for r in packets])
    jsonl(run / "human_grounding_packets.jsonl", [{"response_id": r["response_id"], "question": r["question"],
        "image_path": human_images[r["chart_id"]], **{f: r[f] for f in FIELDS}, "numeric_tolerance": r["numeric_tolerance"],
        "verified_source_table": r["chart_metadata"].get("verified_table")} for r in packets])
    save(run / "annotation_dataset.json", {
        "status": "TO_COLLECT", "stage": stage, "responses": len(records), "charts": len(chart_hashes),
        "annotation_unit": "Distinct factual claim; response labels derived separately per text field.",
        "class_balance": "Unknown until independent annotation; never assume balanced classes.",
        "overlap": "Two independent annotators per response, followed by a separate adjudicated label.",
        "assigned_annotators": None, "annotation_deadline": None, "annotation_release_license": None,
        "source_rights": "Retain source provenance and verify chart redistribution rights separately.",
        "policy": policy, "codebook": "judge_workflow.md", "source_hashes": sources})
    print(f"Prepared {len(records)} responses / {len(chart_hashes)} charts / {len(tasks)} requests in {run}")
    print("No requests submitted. Inspect manifest.json and requests/ before submit.")


def load_manifest(run: Path) -> dict[str, Any]:
    manifest = read(run / "manifest.json")
    if digest((run / "records.jsonl").read_bytes()) != manifest["records_sha256"]:
        raise ValueError("records.jsonl was modified after preparation.")
    fingerprint = protocol_hash(manifest)
    if fingerprint != manifest["protocol_sha256"]:
        raise ValueError("Judge protocol was modified after preparation; use a new run.")
    if manifest["version"] in {VERSION, "charxiv-judge-v5"}:
        for original in manifest["initial_requests"]:
            if digest((run / original["path"]).read_bytes()) != original["sha256"]:
                raise ValueError("A frozen request shard changed after preparation.")
    return manifest


def field_metrics(judgment: dict[str, Any] | None, record: dict[str, Any], field: str) -> dict[str, Any]:
    result: dict[str, Any] = {k: None for k in ["contradicted", "unsupported", "claim_error_rate",
        "claim_contradiction_rate", "observed_unsupported", "observed_contradicted", "corrected_claim_count",
        "claim_count", "retained_claim_count", "material_error_count", "numerical_mismatch_count"]}
    if not judgment or not record[field]:
        return result
    value = judgment[field]
    if "status" in value:
        if value["status"] != "assessed" or judgment["chart_readability"] == "unreadable":
            return result
        retained = value["total_claims"] - value["corrected_claims"]
        errors, contradictions = value["material_errors"], value["material_contradictions"]
        result.update(claim_count=value["total_claims"], corrected_claim_count=value["corrected_claims"],
                      retained_claim_count=retained, material_error_count=errors,
                      contradicted=bool(contradictions) if retained else None,
                      unsupported=bool(errors) if retained else None,
                      claim_error_rate=errors / retained if retained else None,
                      claim_contradiction_rate=contradictions / retained if retained else None,
                      contradicted_claim_count=value["contradicted_claims"],
                      unsupported_claim_count=value["unsupported_claims"])
        # Compact counts cannot reconstruct errors among retracted assertions.
        if not value["corrected_claims"]:
            result.update(observed_unsupported=bool(errors), observed_contradicted=bool(contradictions))
        for category in CATEGORIES:
            result[category] = category in value["error_categories"] if retained else None
        return result
    determinate = (value["applicable"] and value["coverage_complete"] and not value["requires_review"]
                   and judgment["chart_readability"] != "unreadable")
    if determinate:
        observed = copy.deepcopy(value["claims"])
        checks = numerical_checks(observed, record.get("chart_metadata", {}),
                                  record.get("numeric_tolerance", DEFAULT_POLICY["numeric_tolerance"]))
        mismatches = {check["quote"] for check in checks if not check["within_tolerance"]}
        for claim in observed:
            if claim["quote"] in mismatches:
                claim["verdict"] = "contradicted"
                if "chart_reading" not in claim["categories"]:
                    claim["categories"].append("chart_reading")
        claims = [c for c in observed if c.get("resolution") != "explicitly_corrected"]
        errors = sum(c["material"] and c["verdict"] != "supported" for c in claims)
        contradictions = sum(c["material"] and c["verdict"] == "contradicted" for c in claims)
        result.update(contradicted=bool(contradictions) if claims else None,
                      unsupported=bool(errors) if claims else None,
                      claim_error_rate=errors / len(claims) if claims else None,
                      claim_contradiction_rate=contradictions / len(claims) if claims else None,
                      observed_unsupported=any(c["material"] and c["verdict"] != "supported" for c in observed),
                      observed_contradicted=any(c["material"] and c["verdict"] == "contradicted" for c in observed),
                      corrected_claim_count=len(observed) - len(claims), claim_count=len(observed),
                      retained_claim_count=len(claims), material_error_count=errors,
                      numerical_mismatch_count=len(mismatches))
        for category in CATEGORIES:
            result[category] = any(c["material"] and c["verdict"] != "supported" and category in c["categories"] for c in claims) if claims else None
    return result


def joined(run: Path, manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    outcomes = {x["custom_id"]: x for x in lines(run / "judgments.jsonl")}
    result = []
    for record in lines(run / "records.jsonl"):
        item = dict(record)
        answer = outcomes.get(record["response_id"] + "-answer-0", {})
        ground = outcomes.get(record["response_id"] + "-grounding-0", {})
        av = answer.get("judgment", {}).get("verdict")
        item["answer_verdict"] = av
        # Explicitly missing final answers count as answer failures, not judge failures.
        item["answer_correct"] = (av == "correct") if av in {"correct", "incorrect", "missing"} else None
        if not record["final_explanation"].strip():
            item["answer_verdict"] = "missing"
            item["answer_correct"] = False
        item["judge_answer_status"] = answer.get("status", "missing")
        item["judge_grounding_status"] = ground.get("status", "missing")
        aj = answer.get("judgment", {}) if answer.get("status") == "valid" else {}
        item["strategy_followed"] = aj.get("strategy_followed") if record.get("generation_system_prompt") else None
        item["strategy_following_reason"] = aj.get("strategy_following_reason")
        item["answer_review_required"] = aj.get("review_required")
        gj = ground.get("judgment")
        item["proposed_chart_types"] = gj.get("chart_types", []) if gj else []
        metadata = record.get("chart_metadata", {})
        item["chart_types"] = metadata.get("chart_types", []) if metadata.get("human_verified") else []
        item["chart_types_human_verified"] = bool(metadata.get("human_verified") and metadata.get("chart_types"))
        item["numeric_checks"] = {f: numerical_checks(gj[f]["claims"], metadata,
            record.get("numeric_tolerance", DEFAULT_POLICY["numeric_tolerance"]))
            if gj and "claims" in gj[f] else None for f in FIELDS}
        draft_answer = outcomes.get(record["response_id"] + "-draft_answer-0", {}).get("judgment", {})
        dv = draft_answer.get("verdict")
        item["draft_answer_correct"] = (dv == "correct") if dv in {"correct", "incorrect", "missing"} else None
        draft_ground = outcomes.get(record["response_id"] + "-draft_grounding-0", {}).get("judgment")
        draft_record = {**record, **{f: record.get("draft_" + f, "") for f in FIELDS}}
        item["draft_final_metrics"] = field_metrics(draft_ground, draft_record, "final_explanation")
        for field in FIELDS:
            item[field + "_metrics"] = field_metrics(gj, record, field)
        for metric in ["contradicted", "unsupported"]:
            values = [item[f + "_metrics"][metric] for f in FIELDS if record[f]]
            # Positive union needs one confirmed positive; negative union needs every present field evaluated.
            item["either_" + metric] = True if any(v is True for v in values) else (
                False if values and all(v is False for v in values) else None)
        result.append(item)
    return result, outcomes


def metric_values(row: dict[str, Any]) -> dict[str, float | bool | None]:
    metrics = {"answer_accuracy": row["answer_correct"],
               "generation_truncation_rate": row["generation_truncated"],
               "missing_final_answer_rate": row.get("answer_missing", not bool(row["final_explanation"].strip())),
               "answer_judgment_coverage": row["answer_correct"] is not None}
    metrics["strategy_following_coverage"] = row.get("strategy_followed") is not None
    metrics["strategy_following_rate"] = row.get("strategy_followed")
    draft_answer, final_answer = row.get("draft_answer_correct"), row["answer_correct"]
    draft_error, final_error = row.get("draft_final_metrics", {}).get("unsupported"), row["final_explanation_metrics"]["unsupported"]
    metrics.update(
        verification_answer_recovery=final_answer if draft_answer is False else None,
        verification_answer_regression=not final_answer if draft_answer is True and final_answer is not None else None,
        verification_error_recovery=not final_error if draft_error is True and final_error is not None else None,
        verification_error_introduction=final_error if draft_error is False else None)
    for field in FIELDS:
        metrics[field + "_grounding_coverage"] = row[field + "_metrics"]["unsupported"] is not None if row[field] else None
        metrics[field + "_character_count"] = len(row[field])
        for key in ["contradicted", "unsupported", "claim_error_rate", "claim_contradiction_rate",
                    "observed_unsupported", "observed_contradicted", "corrected_claim_count", "claim_count",
                    "retained_claim_count", "material_error_count", "contradicted_claim_count",
                    "unsupported_claim_count", "numerical_mismatch_count", *CATEGORIES]:
            metrics[field + "_" + key] = row[field + "_metrics"].get(key)
    for kind in ["contradicted", "unsupported"]:
        metrics["either_" + kind] = row["either_" + kind]
        for field in [*FIELDS, "either"]:
            error = row["either_" + kind] if field == "either" else row[field + "_metrics"][kind]
            metrics[f"correct_answer_{field}_{kind}"] = error if row["answer_correct"] is True else None
    return metrics


def estimate(rows: list[dict[str, Any]], metric: str, iterations: int, seed: int) -> dict[str, Any]:
    import numpy as np
    clusters: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        clusters.setdefault(row["chart_id"], [])
        value = metric_values(row)[metric]
        if value is not None:
            clusters[row["chart_id"]].append(float(value))
    counts = np.array([len(v) for v in clusters.values()])
    sums = np.array([sum(v) for v in clusters.values()])
    n = int(counts.sum())
    result = {"value": float(sums.sum() / n) if n else None,
              "numerator": float(sums.sum()), "denominator": n,
              "eligible_or_resolved_records": n, "group_records": len(rows),
              "contributing_charts": int((counts > 0).sum()), "ci95": None}
    if (counts > 0).sum() >= 2:
        rng = np.random.default_rng(seed)
        draws = rng.integers(0, len(clusters), size=(iterations, len(clusters)))
        ds = counts[draws].sum(axis=1)
        means = sums[draws].sum(axis=1)[ds > 0] / ds[ds > 0]
        result["ci95"] = np.quantile(means, [0.025, 0.975]).tolist()
        result["bootstrap_valid_replicates"] = len(means)
    return result


def agreement(pairs: list[tuple[bool, bool]]) -> dict[str, Any]:
    tp = sum(h and j for h, j in pairs)
    tn = sum(not h and not j for h, j in pairs)
    fp = sum(not h and j for h, j in pairs)
    fn = sum(h and not j for h, j in pairs)
    n = len(pairs)
    divide = lambda a, b: a / b if b else None
    observed = divide(tp + tn, n)
    expected = ((tp + fn) * (tp + fp) + (tn + fp) * (tn + fn)) / n**2 if n else 1
    return {"n": n, "tp": tp, "tn": tn, "fp": fp, "fn": fn,
            "precision": divide(tp, tp + fp), "recall": divide(tp, tp + fn),
            "f1": divide(2 * tp, 2 * tp + fp + fn), "accuracy": observed,
            "cohen_kappa": (observed - expected) / (1 - expected) if n and expected < 1 else None}


def agreement_ci(pairs: list[tuple[str, bool, bool]], iterations: int, seed: int) -> dict[str, Any]:
    import numpy as np
    result = agreement([(h, j) for _, h, j in pairs])
    clusters: dict[str, list[int]] = {}
    for chart, h, j in pairs:
        counts = clusters.setdefault(chart, [0, 0, 0, 0])
        counts[0 if h and j else 1 if not h and not j else 2 if not h and j else 3] += 1
    result["charts"] = len(clusters)
    result["ci95"] = None
    if len(clusters) < 2:
        return result
    counts = np.array(list(clusters.values()))
    draws = np.random.default_rng(seed).integers(0, len(counts), size=(iterations, len(counts)))
    tp, tn, fp, fn = counts[draws].sum(axis=1).T
    n = tp + tn + fp + fn
    with np.errstate(divide="ignore", invalid="ignore"):
        observed = (tp + tn) / n
        expected = ((tp + fn) * (tp + fp) + (tn + fp) * (tn + fn)) / n**2
        values = {"precision": tp / (tp + fp), "recall": tp / (tp + fn),
                  "f1": 2 * tp / (2 * tp + fp + fn), "accuracy": observed,
                  "cohen_kappa": (observed - expected) / (1 - expected)}
    result["ci95"] = {k: np.quantile(v[np.isfinite(v)], [.025, .975]).tolist() if np.isfinite(v).any() else None
                      for k, v in values.items()}
    return result


def human_entries(path: Path, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize optional independent claim inventories into response labels."""
    by_id = {r["response_id"]: r for r in rows}
    result = []
    for entry in lines(path):
        entry = dict(entry)
        rid = entry["response_id"]
        if rid not in by_id:
            raise ValueError("Unknown response in human annotations.")
        inventory = entry.get("claim_annotations")
        if inventory is not None:
            from judge_schema_legacy import SCHEMAS as legacy_schemas
            annotation_schemas = legacy_schemas if "claims" in inventory.get("final_explanation", {}) else SCHEMAS
            validate_judgment("grounding", inventory, by_id[rid], annotation_schemas)
            for field in FIELDS:
                derived = field_metrics(inventory, by_id[rid], field)
                for metric in ["contradicted", "unsupported", *CATEGORIES]:
                    key = field + "_" + metric
                    value = derived.get(metric)
                    if entry.get(key) is not None and entry[key] != value:
                        raise ValueError("Human response label conflicts with its claim inventory or requires review.")
                    entry[key] = value
        result.append(entry)
    return result


def human_agreement(path: Path | None, rows: list[dict[str, Any]], iterations: int, seed: int) -> dict[str, Any]:
    if path is None:
        return {"available": False, "reason": "Human labels not supplied; automatic labels are not validated ground truth."}
    by_id = {r["response_id"]: r for r in rows}
    labels: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    keys = ["answer_correct", "strategy_followed", *[f"{f}_{m}" for f in FIELDS for m in ["contradicted", "unsupported", *CATEGORIES]]]
    for entry in human_entries(path, rows):
        rid, annotator = entry["response_id"], entry["annotator"]
        if not annotator or annotator == "REPLACE_ME" or rid in labels[annotator]:
            raise ValueError("Missing annotator or duplicate human label.")
        if any(entry.get(k) is not None and type(entry[k]) is not bool for k in keys):
            raise ValueError("Human labels must be true, false or null.")
        if any(entry.get(f + "_contradicted") is True and entry.get(f + "_unsupported") is False for f in FIELDS):
            raise ValueError("A human contradiction positive cannot have unsupported=false.")
        labels[annotator][rid] = entry
    result: dict[str, Any] = {"available": True, "judge_vs_human": {}, "human_vs_human": {}}
    for annotator, entries in labels.items():
        result["judge_vs_human"][annotator] = {}
        for key in keys:
            pairs = []
            for rid, entry in entries.items():
                metric = {"answer_correct": "answer_accuracy", "strategy_followed": "strategy_following_rate"}.get(key, key)
                j = metric_values(by_id[rid])[metric]
                if entry.get(key) is not None and j is not None:
                    pairs.append((by_id[rid]["chart_id"], entry[key], bool(j)))
            result["judge_vs_human"][annotator][key] = agreement_ci(pairs, iterations, seed)
    for left, right in itertools.combinations(sorted(name for name in labels if name != "adjudicated"), 2):
        result["human_vs_human"][f"{left} vs {right}"] = {
            key: agreement_ci([(by_id[rid]["chart_id"], labels[left][rid][key], labels[right][rid][key])
                            for rid in labels[left].keys() & labels[right].keys()
                            if labels[left][rid].get(key) is not None and labels[right][rid].get(key) is not None], iterations, seed)
            for key in keys}
    result["label_balance"] = {annotator: {key: {
        "positive": sum(e.get(key) is True for e in entries.values()),
        "negative": sum(e.get(key) is False for e in entries.values()),
        "uncertain_or_unassessed": sum(e.get(key) is None for e in entries.values())}
        for key in keys} for annotator, entries in labels.items()}
    result["claim_inventories_supplied"] = {annotator: sum(e.get("claim_annotations") is not None for e in entries.values())
                                            for annotator, entries in labels.items()}
    return result


def validate(args: argparse.Namespace) -> None:
    """Evaluate frozen acceptance criteria locally; never submit requests."""
    manifest = load_manifest(args.run)
    if manifest.get("version") != VERSION:
        raise ValueError("Validation requires the current judge protocol; prepare a new held-out validation run.")
    rows, _ = joined(args.run, manifest)
    human_agreement(args.human_labels, rows, args.bootstrap, args.seed)
    decision = validation_decision(manifest, rows, human_entries(args.human_labels, rows), agreement_ci, args.bootstrap, args.seed)
    save(args.run / "validation.json", {**decision, "created_at": stamp(),
        "protocol_sha256": manifest["protocol_sha256"],
        "human_labels_sha256": digest(args.human_labels.read_bytes())})
    print(json.dumps(decision, indent=2))
    if decision["status"] != "passed":
        raise SystemExit(2)


def policy(args: argparse.Namespace) -> None:
    if args.output.exists():
        raise FileExistsError("Choose a new policy filename; existing policies are never overwritten.")
    save(args.output, DEFAULT_POLICY)
    print(f"Wrote proposed acceptance rules to {args.output}. Finalize before preparing held-out validation.")


def paired_comparisons(rows: list[dict[str, Any]], iterations: int, seed: int) -> list[dict[str, Any]]:
    import numpy as np
    results = []
    metrics = ["answer_accuracy", "either_contradicted", "either_unsupported",
               "strategy_following_rate",
               *[f"{f}_{m}" for f in FIELDS for m in ["contradicted", "unsupported", "claim_error_rate"]],
               *[f"correct_answer_{f}_{m}" for f in [*FIELDS, "either"] for m in ["contradicted", "unsupported"]]]
    comparisons = []
    for model in sorted({r["model"] for r in rows}):
        strategies = sorted({r["strategy"] for r in rows if r["model"] == model})
        for left, right in itertools.combinations(strategies, 2):
            a = {r["chart_id"]: r for r in rows if r["model"] == model and r["strategy"] == left}
            b = {r["chart_id"]: r for r in rows if r["model"] == model and r["strategy"] == right}
            comparisons.append(({"model": model, "left": left, "right": right, "comparison": "strategies_within_model"}, a, b))
    for strategy in sorted({r["strategy"] for r in rows}):
        models = sorted({r["model"] for r in rows if r["strategy"] == strategy})
        for left, right in itertools.combinations(models, 2):
            a = {r["chart_id"]: r for r in rows if r["model"] == left and r["strategy"] == strategy}
            b = {r["chart_id"]: r for r in rows if r["model"] == right and r["strategy"] == strategy}
            comparisons.append(({"strategy": strategy, "left": left, "right": right, "comparison": "models_within_strategy"}, a, b))
    for info, a, b in comparisons:
        for metric in metrics:
            pairs = [(metric_values(a[c])[metric], metric_values(b[c])[metric]) for c in sorted(a.keys() & b.keys())]
            values = np.array([float(y) - float(x) for x, y in pairs if x is not None and y is not None])
            ci = None
            if len(values) >= 2:
                rng = np.random.default_rng(seed)
                means = values[rng.integers(0, len(values), size=(iterations, len(values)))].mean(axis=1)
                ci = np.quantile(means, [0.025, 0.975]).tolist()
            results.append({**info, "metric": metric,
                            "difference_right_minus_left": float(values.mean()) if len(values) else None,
                            "paired_charts": len(values), "ci95": ci,
                            "matched_chart_candidates": len(a.keys() & b.keys()),
                            "conditional_shared_successes": metric.startswith("correct_answer_")})
    return results


def report(args: argparse.Namespace) -> None:
    run = args.run
    manifest = load_manifest(run)
    rows, outcomes = joined(run, manifest)
    groups: dict[str, list[dict[str, Any]]] = {"all": rows}
    for row in rows:
        for key in [f"model={row['model']}", f"model={row['model']}|strategy={row['strategy']}"]:
            groups.setdefault(key, []).append(row)
        for chart_type in row["chart_types"]:
            key = f"model={row['model']}|strategy={row['strategy']}|chart_type={chart_type}"
            groups.setdefault(key, []).append(row)
    estimates = {key: {metric: estimate(group, metric, args.bootstrap, args.seed)
                       for metric in metric_values(group[0])} for key, group in groups.items()}
    minimum = manifest.get("policy", DEFAULT_POLICY)["min_conditional_charts"]
    warnings = []
    for group, metrics in estimates.items():
        primary = metrics["correct_answer_final_explanation_unsupported"]
        if primary["contributing_charts"] < minimum:
            warnings.append({"group": group, "reason": "too_few_correct_answer_charts_for_stable_conditional_comparison",
                             "contributing_charts": primary["contributing_charts"], "minimum": minimum})
    sensitivity = {}
    for name, group in groups.items():
        untruncated = [r for r in group if r["generation_truncated"] is False]
        sensitivity[name] = {"eligible_records": len(untruncated),
            "excluded_truncated_or_unknown": len(group) - len(untruncated),
            "metrics": {m: estimate(untruncated, m, args.bootstrap, args.seed)
                        for m in ["answer_accuracy", "correct_answer_final_explanation_unsupported",
                                  "final_explanation_claim_error_rate"]}}
    human_results = human_agreement(args.human_labels, rows, args.bootstrap, args.seed)
    decision = {"status": "not_validated", "reason": "No held-out human validation supplied."}
    if manifest.get("stage") == "validation" and args.human_labels:
        decision = validation_decision(manifest, rows, human_entries(args.human_labels, rows), agreement_ci, args.bootstrap, args.seed)
    elif manifest.get("validation_evidence"):
        decision = manifest["validation_evidence"]["decision"]
    repeats: dict[str, Any] = {}
    for field in [*FIELDS, "either"]:
        for kind in ["contradicted", "unsupported"]:
            pairs = []
            for row in rows:
                repeated = outcomes.get(row["response_id"] + "-grounding-1", {}).get("judgment")
                if not repeated:
                    continue
                values = [field_metrics(repeated, row, f)[kind] for f in FIELDS if row[f]]
                repeat_value = (True if any(v is True for v in values) else
                                False if values and all(v is False for v in values) else None) if field == "either" else field_metrics(repeated, row, field)[kind]
                initial = row["either_" + kind] if field == "either" else row[field + "_metrics"][kind]
                if initial is not None and repeat_value is not None:
                    pairs.append((initial, repeat_value))
            repeats[field + "_" + kind] = agreement(pairs)
    usage_rows = lines(run / "usage.jsonl") if (run / "usage.jsonl").exists() else []
    usage = {key: sum(item["usage"].get(key, 0) for item in usage_rows) for key in ["input_tokens", "output_tokens", "total_tokens"]}
    usage["reasoning_tokens"] = sum((u["usage"].get("output_tokens_details") or {}).get("reasoning_tokens", 0) for u in usage_rows)
    usage["cached_input_tokens"] = sum((u["usage"].get("input_tokens_details") or {}).get("cached_tokens", 0) for u in usage_rows)
    # Optional explicit pricing, never silently apply Sol rates to another judge.
    rates = (args.input_usd_per_million, args.output_usd_per_million, args.cached_input_usd_per_million)
    if any(rate is not None for rate in rates) and not all(rate is not None and rate >= 0 for rate in rates):
        raise ValueError("Supply all three nonnegative token prices, or none.")
    estimated_cost = None
    if all(rate is not None for rate in rates):
        estimated_cost = {"usd": ((usage["input_tokens"] - usage["cached_input_tokens"]) * rates[0]
                                  + usage["output_tokens"] * rates[1] + usage["cached_input_tokens"] * rates[2]) / 1_000_000,
                          "input_usd_per_million": rates[0], "output_usd_per_million": rates[1],
                          "cached_input_usd_per_million": rates[2], "pricing_mode": "standard" if manifest.get("provider_config", {}).get("api") == "generateContent" else "batch",
                          "note": "User-supplied rates; not an invoice. Excludes any other service fees."}
    summary = {"version": manifest["version"], "provider": manifest.get("provider", "openai"), "created_at": stamp(), "judge_model_requested": manifest["model"],
               "returned_models": sorted({u["returned_model"] for u in usage_rows if u.get("returned_model")}),
               "automatic_labels_are_human_validated": decision["status"] == "passed",
               "human_validation_scope": "Answer correctness and final-explanation unsupported response labels; other metrics are exploratory.",
               "validation": decision, "stage": manifest.get("stage", "legacy"),
               "primary_metric": "correct_answer_final_explanation_unsupported",
               "small_sample_warnings": warnings,
               "untruncated_sensitivity": sensitivity,
               "chart_type_analysis": "Only human-verified labels define subgroups; mixed charts contribute to each applicable type.",
               "judgment_coverage": dict(Counter(x["status"] for x in outcomes.values())),
               "response_coverage_by_group": {name: {
                   "responses": len(group), "charts": len({r["chart_id"] for r in group}),
                   "answer_verdicts": dict(Counter(r["answer_verdict"] or "unresolved" for r in group)),
                   "grounding_task_statuses": dict(Counter(r["judge_grounding_status"] for r in group)),
                   "strategy_following_labels": dict(Counter("unassessed" if r["strategy_followed"] is None else
                       "followed" if r["strategy_followed"] else "not_followed" for r in group)),
                   "present_text_fields": {f: sum(bool(r[f]) for r in group) for f in FIELDS},
                   "resolved_grounding_fields": {f: sum(r[f + "_metrics"]["unsupported"] is not None for r in group) for f in FIELDS},
                   "generator_truncated": sum(r["generation_truncated"] is True for r in group),
                   "truncation_unknown": sum(r["generation_truncated"] is None for r in group),
                   "generation_configs": list({json.dumps(r.get("generation_config", {}), sort_keys=True) for r in group}),
                   "generator_usage_totals": {key: sum(r.get("generator_usage", {}).get(key) or 0 for r in group)
                       for key in ["input_tokens", "generated_tokens", "generation_seconds", "elapsed_seconds", "request_count"]}}
                   for name, group in groups.items()},
               "bootstrap": {"unit": "chart", "iterations": args.bootstrap, "seed": args.seed,
                             "interval": "percentile 95%; exploratory, not multiplicity adjusted"},
               "groups": estimates, "paired_strategy_comparisons": paired_comparisons(rows, args.bootstrap, args.seed),
               "human_agreement": human_results, "repeat_stability": repeats,
               "usage_including_retries_and_repeats": usage,
               "estimated_api_cost": estimated_cost,
               "batch_runtime_seconds": {c["batch_id"]: c["batch_snapshot"]["completed_at"] - c["batch_snapshot"]["created_at"]
                   for c in manifest["chunks"] if c.get("batch_id") and c.get("batch_snapshot", {}).get("completed_at")
                   and c.get("batch_snapshot", {}).get("created_at")},
               "limitations": ["Judge labels require independent human validation.",
                   "Conditional rates exclude unresolved judgments; denominators and missingness must be reported.",
                   "Paired conditional comparisons include only charts answered correctly under BOTH strategies.",
                   "Claim error rate is macro averaged per response over the judge's distinct-claim inventory.",
                   "No corrected prevalence or confirmatory significance claim is made.",
                   "Same token cap is not the same compute budget across model tokenizers."]}
    if manifest["version"] == VERSION:
        summary["limitations"].append(
            "Compact counts omit claim quotations and deterministic per-claim numeric checks; "
            "observed-error metrics are unavailable when corrected claims occur.")
    save(run / "summary.json", summary)
    jsonl(run / "evaluated_responses.jsonl", rows)
    chart_proposals = {}
    for row in rows:
        chart_proposals.setdefault(row["chart_id"], {"example_id": row["example_id"],
            "image_path": row["image_path"], "human_verified": row["chart_types_human_verified"],
            "chart_types": row["chart_types"], "proposals": []})["proposals"].append(row["proposed_chart_types"])
    save(run / "chart_type_review.json", chart_proposals)
    review = []
    for row in rows:
        reasons = []
        if row["judge_grounding_status"] != "valid" or row["judge_answer_status"] != "valid":
            reasons.append("missing_or_invalid_judge_output")
        if row["answer_correct"] is None:
            reasons.append("unresolved_answer")
        if row["strategy_followed"] is None:
            reasons.append("unresolved_instruction_following" if row.get("generation_system_prompt") else "missing_generation_prompt")
        if row["generation_truncated"]:
            reasons.append("generator_truncated")
        if row.get("answer_missing", not row["final_explanation"].strip()):
            reasons.append("missing_final_answer")
        if any(not check["within_tolerance"] for checks in row["numeric_checks"].values() for check in (checks or [])):
            reasons.append("verified_table_numeric_mismatch")
        if any(row[f] and row[f + "_metrics"]["unsupported"] is None for f in FIELDS):
            reasons.append("unresolved_or_nonapplicable_grounding")
        if random.Random(row["response_id"] + str(args.seed)).random() < .05:
            reasons.append("seeded_random_audit")
        if reasons:
            review.append({**row, "review_reasons": reasons})
    jsonl(run / "review_queue.jsonl", review)
    with (run / "metrics.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["group", "metric", "value", "numerator", "denominator", "group_records", "contributing_charts", "ci95_low", "ci95_high"])
        for group, metrics in estimates.items():
            for metric, value in metrics.items():
                writer.writerow([group, metric, value["value"], value["numerator"], value["denominator"],
                                 value["group_records"], value["contributing_charts"], *(value["ci95"] or [None, None])])
    print(f"Saved summary.json, metrics.csv, evaluated_responses.jsonl and review_queue.jsonl in {run}")


def parse_args(provider: str) -> argparse.Namespace:
    load_environment()
    model_variable = "OPENAI_MODEL_ID" if provider == "openai" else "GOOGLE_MODEL_ID"
    default_model = os.environ.get(model_variable, "").strip() or ("gpt-6.2-sol" if provider == "openai" else None)
    parser = argparse.ArgumentParser(description="Chart explanation judging: " +
                                     ("OpenAI Batch" if provider == "openai" else "Google AI Studio"))
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("policy", help="Export proposed acceptance/tolerance rules for review; no API usage.")
    p.add_argument("--output", type=Path, required=True)
    p = commands.add_parser("prepare", help="Build local blinded JSONL shards; no API usage.")
    p.add_argument("inputs", nargs="+", type=Path)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--model", default=default_model, help=f"Overrides {model_variable} from the environment or .env.")
    p.add_argument("--effort", choices=["low", "medium", "high"] if provider == "openai" else ["default", "low", "medium", "high"], default="medium" if provider == "openai" else "default")
    p.add_argument("--answer-tokens", type=int, default=2048)
    p.add_argument("--grounding-tokens", type=int, default=12000)
    p.add_argument("--max-shard-mb", type=float, default=150)
    p.add_argument("--repeat-fraction", type=float, default=0.05)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--chart-limit", type=int, help="Prepare only the first N chart IDs, retaining their responses across inputs.")
    p.add_argument("--stage", choices=["development", "validation", "evaluation"], default="development")
    p.add_argument("--policy", type=Path, help="JSON acceptance/tolerance policy, frozen before judging.")
    p.add_argument("--chart-metadata", type=Path, help="Human-checked chart types and optional verified source cells.")
    p.add_argument("--exclude-run", type=Path, action="append", default=[], help="Exclude all charts from this previous run, including its exclusions.")
    p.add_argument("--validated-run", type=Path, help="Held-out validation run required for evaluation.")
    p.add_argument("--human-labels", type=Path, help="Independent and adjudicated validation labels required for evaluation.")
    for command in ["submit", "status", "collect", "retry", "report", "attach", "validate"]:
        p = commands.add_parser(command)
        p.add_argument("--run", type=Path, required=True)
        if command in {"report", "validate"}:
            p.add_argument("--human-labels", type=Path, required=command == "validate")
            p.add_argument("--bootstrap", type=int, default=2000)
            p.add_argument("--seed", type=int, default=42)
        if command == "report":
            p.add_argument("--input-usd-per-million", type=float)
            p.add_argument("--output-usd-per-million", type=float)
            p.add_argument("--cached-input-usd-per-million", type=float)
        if command == "attach":
            p.add_argument("--chunk", type=int, required=True)
            p.add_argument("--batch-id", required=True)
    args = parser.parse_args()
    if args.command == "prepare" and (not args.model or not args.model.strip()):
        parser.error(f"Set {model_variable} in .env or pass --model.")
    if args.command == "prepare" and (not 0 <= args.repeat_fraction <= 1 or not 0 < args.max_shard_mb <= 190
                                     or min(args.answer_tokens, args.grounding_tokens) < 1
                                     or args.chart_limit is not None and args.chart_limit < 1):
        parser.error("Invalid repeat fraction, shard size or token budget.")
    if args.command in {"report", "validate"} and args.bootstrap < 100:
        parser.error("Use at least 100 bootstrap replicates.")
    return args

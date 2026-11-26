"""Run the four CharXiv chart-explanation strategies on one Eden GPU.

The script downloads the Hugging Face model and dataset, runs inference, and
checkpoints a valid JSON document after every completed strategy. It can be
submitted with Slurm or run with --prepare-only on a login node to fill a
shared Hugging Face cache before an offline GPU job.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import signal
import sys
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = PROJECT_ROOT / "outputs" / "eden_gemma4_e4b" / "results.json"
MODEL_ID = "google/gemma-4-E4B-it"  # Hugging Face instruction model, not the LM Studio alias.
ATTENTION_IMPLEMENTATION = {"audio_config": "eager"}  # Other backbones retain SDPA.
DATASET_ID = "princeton-nlp/CharXiv"
SPLIT = "validation"  # CharXiv test answers are withheld.
MAX_CHARTS = 1250
PILOT_FIGURES = {
    "images/1524.jpg", "images/270.jpg", "images/56.jpg",
    "images/1773.jpg", "images/640.jpg",
}

COMMON_RULES = (
    "Answer the question using only the attached chart. Do not invent chart labels, "
    "values, or units. For comparisons, inspect the relevant series over the same "
    "range; for slopes, compare their vertical changes between two visible x-values "
    "rather than relying only on whether the lines look parallel. When the chart is "
    "readable, choose the best-supported candidate even if the difference is small, "
    "and express any uncertainty in the explanation. Say that the answer cannot be "
    "determined only when the relevant chart evidence is absent or unreadable."
)
STRATEGY_PROMPTS = {
    "direct": (
        f"{COMMON_RULES} Give a brief explanation based on the chart, followed by "
        "a line beginning 'Final answer:'."
    ),
    "structured": (
        f"{COMMON_RULES} First write 'Chart evidence:' and list only the chart "
        "labels, values, units, and comparisons needed for this question. Then write "
        "'Explanation:' connecting that evidence to your answer. Finish with a line "
        "beginning 'Final answer:'."
    ),
    "chain_of_thought": (
        f"{COMMON_RULES} Explain the sequence of chart-reading and calculation steps "
        "that supports your answer. State which visible chart evidence supports each "
        "step, and show any arithmetic. Finish with a line beginning 'Final answer:'."
    ),
    "verification": (
        f"{COMMON_RULES} You are checking a fallible draft response. Re-read the chart and "
        "check every material claim in the draft, including labels, values, units, "
        "comparisons, and arithmetic. If the draft abstains, check whether the chart "
        "still supports a best answer. Correct unsupported claims. Write 'Checks:' "
        "with the evidence you verified, then 'Explanation:' and a line beginning "
        "'Final answer:'."
    ),
}
VERIFICATION_DRAFT_PROMPT = (
    f"{COMMON_RULES} Draft an answer with a brief chart-based explanation and a "
    "line beginning 'Final answer:'. This draft will be checked in a second pass."
)
PROMPT_FINGERPRINT = hashlib.sha256(
    json.dumps({"strategies": STRATEGY_PROMPTS, "draft": VERIFICATION_DRAFT_PROMPT}, sort_keys=True).encode()
).hexdigest()


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def exclusion_figures(paths: list[Path], prior: dict[str, Any] | None) -> list[str]:
    """Load generated chart IDs; keep exclusions in the checkpoint for resume."""
    if not paths:
        return sorted(prior.get("excluded_previous_figures", [])) if prior else []
    figures: set[str] = set()
    for path in paths:
        path = path.expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        document = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(document, dict) or document.get("dataset") != DATASET_ID
                or document.get("split") != SPLIT
                or not isinstance(document.get("results"), list)):
            raise ValueError(f"{path} must be an Eden {DATASET_ID} {SPLIT} results file.")
        for record in document["results"]:
            figure = record.get("example_id") if isinstance(record, dict) else None
            if not isinstance(figure, str) or not figure:
                raise ValueError(f"{path} contains a result without a valid example_id.")
            figures.add(figure)
    excluded = sorted(figures)
    if prior is not None and excluded != sorted(prior.get("excluded_previous_figures", [])):
        raise ValueError("Cannot resume: exclusions differ from the saved run.")
    return excluded


def select_charts(figures: list[str], questions: list[Any], answers: list[Any],
                  n: int, seed: int, excluded: list[str]) -> list[int]:
    blocked = PILOT_FIGURES | set(excluded)
    valid_indices = [i for i, (figure, question, answer) in
                     enumerate(zip(figures, questions, answers))
                     if figure not in blocked and question and answer]
    if n > len(valid_indices):
        raise ValueError(f"Requested {n} charts, but only {len(valid_indices)} remain "
                         "with reasoning Q/A after pilot and previous-run exclusions.")
    return random.Random(seed).sample(valid_indices, n)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=125, help="Charts to sample (default: 125; max: 1250).")
    parser.add_argument("--seed", type=int, default=20261117)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--exclude-from", type=Path, action="append", default=[],
                        help="Exclude generated charts in an Eden results JSON; repeat for multiple runs.")
    parser.add_argument("--cache-dir", type=Path, help="Shared Hugging Face cache; default is the user's HF cache.")
    parser.add_argument("--model-revision", help="Model commit hash; resolved automatically when online.")
    parser.add_argument("--dataset-revision", help="Dataset commit hash; resolved automatically when online.")
    parser.add_argument("--max-new-tokens", type=int, default=1536)
    parser.add_argument("--time-budget-hours", type=float, default=22.0)
    parser.add_argument("--resume", action="store_true", help="Continue an interrupted matching output.")
    parser.add_argument("--prepare-only", action="store_true", help="Download model and dataset without loading a GPU model.")
    parser.add_argument("--offline", action="store_true", help="Use only a previously prepared shared cache.")
    return parser.parse_args()


def response_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(response_text(item) for item in value)
    if isinstance(value, dict):
        return str(value.get("text", value.get("content", value)))
    return "" if value is None else str(value)


def parse_gemma_output(processor: Any, raw: str, prefix: Any) -> tuple[str, str, str]:
    """Return final content, exposed thinking text, and parser method."""
    try:
        parsed = processor.parse_response(raw, prefix=prefix)
        answer = response_text(parsed.get("content", "")).strip()
        reasoning = response_text(parsed.get("reasoning_content") or parsed.get("thinking") or "").strip()
        if answer:
            return answer, reasoning, "processor.parse_response"
    except (AttributeError, TypeError, ValueError):
        pass

    # Keep an auditable fallback for older Transformers response templates.
    if "<|channel>thought\n" in raw:
        thought = raw.split("<|channel>thought\n", 1)[1]
        if "<channel|>" in thought:
            reasoning, answer = thought.split("<channel|>", 1)
            answer = answer.replace("<|channel>final\n", "").replace("<|turn|>", "").strip()
            if answer:
                return answer, reasoning.strip(), "gemma_channel_fallback"
    answer = raw.replace("<|turn|>", "").strip()
    return answer, "", "raw_fallback"


def generate_response(
    model: Any, processor: Any, torch: Any, image_path: Path,
    question: str, system_prompt: str, max_new_tokens: int,
    draft: str | None = None,
) -> dict[str, Any]:
    user_text = f"Question: {question}"
    if draft is not None:
        user_text += f"\n\nDraft response to check against the chart:\n{draft}"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": [
            {"type": "image", "path": str(image_path)},
            {"type": "text", "text": user_text},
        ]},
    ]
    inputs = processor.apply_chat_template(
        messages, tokenize=True, return_dict=True, return_tensors="pt",
        add_generation_prompt=True, enable_thinking=True,
    ).to(model.device)
    input_tokens = int(inputs["input_ids"].shape[-1])
    started = time.monotonic()
    with torch.inference_mode():
        generated = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
    elapsed = time.monotonic() - started
    generated_ids = generated[0][input_tokens:]
    raw = processor.decode(generated_ids, skip_special_tokens=False)
    answer, reasoning, parse_method = parse_gemma_output(processor, raw, inputs["input_ids"])
    return {
        "model_answer": answer,
        "model_reasoning": reasoning,
        "reasoning_returned": bool(reasoning),
        "raw_model_output": raw,
        "parse_method": parse_method,
        "input_tokens": input_tokens,
        "generated_tokens": int(generated_ids.shape[-1]),
        "generation_truncated": int(generated_ids.shape[-1]) >= max_new_tokens,
        "generation_seconds": round(elapsed, 3),
    }


def save_chart(row: dict[str, Any], destination: Path) -> str:
    from PIL import Image

    image = row["image"]
    if isinstance(image, dict):
        if image.get("bytes"):
            image = Image.open(BytesIO(image["bytes"]))
        elif image.get("path"):
            image = Image.open(image["path"])
    if not isinstance(image, Image.Image):
        raise TypeError(f"Unsupported CharXiv image type: {type(image).__name__}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.is_file():
        image.convert("RGB").save(destination, format="PNG")
    return hashlib.sha256(destination.read_bytes()).hexdigest()


def resolve_revisions(args: argparse.Namespace, prior: dict[str, Any] | None, manifest: dict[str, Any]) -> tuple[str, str]:
    model_rev = args.model_revision or (prior or {}).get("model_revision") or manifest.get("model_revision")
    dataset_rev = args.dataset_revision or (prior or {}).get("dataset_revision") or manifest.get("dataset_revision")
    if args.offline:
        if not model_rev or not dataset_rev:
            raise ValueError("Offline mode needs a cache manifest from --prepare-only or explicit commit revisions.")
    else:
        from huggingface_hub import HfApi

        api = HfApi()
        model_rev = model_rev or api.model_info(MODEL_ID).sha
        dataset_rev = dataset_rev or api.dataset_info(DATASET_ID).sha
    return model_rev, dataset_rev


def main() -> None:
    job_started = time.monotonic()
    args = parse_args()
    if not 1 <= args.n <= MAX_CHARTS:
        raise ValueError(f"--n must be between 1 and {MAX_CHARTS}.")
    if args.max_new_tokens < 1 or args.time_budget_hours <= 0:
        raise ValueError("--max-new-tokens and --time-budget-hours must be positive.")
    output = args.output if args.output.is_absolute() else PROJECT_ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not args.resume and not args.prepare_only:
        raise FileExistsError(f"{output} already exists; use --resume or choose another --output.")
    if args.resume and not output.is_file():
        raise FileNotFoundError(f"Cannot resume: {output} does not exist.")
    prior = json.loads(output.read_text(encoding="utf-8")) if args.resume else None
    excluded = exclusion_figures(args.exclude_from, prior)
    if prior and prior.get("status") == "complete":
        for key, value in {"sample_size": args.n, "seed": args.seed,
                           "prompt_fingerprint": PROMPT_FINGERPRINT,
                           "max_new_tokens": args.max_new_tokens}.items():
            if prior.get(key) != value:
                raise ValueError(f"Cannot resume: {key} differs from the saved run.")
        print(f"Run already complete: {output}", flush=True)
        return

    manifest_path = output.parent / "cache_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    if args.offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
    if not args.prepare_only:
        import torch

        if not torch.cuda.is_available():
            raise RuntimeError("No CUDA GPU is visible. Run inference inside a Slurm GPU allocation.")
    from datasets import load_dataset
    from huggingface_hub import snapshot_download

    model_revision, dataset_revision = resolve_revisions(args, prior, manifest)
    cache_dir = str(args.cache_dir.expanduser().resolve()) if args.cache_dir else manifest.get("cache_dir")
    print(f"Preparing {MODEL_ID} at {model_revision} and {DATASET_ID} at {dataset_revision}", flush=True)
    snapshot = Path(snapshot_download(
        repo_id=MODEL_ID, revision=model_revision, cache_dir=cache_dir,
        local_files_only=args.offline,
    ))
    dataset = load_dataset(DATASET_ID, split=SPLIT, revision=dataset_revision, cache_dir=cache_dir)
    required = {"image", "figure_path", "reasoning_q", "reasoning_a"}
    missing = required.difference(dataset.column_names)
    if missing:
        raise ValueError(f"CharXiv validation is missing columns: {', '.join(sorted(missing))}")
    write_json_atomic(manifest_path, {
        "model_id": MODEL_ID, "model_revision": model_revision,
        "dataset_id": DATASET_ID, "dataset_revision": dataset_revision,
        "cache_dir": cache_dir,
        "prepared_at_utc": now_utc(),
    })
    if args.prepare_only:
        print(f"Cached model at {snapshot}; cached {len(dataset)} validation charts.", flush=True)
        print(f"Cache manifest: {manifest_path}", flush=True)
        return

    import transformers
    from tqdm.auto import tqdm
    from transformers import AutoModelForImageTextToText, AutoProcessor

    figures = dataset["figure_path"]
    questions = dataset["reasoning_q"]
    answers = dataset["reasoning_a"]
    selected_indices = select_charts(figures, questions, answers, args.n, args.seed, excluded)
    print(f"Excluded {len(excluded)} previously generated chart IDs; selected {len(selected_indices)} charts.", flush=True)
    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    print(f"Loading model on {torch.cuda.get_device_name(0)} with {dtype}", flush=True)
    processor = AutoProcessor.from_pretrained(snapshot)
    model = AutoModelForImageTextToText.from_pretrained(
        snapshot, dtype=dtype, device_map="auto",
        attn_implementation=ATTENTION_IMPLEMENTATION,
    )
    model.eval()
    placements = {str(place) for place in getattr(model, "hf_device_map", {}).values()}
    if "cpu" in placements or "disk" in placements or not str(model.device).startswith("cuda"):
        raise RuntimeError(f"Model offloaded to {placements}; request a GPU with enough memory.")

    expected = {
        "dataset": DATASET_ID, "dataset_revision": dataset_revision, "split": SPLIT,
        "model": MODEL_ID, "model_revision": model_revision, "sample_size": args.n,
        "seed": args.seed, "selected_indices": selected_indices,
        "prompt_fingerprint": PROMPT_FINGERPRINT, "max_new_tokens": args.max_new_tokens,
        "dtype": str(dtype), "attn_implementation": ATTENTION_IMPLEMENTATION,
    }
    if prior:
        for key, value in expected.items():
            if prior.get(key) != value:
                raise ValueError(f"Cannot resume: {key} differs from the saved run.")
        document = prior
        document.pop("last_error", None)
        document["status"] = "in_progress"
    else:
        document = {
            **expected,
            "excluded_previous_figures": excluded,
            "excluded_pilot_figures": sorted(PILOT_FIGURES),
            "generation": {"do_sample": False, "enable_thinking": True},
            "strategy_prompts": STRATEGY_PROMPTS,
            "verification_draft_prompt": VERIFICATION_DRAFT_PROMPT,
            "torch_version": torch.__version__,
            "transformers_version": transformers.__version__,
            "gpu_name": torch.cuda.get_device_name(0),
            "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
            "created_at_utc": now_utc(),
            "status": "in_progress",
            "results": [],
        }
        write_json_atomic(output, document)

    completed = {(record["dataset_index"], record["prompt_strategy"])
                 for record in document["results"]}
    completed_calls = sum(record["request_count"] for record in document["results"])
    requested_stop = False

    def stop_after_current(_signum: int, _frame: Any) -> None:
        nonlocal requested_stop
        requested_stop = True

    signal.signal(signal.SIGUSR1, stop_after_current)
    signal.signal(signal.SIGTERM, stop_after_current)
    total_calls = args.n * 5  # Direct, structured, CoT, and two verification calls.
    try:
        with tqdm(total=total_calls, initial=completed_calls, desc="Gemma 4", unit="call") as progress:
            for sample_number, row_index in enumerate(selected_indices, start=1):
                row = dataset[row_index]
                figure_id = str(row["figure_path"])
                image_path = output.parent / "images" / f"{sample_number:04d}_{Path(figure_id).stem}.png"
                image_hash = save_chart(row, image_path)
                for strategy, system_prompt in STRATEGY_PROMPTS.items():
                    if (row_index, strategy) in completed:
                        continue
                    if requested_stop or time.monotonic() - job_started >= args.time_budget_hours * 3600:
                        document["status"] = "paused"
                        document["updated_at_utc"] = now_utc()
                        write_json_atomic(output, document)
                        print(f"Paused with {len(document['results'])}/{args.n * 4} results: {output}", flush=True)
                        return
                    question = str(row["reasoning_q"])
                    strategy_started = time.monotonic()
                    draft = None
                    if strategy == "verification":
                        draft = generate_response(model, processor, torch, image_path, question,
                                                  VERIFICATION_DRAFT_PROMPT, args.max_new_tokens)
                        progress.update(1)
                    final = generate_response(
                        model, processor, torch, image_path, question,
                        system_prompt, args.max_new_tokens,
                        draft=draft["model_answer"] if draft else None,
                    )
                    progress.update(1)
                    record = {
                        "sample_number": sample_number,
                        "dataset_index": row_index,
                        "example_id": figure_id,
                        "question": question,
                        "correct_answer": str(row["reasoning_a"]),
                        "image_path": image_path.relative_to(output.parent).as_posix(),
                        "image_sha256": image_hash,
                        "prompt_strategy": strategy,
                        "system_prompt": system_prompt,
                        **final,
                        "request_count": 2 if draft else 1,
                        "elapsed_seconds": round(time.monotonic() - strategy_started, 3),
                    }
                    if draft:
                        record["draft_system_prompt"] = VERIFICATION_DRAFT_PROMPT
                        record["draft_model_answer"] = draft["model_answer"]
                        record["draft_model_reasoning"] = draft["model_reasoning"]
                        record["draft_raw_model_output"] = draft["raw_model_output"]
                    document["results"].append(record)
                    document["updated_at_utc"] = now_utc()
                    write_json_atomic(output, document)
                    print(f"[{len(document['results'])}/{args.n * 4}] {figure_id} / {strategy}", flush=True)
    except (Exception, KeyboardInterrupt) as error:
        document["status"] = "failed"
        document["last_error"] = f"{type(error).__name__}: {error}"
        document["updated_at_utc"] = now_utc()
        write_json_atomic(output, document)
        raise
    document["status"] = "complete"
    document["completed_at_utc"] = now_utc()
    write_json_atomic(output, document)
    print(f"Saved {len(document['results'])} results to {output}", flush=True)


if __name__ == "__main__":
    main()

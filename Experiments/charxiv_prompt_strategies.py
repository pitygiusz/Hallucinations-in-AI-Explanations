"""Compare four chart-explanation prompts on the same CharXiv examples."""

from __future__ import annotations

import argparse
import json
import mimetypes
import random
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

import requests
from tqdm.auto import tqdm

import charxiv_pipeline as base


DEFAULT_OUTPUT_PATH = base.PROJECT_ROOT / "outputs" / "prompt_strategies" / "charxiv_answers_v2.json"

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


def _ask_lm_studio(
    *,
    session: requests.Session,
    api_url: str,
    model: str,
    system_prompt: str,
    question: str,
    image_data_url: str,
    timeout: int,
    draft: str | None = None,
) -> tuple[str, str]:
    user_text = f"Question: {question}"
    if draft is not None:
        user_text += f"\n\nDraft response to check against the chart:\n{draft}"
    payload = {
        "model": model,
        "system_prompt": system_prompt,
        "input": [
            {"type": "text", "content": user_text},
            {"type": "image", "data_url": image_data_url},
        ],
        "temperature": 0,
        "reasoning": "on",
        "store": False,
    }
    response = session.post(api_url, json=payload, timeout=timeout)
    response.raise_for_status()
    return base._extract_output(response.json())


def _save_image(example: dict[str, Any], sample_number: int, output_dir: Path) -> str:
    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    source_name = Path(example["example_id"]).name
    extension = Path(source_name).suffix or mimetypes.guess_extension(example["image_mime_type"]) or ".img"
    image_path = images_dir / f"{sample_number:03d}_{Path(source_name).stem}{extension}"
    image_path.write_bytes(example["image_bytes"])
    return image_path.relative_to(output_dir).as_posix()


def _write_json(output: Path, document: dict[str, Any]) -> None:
    output.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_pipeline(
    *,
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
    n: int = base.DEFAULT_N,
    seed: int = base.DEFAULT_SEED,
    dataset_id: str = base.DATASET_ID,
    split: str = "validation",
    model: str = base.DEFAULT_MODEL,
    api_url: str = base.DEFAULT_API_URL,
    timeout: int = 300,
    resume: bool = False,
) -> Path:
    """Run every sampled chart through four strategies and save one record per pair."""
    rows = base.load_reasoning_rows(dataset_id, split)
    if n < 1 or n > len(rows):
        raise ValueError(f"Requested n={n}, but found {len(rows)} reasoning examples.")
    selected_indices = random.Random(seed).sample(range(len(rows)), n)
    output = Path(output_path)
    if not output.is_absolute():
        output = base.PROJECT_ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)

    if resume:
        if not output.is_file():
            raise FileNotFoundError(f"Cannot resume: output file does not exist: {output}")
        document = json.loads(output.read_text(encoding="utf-8"))
        expected = {"dataset": dataset_id, "split": split, "sample_size": n, "seed": seed,
                    "model": model, "api_url": api_url, "selected_indices": selected_indices,
                    "strategy_prompts": STRATEGY_PROMPTS}
        for key, value in expected.items():
            if document.get(key) != value:
                raise ValueError(f"Cannot resume: {key} differs from the existing output.")
    else:
        document = {
            "dataset": dataset_id,
            "split": split,
            "sample_size": n,
            "seed": seed,
            "model": model,
            "api_url": api_url,
            "selected_indices": selected_indices,
            "strategy_prompts": STRATEGY_PROMPTS,
            "verification_draft_prompt": VERIFICATION_DRAFT_PROMPT,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": "in_progress",
            "results": [],
        }
        _write_json(output, document)

    completed = {(record["dataset_index"], record["prompt_strategy"])
                 for record in document["results"]}
    total_requests = n * (len(STRATEGY_PROMPTS) + 1)  # Verification uses two calls.
    completed_requests = sum(record["request_count"] for record in document["results"])
    with requests.Session() as session, tqdm(
        total=total_requests, initial=completed_requests, desc="LM Studio", unit="request"
    ) as progress:
        for sample_number, row_index in enumerate(selected_indices, start=1):
            example = base._prepare_example(rows[row_index], row_index)
            image_path = _save_image(example, sample_number, output.parent)
            for strategy, system_prompt in STRATEGY_PROMPTS.items():
                if (row_index, strategy) in completed:
                    continue
                started = perf_counter()
                draft_answer = None
                draft_reasoning = None
                if strategy == "verification":
                    draft_reasoning, draft_answer = _ask_lm_studio(
                        session=session, api_url=api_url, model=model,
                        system_prompt=VERIFICATION_DRAFT_PROMPT,
                        question=example["question"], image_data_url=example["image_data_url"],
                        timeout=timeout,
                    )
                    progress.update(1)
                reasoning, answer = _ask_lm_studio(
                    session=session, api_url=api_url, model=model,
                    system_prompt=system_prompt, question=example["question"],
                    image_data_url=example["image_data_url"], timeout=timeout,
                    draft=draft_answer,
                )
                progress.update(1)
                record = {
                    "sample_number": sample_number,
                    "dataset_index": row_index,
                    "example_id": example["example_id"],
                    "question": example["question"],
                    "correct_answer": example["correct_answer"],
                    "image_path": image_path,
                    "prompt_strategy": strategy,
                    "system_prompt": system_prompt,
                    "model_answer": answer,
                    "model_reasoning": reasoning,
                    "reasoning_returned": bool(reasoning),
                    "request_count": 2 if strategy == "verification" else 1,
                    "elapsed_seconds": round(perf_counter() - started, 3),
                }
                if strategy == "verification":
                    record["draft_system_prompt"] = VERIFICATION_DRAFT_PROMPT
                    record["draft_model_answer"] = draft_answer
                    record["draft_model_reasoning"] = draft_reasoning
                document["results"].append(record)
                _write_json(output, document)

    document["status"] = "complete"
    document["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    _write_json(output, document)
    return output.resolve()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=base.DEFAULT_N)
    parser.add_argument("--seed", type=int, default=base.DEFAULT_SEED)
    parser.add_argument("--split", default="validation")
    parser.add_argument("--dataset", default=base.DATASET_ID)
    parser.add_argument("--model", default=base.DEFAULT_MODEL)
    parser.add_argument("--api-url", default=base.DEFAULT_API_URL)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--resume", action="store_true", help="Continue a matching partial run.")
    args = parser.parse_args()
    path = run_pipeline(
        output_path=args.output, n=args.n, seed=args.seed, dataset_id=args.dataset,
        split=args.split, model=args.model, api_url=args.api_url,
        timeout=args.timeout, resume=args.resume,
    )
    print(f"Saved {args.n * len(STRATEGY_PROMPTS)} results to {path}")


if __name__ == "__main__":
    main()

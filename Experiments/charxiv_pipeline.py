"""Small reproducible CharXiv-to-LM-Studio evaluation pipeline."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import random
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from datasets import load_dataset


## SELECT MODEL ##
DEFAULT_MODEL = "google/gemma-4-e4b"
#DEFAULT_MODEL = "qwen/qwen3.5-9b"

DATASET_ID = "princeton-nlp/CharXiv"
DEFAULT_SEED = 42
DEFAULT_N = 25
DEFAULT_API_URL = "http://localhost:1234/api/v1/chat"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "outputs" / "charxiv_lm_studio_answers.json"
def _text(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return "\n".join(map(str, value))
    return str(value)


def _image_bytes(value: Any) -> tuple[bytes, str]:
    """Convert datasets/PIL image representations to bytes and a MIME type."""
    if isinstance(value, dict):
        raw = value.get("bytes")
        path = value.get("path")
        if raw:
            data = raw
            mime = mimetypes.guess_type(path or "chart.png")[0] or "image/png"
            return data, mime
        if path:
            image_path = Path(path)
            return image_path.read_bytes(), mimetypes.guess_type(path)[0] or "image/png"
    if isinstance(value, (bytes, bytearray)):
        return bytes(value), "image/png"
    if hasattr(value, "save"):
        buffer = BytesIO()
        image_format = getattr(value, "format", None) or "PNG"
        value.save(buffer, format=image_format)
        mime = mimetypes.guess_type(f"chart.{image_format.lower()}")[0] or "image/png"
        return buffer.getvalue(), mime
    if isinstance(value, str) and Path(value).is_file():
        return Path(value).read_bytes(), mimetypes.guess_type(value)[0] or "image/png"
    raise ValueError(f"Unsupported image value: {type(value).__name__}")


def load_reasoning_rows(dataset_id: str = DATASET_ID, split: str = "validation") -> list[dict[str, Any]]:
    """Load CharXiv chart rows containing reasoning questions and answers."""
    dataset = load_dataset(dataset_id, split=split)
    required_fields = {"image", "reasoning_q", "reasoning_a"}
    missing_fields = required_fields.difference(dataset.column_names)
    if missing_fields:
        raise ValueError(
            f"{dataset_id!r} split {split!r} is missing required CharXiv columns: "
            f"{', '.join(sorted(missing_fields))}"
        )
    rows = [dict(row) for row in dataset]
    rows = [row for row in rows if row["reasoning_q"] is not None and row["reasoning_a"] is not None]
    if not rows:
        raise ValueError(f"No reasoning question/answer rows found in {dataset_id!r} split {split!r}.")
    return rows


def _prepare_example(row: dict[str, Any], index: int) -> dict[str, Any]:
    image_bytes, mime_type = _image_bytes(row["image"])
    return {
        "example_id": str(row.get("figure_path", index)),
        "question": _text(row["reasoning_q"]),
        "correct_answer": _text(row["reasoning_a"]),
        "image_bytes": image_bytes,
        "image_mime_type": mime_type,
        "image_data_url": f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}",
    }


def _extract_output(response_json: dict[str, Any]) -> tuple[str, str]:
    reasoning: list[str] = []
    messages: list[str] = []
    for item in response_json.get("output", []):
        if item.get("type") == "reasoning" and item.get("content"):
            reasoning.append(str(item["content"]))
        elif item.get("type") == "message" and item.get("content"):
            messages.append(str(item["content"]))
    # Accommodate an OpenAI-compatible response from alternative LM Studio versions.
    if not messages and response_json.get("choices"):
        choice = response_json["choices"][0]
        message = choice.get("message", {})
        messages = [str(message.get("content", ""))]
        reasoning = [str(message.get("reasoning_content", ""))] if message.get("reasoning_content") else reasoning
    return "\n\n".join(reasoning), "\n\n".join(messages) or json.dumps(response_json, ensure_ascii=False)


def run_pipeline(
    *,
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
    n: int = DEFAULT_N,
    seed: int = DEFAULT_SEED,
    dataset_id: str = DATASET_ID,
    split: str = "validation",
    model: str = DEFAULT_MODEL,
    api_url: str = DEFAULT_API_URL,
    timeout: int = 300,
) -> Path:
    """Sample reasoning questions, query LM Studio, and write a JSON result."""
    rows = load_reasoning_rows(dataset_id, split)
    if n < 1 or n > len(rows):
        raise ValueError(f"Requested n={n}, but found {len(rows)} reasoning examples.")
    selected_indices = random.Random(seed).sample(range(len(rows)), n)
    output = Path(output_path)
    if not output.is_absolute():
        output = PROJECT_ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    images_dir = output.parent / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for sample_number, row_index in enumerate(selected_indices, start=1):
        example = _prepare_example(rows[row_index], row_index)
        image_name = Path(example["example_id"]).name
        image_extension = Path(image_name).suffix or mimetypes.guess_extension(example["image_mime_type"]) or ".img"
        image_path = images_dir / f"{sample_number:03d}_{Path(image_name).stem}{image_extension}"
        image_path.write_bytes(example["image_bytes"])
        payload = {
            "model": model,
            "system_prompt": "Answer using only the attached chart.",
            "input": [
                {"type": "text", "content": example["question"]},
                {"type": "image", "data_url": example["image_data_url"]},
            ],
            "temperature": 0,
            "reasoning": "on",
            "store": False,
        }
        response = requests.post(api_url, json=payload, timeout=timeout)
        response.raise_for_status()
        reasoning, answer = _extract_output(response.json())
        results.append({
            "sample_number": sample_number,
            "dataset_index": row_index,
            "example_id": example["example_id"],
            "question": example["question"],
            "correct_answer": example["correct_answer"],
            "model_answer": answer,
            "model_reasoning": reasoning,
            "reasoning_returned": bool(reasoning),
            "image_path": image_path.relative_to(output.parent).as_posix(),
        })
        print(f"[{sample_number}/{n}] completed: {example['example_id']}", flush=True)

    document = {
        "dataset": dataset_id,
        "split": split,
        "sample_size": n,
        "seed": seed,
        "model": model,
        "api_url": api_url,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }
    output.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output.resolve()


def copy_images_for_existing_output(output_path: str | Path = DEFAULT_OUTPUT_PATH) -> Path:
    """Copy charts referenced by an existing results JSON without rerunning LM Studio."""
    output = Path(output_path)
    if not output.is_absolute():
        output = PROJECT_ROOT / output
    document = json.loads(output.read_text(encoding="utf-8"))
    dataset = load_dataset(document["dataset"], split=document["split"])
    images_dir = output.parent / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    for result in document["results"]:
        row_index = result["dataset_index"]
        row = dataset[row_index]
        image_bytes, mime_type = _image_bytes(row["image"])
        image_name = Path(result["example_id"]).name
        image_extension = Path(image_name).suffix or mimetypes.guess_extension(mime_type) or ".img"
        image_path = images_dir / f"{result['sample_number']:03d}_{Path(image_name).stem}{image_extension}"
        image_path.write_bytes(image_bytes)
        result["image_path"] = image_path.relative_to(output.parent).as_posix()

    output.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output.resolve()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=DEFAULT_N, help="Number of reasoning questions to sample (default: 25).")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--split", default="validation")
    parser.add_argument("--dataset", default=DATASET_ID)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument(
        "--copy-images-only",
        action="store_true",
        help="Copy images referenced by an existing output JSON without querying LM Studio.",
    )
    args = parser.parse_args()
    if args.copy_images_only:
        path = copy_images_for_existing_output(args.output)
        print(f"Copied images referenced by {path}")
        return
    path = run_pipeline(
        output_path=args.output, n=args.n, seed=args.seed, dataset_id=args.dataset,
        split=args.split, model=args.model, api_url=args.api_url, timeout=args.timeout,
    )
    print(f"Saved {args.n} results to {path}")


if __name__ == "__main__":
    main()

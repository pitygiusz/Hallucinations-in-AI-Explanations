"""Export the charts referenced by a CharXiv experiment JSON.

The experiment's dataset_index may refer to either the full validation split
or the reasoning-only rows used by the local LM Studio pipeline. Match each
row against example_id before saving, so a dataset reorder cannot silently
attach the wrong chart to an answer.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import mimetypes
import os
import re
from pathlib import Path
from typing import Any

from datasets import load_dataset

from charxiv_pipeline import _image_bytes


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def project_path(value: Path) -> Path:
    value = value.expanduser()
    return value if value.is_absolute() else PROJECT_ROOT / value


def image_extension(mime_type: str, example_id: str) -> str:
    if mime_type == "image/jpeg":
        return ".jpg"
    return mimetypes.guess_extension(mime_type) or Path(example_id).suffix or ".img"


def safe_stem(example_id: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(example_id).stem).strip("_")
    if not stem:
        raise ValueError(f"Cannot make a filename from example_id={example_id!r}")
    return stem


def write_json_atomic(path: Path, document: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def find_raw_index(dataset: Any, filtered_indices: list[int], index: int, example_id: str) -> int:
    candidates = []
    if 0 <= index < len(filtered_indices):
        candidates.append(filtered_indices[index])
    if 0 <= index < len(dataset) and index not in candidates:
        candidates.append(index)
    matches = [candidate for candidate in candidates
               if str(dataset[candidate]["figure_path"]) == example_id]
    if not matches:
        raise ValueError(
            f"No dataset row matches index {index} and figure {example_id!r}. "
            "The dataset may have changed since this experiment was run."
        )
    return matches[0]


def export_images(results_path: Path, output_dir: Path, output_json: Path) -> int:
    if output_json == results_path:
        raise ValueError("The companion JSON must differ from the source results JSON.")
    document = json.loads(results_path.read_text(encoding="utf-8"))
    records = document.get("results")
    if not isinstance(records, list) or not records:
        raise ValueError("The results JSON has no result records.")
    dataset_id = document["dataset"]
    split = document["split"]
    samples: dict[int, tuple[int, str]] = {}
    selected_indices = document.get("selected_indices")
    for record in records:
        sample_number = int(record["sample_number"])
        dataset_index = int(record["dataset_index"])
        example_id = str(record["example_id"])
        if sample_number < 1:
            raise ValueError(f"Invalid sample_number: {sample_number}")
        if selected_indices is not None and (
            sample_number > len(selected_indices)
            or selected_indices[sample_number - 1] != dataset_index
        ):
            raise ValueError(f"Sample {sample_number} disagrees with selected_indices.")
        identity = (dataset_index, example_id)
        if sample_number in samples and samples[sample_number] != identity:
            raise ValueError(f"Sample {sample_number} refers to multiple charts.")
        samples[sample_number] = identity

    dataset = load_dataset(dataset_id, split=split)
    required = {"image", "figure_path", "reasoning_q", "reasoning_a"}
    missing = required.difference(dataset.column_names)
    if missing:
        raise ValueError(f"Dataset is missing columns: {', '.join(sorted(missing))}")
    filtered_indices = [raw_index for raw_index, (question, answer) in enumerate(
        zip(dataset["reasoning_q"], dataset["reasoning_a"]))
        if question is not None and answer is not None]

    output_dir.mkdir(parents=True, exist_ok=True)
    exported: dict[int, tuple[Path, str]] = {}
    for sample_number, (dataset_index, example_id) in sorted(samples.items()):
        raw_index = find_raw_index(dataset, filtered_indices, dataset_index, example_id)
        image_bytes, mime_type = _image_bytes(dataset[raw_index]["image"])
        filename = (f"{sample_number:03d}_idx{dataset_index:04d}_"
                    f"{safe_stem(example_id)}{image_extension(mime_type, example_id)}")
        destination = output_dir / filename
        digest = hashlib.sha256(image_bytes).hexdigest()
        if destination.exists():
            existing_digest = hashlib.sha256(destination.read_bytes()).hexdigest()
            if existing_digest != digest:
                raise FileExistsError(f"Existing image differs from dataset image: {destination}")
        else:
            destination.write_bytes(image_bytes)
        exported[sample_number] = destination, digest
        print(f"{sample_number:03d}: dataset index {dataset_index} -> {destination}")

    updated = copy.deepcopy(document)
    for record in updated["results"]:
        destination, digest = exported[int(record["sample_number"])]
        record["source_image_path"] = record.get("image_path")
        record["image_path"] = Path(os.path.relpath(destination, output_json.parent)).as_posix()
        record["exported_image_sha256"] = digest
    updated["image_export_source"] = Path(os.path.relpath(results_path, output_json.parent)).as_posix()
    output_json.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(output_json, updated)
    print(f"Exported {len(exported)} unique charts. Updated paths: {output_json}")
    return len(exported)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_json", type=Path, help="Experiment result JSON, absolute or relative to the repo root.")
    parser.add_argument("--output-dir", type=Path, help="Default: outputs/images/<results JSON stem>/")
    parser.add_argument("--output-json", type=Path, help="Default: <results JSON stem>_with_images.json")
    args = parser.parse_args()
    results_path = project_path(args.results_json)
    output_dir = project_path(args.output_dir) if args.output_dir else (
        PROJECT_ROOT / "outputs" / "images" / results_path.stem)
    output_json = project_path(args.output_json) if args.output_json else (
        results_path.with_name(results_path.stem + "_with_images.json"))
    export_images(results_path, output_dir, output_json)


if __name__ == "__main__":
    main()

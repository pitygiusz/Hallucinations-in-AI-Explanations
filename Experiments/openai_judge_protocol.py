"""Offline validation policy and chart evidence for the Batch judge.

All acceptance rules are frozen by prepare, before held-out judgments exist.
These defaults are a study design proposal, never a claim of human validation.
"""
from __future__ import annotations

import itertools
import math
from collections import defaultdict
from typing import Any


CHART_TYPES = ["bar", "line", "scatter", "area", "pie", "box", "heatmap",
               "histogram", "other", "unclear"]
PRIMARY_LABEL = "final_explanation_unsupported"
DEFAULT_POLICY = {
    "primary_label": PRIMARY_LABEL,
    "thresholds": {"precision": 0.80, "recall": 0.80, "f1": 0.80},
    "min_validation_charts": 10,
    "min_positive_responses": 10,
    "min_negative_responses": 10,
    "min_judge_coverage": 0.95,
    "min_answer_accuracy": 0.95,
    "min_human_overlap_fraction": 1.0,
    "min_human_kappa": 0.60,
    "min_conditional_charts": 10,
    "fallback": "Use a smaller human-annotated analysis; revise on development data and validate on fresh charts.",
    "numeric_tolerance": {
        "rule": "half_smallest_readable_tick",
        "absolute": 0.0,
        "relative": 0.0,
        "description": "For an approximate visual reading, allow half the smallest readable tick interval in axis space, including log axes. If ticks or resolution do not resolve the value, mark insufficient evidence and request review. Exact printed labels and verified tables use the declared absolute/relative tolerances, not a visual allowance.",
    },
}


def validate_policy(policy: dict[str, Any]) -> None:
    if set(policy) != set(DEFAULT_POLICY) or policy["primary_label"] != PRIMARY_LABEL:
        raise ValueError("Policy must declare all documented fields and the primary final-explanation label.")
    if set(policy["thresholds"]) != {"precision", "recall", "f1"}:
        raise ValueError("Declare precision, recall and F1 thresholds.")
    for value in [*policy["thresholds"].values(), policy["min_judge_coverage"], policy["min_answer_accuracy"],
                  policy["min_human_overlap_fraction"], policy["min_human_kappa"]]:
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("Policy rates must be finite numbers between zero and one.")
    for key in ["min_validation_charts", "min_positive_responses", "min_negative_responses", "min_conditional_charts"]:
        if type(policy[key]) is not int or policy[key] < 2:
            raise ValueError(f"{key} must be an integer of at least two.")
    tolerance = policy["numeric_tolerance"]
    if set(tolerance) != {"rule", "absolute", "relative", "description"} or tolerance["rule"] != "half_smallest_readable_tick":
        raise ValueError("Unknown numerical tolerance policy.")
    for key in ["absolute", "relative"]:
        if type(tolerance[key]) not in (int, float) or not math.isfinite(tolerance[key]) or tolerance[key] < 0:
            raise ValueError("Numerical tolerances must be finite and nonnegative.")
    if not isinstance(tolerance["description"], str) or not tolerance["description"].strip():
        raise ValueError("Describe the tolerance rule.")
    if not isinstance(policy["fallback"], str) or not policy["fallback"].strip():
        raise ValueError("Declare the human-annotation fallback.")


def validate_chart_metadata(entries: Any) -> dict[str, dict[str, Any]]:
    """Metadata is keyed by full chart ID or dataset example_id, never model/strategy."""
    if not isinstance(entries, dict):
        raise ValueError("Chart metadata must be an object keyed by chart_id or example_id.")
    for key, entry in entries.items():
        if not isinstance(entry, dict) or set(entry) - {"chart_types", "human_verified", "verified_table"}:
            raise ValueError(f"Invalid metadata for {key}.")
        types = entry.get("chart_types", [])
        if not isinstance(types, list) or any(t not in CHART_TYPES for t in types) or len(set(types)) != len(types):
            raise ValueError("Chart types must be unique documented labels.")
        if type(entry.get("human_verified", False)) is not bool:
            raise ValueError("human_verified must be Boolean.")
        table = entry.get("verified_table")
        if table is not None:
            if not entry.get("human_verified") or not isinstance(table, dict) or set(table) != {"provenance", "values"}:
                raise ValueError("Source tables require human_verified=true, provenance and values.")
            if not isinstance(table["provenance"], str) or not table["provenance"].strip() or not isinstance(table["values"], list):
                raise ValueError("A verified table needs a provenance description and a list of cells.")
            ids = set()
            for cell in table["values"]:
                if not isinstance(cell, dict) or set(cell) != {"id", "value", "unit"}:
                    raise ValueError("Each table cell needs id, value and unit.")
                if not isinstance(cell["id"], str) or not cell["id"] or cell["id"] in ids or not isinstance(cell["unit"], str):
                    raise ValueError("Table cell IDs must be unique nonempty strings; units must be strings.")
                if type(cell["value"]) not in (int, float) or not math.isfinite(cell["value"]):
                    raise ValueError("Table values must be finite numbers.")
                ids.add(cell["id"])
    return entries


def numerical_checks(claims: list[dict[str, Any]], metadata: dict[str, Any], tolerance: dict[str, Any]) -> list[dict[str, Any]]:
    cells = {c["id"]: c for c in metadata.get("verified_table", {}).get("values", [])}
    checks = []
    for claim in claims:
        reference = claim.get("numeric_reference", "")
        if not reference:
            continue
        if reference not in cells or claim.get("numeric_value") is None:
            raise ValueError("A numerical claim references an unavailable verified cell or has no numeric value.")
        cell = cells[reference]
        value = claim["numeric_value"]
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("Numerical claim values must be finite numbers.")
        allowed = max(tolerance["absolute"], tolerance["relative"] * abs(cell["value"]))
        checks.append({"quote": claim["quote"], "reference": reference, "claimed": value,
                       "reference_value": cell["value"], "unit": cell["unit"], "tolerance": allowed,
                       "within_tolerance": abs(value - cell["value"]) <= allowed})
    return checks


def validation_decision(manifest: dict[str, Any], rows: list[dict[str, Any]],
                        human_entries: list[dict[str, Any]], agreement_fn: Any,
                        iterations: int, seed: int) -> dict[str, Any]:
    """Fail closed on inadequate labels, chart counts, overlap or judge coverage.

    agreement_fn is the chart-clustered CI implementation from the CLI module.
    Adjudication never substitutes for original independent human annotations.
    """
    policy = manifest["policy"]
    validate_policy(policy)
    by_id = {r["response_id"]: r for r in rows}
    humans: dict[str, dict[str, Any]] = defaultdict(dict)
    for entry in human_entries:
        rid, annotator = entry.get("response_id"), entry.get("annotator")
        if rid not in by_id or not annotator or annotator == "REPLACE_ME" or annotator in humans[rid]:
            raise ValueError("Unknown response, duplicate label or missing annotator in validation labels.")
        for key in [PRIMARY_LABEL, "answer_correct"]:
            value = entry.get(key)
            if value is not None and type(value) is not bool:
                raise ValueError("Validation labels must be true, false or null.")
        humans[rid][annotator] = entry
    eligible, pairs, answer_pairs, overlap_pairs = [], [], [], defaultdict(list)
    positive, negative, overlap = 0, 0, 0
    for row in rows:
        rid = row["response_id"]
        human = humans[rid].get("adjudicated", {}).get(PRIMARY_LABEL)
        independent = {k: v[PRIMARY_LABEL] for k, v in humans[rid].items()
                       if k != "adjudicated" and v.get(PRIMARY_LABEL) is not None}
        human_answer = humans[rid].get("adjudicated", {}).get("answer_correct")
        if human_answer is not None and row.get("answer_correct") is not None:
            answer_pairs.append((row["chart_id"], human_answer, row["answer_correct"]))
        if human is None:
            continue
        eligible.append(row)
        positive += human is True
        negative += human is False
        overlap += len(independent) >= 2
        for left, right in itertools.combinations(sorted(independent), 2):
            overlap_pairs[(left, right)].append((row["chart_id"], independent[left], independent[right]))
        prediction = row["final_explanation_metrics"]["unsupported"]
        if prediction is not None:
            pairs.append((row["chart_id"], human, bool(prediction)))
    stats = agreement_fn(pairs, iterations, seed)
    answer_stats = agreement_fn(answer_pairs, iterations, seed)
    human_stats = {f"{a} vs {b}": agreement_fn(p, iterations, seed) for (a, b), p in overlap_pairs.items()}
    coverage = len(pairs) / len(rows) if rows else 0.0
    overlap_fraction = overlap / len(eligible) if eligible else 0.0
    reasons = []
    if manifest.get("stage") != "validation":
        reasons.append("not_a_held_out_validation_run")
    if min(stats["charts"], answer_stats["charts"]) < policy["min_validation_charts"]:
        reasons.append("too_few_resolved_validation_charts")
    if positive < policy["min_positive_responses"] or negative < policy["min_negative_responses"]:
        reasons.append("insufficient_positive_or_negative_examples")
    if stats["tp"] + stats["fn"] < policy["min_positive_responses"] or stats["tn"] + stats["fp"] < policy["min_negative_responses"]:
        reasons.append("insufficient_resolved_positive_or_negative_examples")
    if answer_stats["tp"] + answer_stats["fn"] < policy["min_positive_responses"] or answer_stats["tn"] + answer_stats["fp"] < policy["min_negative_responses"]:
        reasons.append("insufficient_resolved_correct_or_incorrect_answer_examples")
    if coverage < policy["min_judge_coverage"]:
        reasons.append("insufficient_human_and_judge_coverage")
    if not rows or len(answer_pairs) / len(rows) < policy["min_judge_coverage"]:
        reasons.append("insufficient_answer_validation_coverage")
    if answer_stats["accuracy"] is None or answer_stats["accuracy"] < policy["min_answer_accuracy"]:
        reasons.append("answer_judge_accuracy_below_threshold_or_undefined")
    if overlap_fraction < policy["min_human_overlap_fraction"]:
        reasons.append("insufficient_independent_human_overlap")
    if not human_stats or any(s["cohen_kappa"] is None or s["cohen_kappa"] < policy["min_human_kappa"] for s in human_stats.values()):
        reasons.append("human_agreement_below_threshold_or_undefined")
    for metric, threshold in policy["thresholds"].items():
        if stats[metric] is None or stats[metric] < threshold:
            reasons.append(f"judge_{metric}_below_threshold_or_undefined")
    return {"status": "passed" if not reasons else "not_validated", "reasons": reasons,
            "label": PRIMARY_LABEL, "policy": policy, "judge_vs_adjudicated": stats,
            "answer_judge_vs_adjudicated": answer_stats,
            "independent_human_agreement": human_stats, "positive_responses": positive,
            "negative_responses": negative, "human_overlap_fraction": overlap_fraction,
            "coverage_of_all_validation_responses": coverage,
            "fallback": policy["fallback"],
            "scope": "Answer correctness and final-explanation unsupported-or-contradicted response labels; claim segmentation, other categories and reasoning require separate validation."}

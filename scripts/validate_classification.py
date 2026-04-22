#!/usr/bin/env python3
"""Validate sidecar or enriched classification output."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def load_rows(path: Path, source_type: str) -> list[dict[str, Any]]:
    if source_type == "csv":
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    if source_type == "jsonl":
        with path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]
    if source_type == "json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise SystemExit("JSON validation input must be an array")
        return payload
    raise ValueError(f"unsupported source_type: {source_type}")


def parse_jsonish(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return fallback


def get_value(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in row:
            return row[name]
    return None


def validate(rows: list[dict[str, Any]], id_column: str | None, low_confidence: float, sample_size: int) -> dict[str, Any]:
    review_status = Counter()
    rule_counts = Counter()
    axis_fill = Counter()
    axis_empty = Counter()
    axis_value_counts: dict[str, Counter[str]] = defaultdict(Counter)
    conflict_count = 0
    missing_required_axis_counts = Counter()
    low_confidence_samples = []
    conflict_samples = []
    unmatched_samples = []
    missing_required_samples = []

    for row in rows:
        axis_values = parse_jsonish(get_value(row, "classified_axis_values", "axis_values"), {})
        rule_ids = parse_jsonish(get_value(row, "classified_rule_ids", "rule_ids"), [])
        conflicts = parse_jsonish(get_value(row, "classified_conflicts", "conflicts"), [])
        missing_required_axes = parse_jsonish(
            get_value(row, "classified_missing_required_axes", "missing_required_axes"),
            [],
        )
        status = get_value(row, "classified_review_status", "review_status") or "unknown"
        confidence_raw = get_value(row, "classified_confidence", "confidence") or 0
        try:
            confidence = float(confidence_raw)
        except (TypeError, ValueError):
            confidence = 0.0

        review_status[str(status)] += 1
        for rule_id in rule_ids if isinstance(rule_ids, list) else []:
            rule_counts[str(rule_id)] += 1

        if isinstance(axis_values, dict):
            for axis, value in axis_values.items():
                is_empty = value in ("", None, []) or value == {}
                if is_empty:
                    axis_empty[axis] += 1
                else:
                    axis_fill[axis] += 1
                    values = value if isinstance(value, list) else [value]
                    for item in values:
                        axis_value_counts[axis][str(item)] += 1
        if conflicts:
            conflict_count += 1
            if len(conflict_samples) < sample_size:
                conflict_samples.append(sample(row, id_column))
        for axis in missing_required_axes if isinstance(missing_required_axes, list) else []:
            missing_required_axis_counts[str(axis)] += 1
        if missing_required_axes and len(missing_required_samples) < sample_size:
            missing_required_samples.append(sample(row, id_column))
        if confidence < low_confidence:
            if len(low_confidence_samples) < sample_size:
                low_confidence_samples.append(sample(row, id_column))
        if not rule_ids:
            if len(unmatched_samples) < sample_size:
                unmatched_samples.append(sample(row, id_column))

    axis_summary = {}
    total = len(rows)
    for axis in sorted(set(axis_fill) | set(axis_empty)):
        filled = axis_fill[axis]
        axis_summary[axis] = {
            "filled": filled,
            "empty": axis_empty[axis],
            "fill_rate": round(filled / total, 4) if total else None,
            "top_values": axis_value_counts[axis].most_common(20),
        }

    return {
        "row_count": total,
        "review_status_counts": review_status,
        "axis_summary": axis_summary,
        "rule_match_counts": rule_counts.most_common(),
        "conflict_count": conflict_count,
        "missing_required_axis_counts": missing_required_axis_counts.most_common(),
        "low_confidence_threshold": low_confidence,
        "low_confidence_samples": low_confidence_samples,
        "conflict_samples": conflict_samples,
        "missing_required_samples": missing_required_samples,
        "unmatched_samples": unmatched_samples,
    }


def sample(row: dict[str, Any], id_column: str | None) -> dict[str, Any]:
    if id_column and id_column in row:
        return {id_column: row[id_column]}
    return {key: row[key] for key in list(row)[:5]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-type", choices=["csv", "json", "jsonl"], required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--id-column")
    parser.add_argument("--low-confidence", type=float, default=0.6)
    parser.add_argument("--sample-size", type=int, default=20)
    parser.add_argument("--output", default="-")
    args = parser.parse_args()

    rows = load_rows(Path(args.source), args.source_type)
    report = validate(rows, args.id_column, args.low_confidence, args.sample_size)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output == "-":
        print(payload)
    else:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

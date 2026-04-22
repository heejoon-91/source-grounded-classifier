#!/usr/bin/env python3
"""Apply rule-based taxonomy classifications to CSV, JSON, or JSONL rows."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any


def flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            output.update(flatten(child, child_prefix))
        return output
    return {prefix: value}


def load_rows(path: Path, source_type: str) -> list[dict[str, Any]]:
    if source_type == "csv":
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    if source_type == "jsonl":
        with path.open(encoding="utf-8") as handle:
            return [flatten(json.loads(line)) for line in handle if line.strip()]
    if source_type == "json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise SystemExit("JSON source must be an array of objects for rule application")
        return [flatten(row) for row in payload]
    raise ValueError(f"unsupported source_type: {source_type}")


def cell_text(row: dict[str, Any], columns: list[str]) -> str:
    parts = []
    for column in columns:
        value = row.get(column)
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            parts.append(json.dumps(value, ensure_ascii=False, sort_keys=True))
        else:
            parts.append(str(value))
    return " ".join(parts).casefold()


def normalize_scalar(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().casefold()


def row_values(row: dict[str, Any], column: str) -> list[str]:
    value = row.get(column)
    if value is None:
        return []
    if isinstance(value, list):
        return [normalize_scalar(item) for item in value]
    if isinstance(value, dict):
        return [normalize_scalar(json.dumps(value, ensure_ascii=False, sort_keys=True))]
    text = str(value).strip()
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [normalize_scalar(item) for item in parsed]
        except json.JSONDecodeError:
            pass
    return [normalize_scalar(text)]


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def parse_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def exact_values_match(row: dict[str, Any], exact_values: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    matched = []
    for column, expected in exact_values.items():
        actual_values = row_values(row, column)
        expected_values = [normalize_scalar(item) for item in as_list(expected)]
        if not actual_values or not any(actual in expected_values for actual in actual_values):
            return False, []
        matched.append({"type": "exact_value", "column": column, "value": expected})
    return True, matched


def numeric_ranges_match(row: dict[str, Any], numeric_ranges: dict[str, dict[str, Any]]) -> tuple[bool, list[dict[str, Any]]]:
    matched = []
    for column, range_rule in numeric_ranges.items():
        value = parse_number(row.get(column))
        if value is None:
            return False, []
        minimum = range_rule.get("min")
        maximum = range_rule.get("max")
        if minimum is not None and value < float(minimum):
            return False, []
        if maximum is not None and value > float(maximum):
            return False, []
        matched.append({"type": "numeric_range", "column": column, "value": value, "range": range_rule})
    return True, matched


def criteria_matches(row: dict[str, Any], criteria: dict[str, Any], default_columns: list[str]) -> tuple[bool, list[dict[str, Any]]]:
    evidence: list[dict[str, Any]] = []
    positive_groups = 0

    columns = criteria.get("source_columns") or default_columns
    text = cell_text(row, columns)

    negative_keywords = criteria.get("negative_keywords") or []
    for keyword in negative_keywords:
        if str(keyword).casefold() in text:
            return False, []

    if criteria.get("always") is True:
        positive_groups += 1
        evidence.append({"type": "always", "value": True})

    keywords = criteria.get("keywords") or []
    if keywords:
        positive_groups += 1
        keyword_matches = [
            {"type": "keyword", "value": keyword}
            for keyword in keywords
            if str(keyword).casefold() in text
        ]
        if not keyword_matches:
            return False, []
        evidence.extend(keyword_matches)

    regexes = criteria.get("regex") or []
    if regexes:
        positive_groups += 1
        regex_matches = [
            {"type": "regex", "value": pattern}
            for pattern in regexes
            if re.search(pattern, text, flags=re.IGNORECASE)
        ]
        if not regex_matches:
            return False, []
        evidence.extend(regex_matches)

    exact_values = criteria.get("exact_values") or {}
    if exact_values:
        positive_groups += 1
        matched, exact_evidence = exact_values_match(row, exact_values)
        if not matched:
            return False, []
        evidence.extend(exact_evidence)

    numeric_ranges = criteria.get("numeric_ranges") or {}
    if numeric_ranges:
        positive_groups += 1
        matched, numeric_evidence = numeric_ranges_match(row, numeric_ranges)
        if not matched:
            return False, []
        evidence.extend(numeric_evidence)

    all_of = criteria.get("all_of") or []
    if all_of:
        positive_groups += 1
        for child in all_of:
            matched, child_evidence = criteria_matches(row, child, columns)
            if not matched:
                return False, []
            evidence.extend({"type": "all_of", **item} for item in child_evidence)

    any_of = criteria.get("any_of") or []
    if any_of:
        positive_groups += 1
        child_matches = []
        for child in any_of:
            matched, child_evidence = criteria_matches(row, child, columns)
            if matched:
                child_matches.extend({"type": "any_of", **item} for item in child_evidence)
        if not child_matches:
            return False, []
        evidence.extend(child_matches)

    none_of = criteria.get("none_of") or []
    for child in none_of:
        matched, _ = criteria_matches(row, child, columns)
        if matched:
            return False, []

    return positive_groups > 0, evidence


def classify_row(row: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    default_columns = rules.get("text_columns") or list(row.keys())
    auto_accept_threshold = float(rules.get("auto_accept_threshold", 0.6))
    axis_values: dict[str, Any] = {}
    evidence: dict[str, list[dict[str, Any]]] = {}
    rule_ids: list[str] = []
    conflicts: list[str] = []
    missing_required_axes: list[str] = []

    for axis_name, axis in (rules.get("axes") or {}).items():
        multi_value = bool(axis.get("multi_value"))
        matches = []
        for value_name, value_rule in (axis.get("values") or {}).items():
            matched, matched_terms = criteria_matches(row, value_rule, default_columns)
            if matched_terms:
                matches.append(
                    {
                        "value": value_name,
                        "confidence": float(value_rule.get("confidence", 0.7)),
                        "priority": int(value_rule.get("priority", 0)),
                        "rule_id": value_rule.get("rule_id", f"{axis_name}.{value_name}"),
                        "matched": matched_terms,
                    }
                )

        if not matches:
            axis_values[axis_name] = [] if multi_value else ""
            if axis.get("required") or axis.get("review_if_empty"):
                missing_required_axes.append(axis_name)
            continue

        matches.sort(key=lambda item: (item["confidence"], item["priority"]), reverse=True)
        if multi_value:
            max_values = axis.get("max_values")
            if max_values is not None:
                matches = matches[: int(max_values)]
            axis_values[axis_name] = [item["value"] for item in matches]
            evidence[axis_name] = matches
            rule_ids.extend(item["rule_id"] for item in matches)
        else:
            best = matches[0]
            tied = [
                item
                for item in matches
                if abs(item["confidence"] - best["confidence"]) < 0.05
                and item["priority"] == best["priority"]
            ]
            if len(tied) > 1:
                conflicts.append(axis_name)
            axis_values[axis_name] = best["value"]
            evidence[axis_name] = [best]
            rule_ids.append(best["rule_id"])

    confidence_values = [
        item["confidence"]
        for axis_matches in evidence.values()
        for item in axis_matches
    ]
    confidence = round(sum(confidence_values) / len(confidence_values), 4) if confidence_values else 0.0
    review_status = (
        "needs_review"
        if conflicts or missing_required_axes or confidence < auto_accept_threshold or not rule_ids
        else "auto_accepted"
    )

    return {
        "axis_values": axis_values,
        "confidence": confidence,
        "evidence": evidence,
        "rule_ids": sorted(set(rule_ids)),
        "review_status": review_status,
        "conflicts": conflicts,
        "missing_required_axes": missing_required_axes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-type", choices=["csv", "json", "jsonl"], required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--rules", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    rules = json.loads(Path(args.rules).read_text(encoding="utf-8"))
    rows = load_rows(Path(args.source), args.source_type)
    id_column = rules.get("id_column")
    if not id_column:
        raise SystemExit("rules.json must include id_column")

    output_fields = [
        id_column,
        "taxonomy_version",
        "axis_values",
        "confidence",
        "evidence",
        "rule_ids",
        "review_status",
        "conflicts",
        "missing_required_axes",
    ]
    with Path(args.output).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=output_fields)
        writer.writeheader()
        for row in rows:
            result = classify_row(row, rules)
            writer.writerow(
                {
                    id_column: row.get(id_column, ""),
                    "taxonomy_version": rules.get("version", ""),
                    "axis_values": json.dumps(result["axis_values"], ensure_ascii=False, sort_keys=True),
                    "confidence": result["confidence"],
                    "evidence": json.dumps(result["evidence"], ensure_ascii=False, sort_keys=True),
                    "rule_ids": json.dumps(result["rule_ids"], ensure_ascii=False),
                    "review_status": result["review_status"],
                    "conflicts": json.dumps(result["conflicts"], ensure_ascii=False),
                    "missing_required_axes": json.dumps(result["missing_required_axes"], ensure_ascii=False),
                }
            )


if __name__ == "__main__":
    main()

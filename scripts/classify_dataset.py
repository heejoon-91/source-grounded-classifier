#!/usr/bin/env python3
"""Return a new dataset with rule-based taxonomy columns appended.

This script never edits the input file in place. The output path must be
different from the source path.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from apply_rules import classify_row, load_rows


def infer_output_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix in {".jsonl", ".ndjson"}:
        return "jsonl"
    if suffix == ".json":
        return "json"
    raise SystemExit("--output-type is required when output extension is not csv/json/jsonl")


def serialize_csv_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return "" if value is None else str(value)


def enriched_row(row: dict[str, Any], rules: dict[str, Any], prefix: str) -> dict[str, Any]:
    result = classify_row(row, rules)
    axis_values = result["axis_values"]
    output = dict(row)
    output[f"{prefix}taxonomy_version"] = rules.get("version", "")
    output[f"{prefix}axis_values"] = axis_values
    output[f"{prefix}confidence"] = result["confidence"]
    output[f"{prefix}evidence"] = result["evidence"]
    output[f"{prefix}rule_ids"] = result["rule_ids"]
    output[f"{prefix}review_status"] = result["review_status"]
    output[f"{prefix}conflicts"] = result["conflicts"]
    output[f"{prefix}missing_required_axes"] = result["missing_required_axes"]
    for axis_name, value in axis_values.items():
        output[f"{prefix}{axis_name}"] = value
    return output


def write_csv(rows: list[dict[str, Any]], output: Path) -> None:
    fields: list[str] = []
    seen = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: serialize_csv_value(row.get(key)) for key in fields})


def write_jsonl(rows: list[dict[str, Any]], output: Path) -> None:
    with output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_json(rows: list[dict[str, Any]], output: Path) -> None:
    output.write_text(json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-type", choices=["csv", "json", "jsonl"], required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--rules", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--output-type", choices=["csv", "json", "jsonl"])
    parser.add_argument("--column-prefix", default="classified_")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    source = Path(args.source).resolve()
    output = Path(args.output).resolve()
    if source == output:
        raise SystemExit("Refusing to write output over the source file")
    if output.exists() and not args.overwrite:
        raise SystemExit(f"Output already exists: {output}. Use --overwrite to replace it.")

    rules = json.loads(Path(args.rules).read_text(encoding="utf-8"))
    rows = load_rows(source, args.source_type)
    enriched = [enriched_row(row, rules, args.column_prefix) for row in rows]

    output_type = args.output_type or infer_output_type(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output_type == "csv":
        write_csv(enriched, output)
    elif output_type == "jsonl":
        write_jsonl(enriched, output)
    else:
        write_json(enriched, output)

    print(f"wrote {len(enriched)} classified rows to {output}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Profile CSV, JSON, JSONL, or PostgreSQL table data for taxonomy design."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import decimal
import json
import math
from collections import Counter, defaultdict
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


def truncate_text(value: str, max_chars: int) -> str:
    if max_chars <= 0 or len(value) <= max_chars:
        return value
    return value[:max_chars] + "...[truncated]"


def normalize_cell(value: Any, max_chars: int = 300) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return truncate_text(json.dumps(value, ensure_ascii=False, sort_keys=True), max_chars)
    return truncate_text(str(value), max_chars)


def to_jsonable(value: Any, max_chars: int = 300) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return truncate_text(value, max_chars) if isinstance(value, str) else value
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, (dt.date, dt.datetime, dt.time)):
        return value.isoformat()
    if isinstance(value, list):
        converted = [to_jsonable(item, max_chars) for item in value]
        text = json.dumps(converted, ensure_ascii=False, sort_keys=True)
        if len(text) > max_chars:
            return truncate_text(text, max_chars)
        return converted
    if isinstance(value, dict):
        converted = {str(key): to_jsonable(item, max_chars) for key, item in value.items()}
        text = json.dumps(converted, ensure_ascii=False, sort_keys=True)
        if len(text) > max_chars:
            return truncate_text(text, max_chars)
        return converted
    return truncate_text(str(value), max_chars)


def column_is_vector_like(column: str) -> bool:
    lower = column.lower()
    return "embedding" in lower or "vector" in lower


def load_file(path: Path, source_type: str) -> list[dict[str, Any]]:
    if source_type == "csv":
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    if source_type == "jsonl":
        rows = []
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    rows.append(flatten(json.loads(line)))
        return rows
    if source_type == "json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [flatten(row) if isinstance(row, dict) else {"value": row} for row in payload]
        if isinstance(payload, dict):
            for value in payload.values():
                if isinstance(value, list):
                    return [flatten(row) if isinstance(row, dict) else {"value": row} for row in value]
            return [flatten(payload)]
        return [{"value": payload}]
    raise ValueError(f"unsupported source_type: {source_type}")


def load_postgres(dsn: str, table: str, limit: int | None) -> list[dict[str, Any]]:
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError as exc:
        raise SystemExit("psycopg2 is required for postgres profiling") from exc

    query = f"select * from {table}"
    if limit:
        query += " limit %s"
    with psycopg2.connect(dsn) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(query, [limit] if limit else None)
            return [dict(row) for row in cursor.fetchall()]


def profile_rows(
    rows: list[dict[str, Any]],
    top_n: int,
    sample_size: int,
    max_cell_chars: int,
    redact_columns: set[str],
    include_samples: bool,
) -> dict[str, Any]:
    columns = sorted({key for row in rows for key in row})
    total = len(rows)
    stats: dict[str, Any] = {}

    for column in columns:
        null_count = 0
        values: Counter[str] = Counter()
        examples = []
        for row in rows:
            raw = row.get(column)
            value = normalize_cell(raw, max_cell_chars).strip()
            if value == "":
                null_count += 1
                continue
            if column.casefold() in redact_columns:
                pass
            elif not column_is_vector_like(column):
                values[value] += 1
            if len(examples) < sample_size and column.casefold() not in redact_columns:
                examples.append(value)
            elif len(examples) < sample_size and column.casefold() in redact_columns:
                examples.append("<REDACTED>")
        stats[column] = {
            "null_count": null_count,
            "null_rate": None if total == 0 else round(null_count / total, 4),
            "distinct_count": None if column.casefold() in redact_columns else len(values),
            "top_values": [] if column_is_vector_like(column) or column.casefold() in redact_columns else values.most_common(top_n),
            "examples": examples,
            "category_like_score": category_like_score(column, total, null_count, len(values)),
        }

    return {
        "row_count": total,
        "columns": columns,
        "column_stats": stats,
        "sample_rows": [
            redacted_jsonable_row(row, max_cell_chars, redact_columns)
            for row in rows[:sample_size]
        ] if include_samples else [],
    }


def redacted_jsonable_row(row: dict[str, Any], max_chars: int, redact_columns: set[str]) -> dict[str, Any]:
    return {
        key: "<REDACTED>" if key.casefold() in redact_columns else to_jsonable(value, max_chars)
        for key, value in row.items()
    }


def category_like_score(column: str, total: int, null_count: int, distinct_count: int) -> float:
    name = column.lower()
    name_score = 0.0
    for token in ("category", "type", "tag", "label", "class", "segment", "status", "group"):
        if token in name:
            name_score += 0.35
    if total <= 0:
        return round(min(name_score, 1.0), 3)
    coverage = 1.0 - (null_count / total)
    cardinality_ratio = distinct_count / max(total, 1)
    cardinality_score = 0.0
    if distinct_count > 1:
        cardinality_score = 0.25
    if 0.001 <= cardinality_ratio <= 0.2:
        cardinality_score += 0.25
    if math.isclose(cardinality_ratio, 1.0):
        cardinality_score -= 0.25
    return round(max(0.0, min(1.0, name_score + 0.25 * coverage + cardinality_score)), 3)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-type", choices=["csv", "json", "jsonl", "postgres_table"], required=True)
    parser.add_argument("--source", help="file path for csv/json/jsonl")
    parser.add_argument("--dsn", help="PostgreSQL DSN for postgres_table")
    parser.add_argument("--table", help="PostgreSQL table name for postgres_table")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--sample-size", type=int, default=10)
    parser.add_argument("--max-cell-chars", type=int, default=300)
    parser.add_argument("--redact-columns", default="", help="Comma-separated columns to redact in examples and samples")
    parser.add_argument("--no-samples", action="store_true", help="Do not include sample rows in the profile output")
    parser.add_argument("--output", default="-")
    args = parser.parse_args()

    if args.source_type == "postgres_table":
        if not args.dsn or not args.table:
            raise SystemExit("--dsn and --table are required for postgres_table")
        rows = load_postgres(args.dsn, args.table, args.limit)
    else:
        if not args.source:
            raise SystemExit("--source is required for file sources")
        rows = load_file(Path(args.source), args.source_type)
        if args.limit:
            rows = rows[: args.limit]

    redact_columns = {column.strip().casefold() for column in args.redact_columns.split(",") if column.strip()}
    result = profile_rows(
        rows,
        args.top_n,
        args.sample_size,
        args.max_cell_chars,
        redact_columns,
        include_samples=not args.no_samples,
    )
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output == "-":
        print(payload)
    else:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Load classification output into a PostgreSQL staging table.

This script creates or replaces only the staging table named by --table. It
does not update the source data table.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def parse_jsonish(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return fallback


def load_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def get_value(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in row:
            return row[name]
    return None


def quote_ident(identifier: str) -> str:
    parts = identifier.split(".")
    for part in parts:
        if not part.replace("_", "").isalnum() or part[0].isdigit():
            raise SystemExit(f"Unsafe SQL identifier: {identifier}")
    return ".".join('"' + part.replace('"', '""') + '"' for part in parts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--source", required=True, help="classification CSV from apply_rules.py or classify_dataset.py")
    parser.add_argument("--table", default="classification_staging")
    parser.add_argument("--id-column", required=True)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    if args.table.lower() in {"product", "users", "orders"}:
        raise SystemExit("Refusing to write to a likely source table. Use a staging table name.")
    table_name = quote_ident(args.table)

    try:
        import psycopg2
        import psycopg2.extras
    except ImportError as exc:
        raise SystemExit("psycopg2 is required for PostgreSQL staging") from exc

    rows = load_csv(Path(args.source))
    ddl = f"""
    create table if not exists {table_name} (
        source_row_id text primary key,
        taxonomy_version text,
        axis_values jsonb not null default '{{}}'::jsonb,
        confidence numeric,
        evidence jsonb not null default '{{}}'::jsonb,
        rule_ids text[] not null default '{{}}'::text[],
        review_status text not null,
        conflicts text[] not null default '{{}}'::text[],
        missing_required_axes text[] not null default '{{}}'::text[],
        classified_at timestamptz not null default now()
    )
    """

    with psycopg2.connect(args.dsn) as conn:
        with conn.cursor() as cursor:
            if args.replace:
                cursor.execute(f"drop table if exists {table_name}")
            cursor.execute(ddl)
            cursor.execute(
                f"alter table {table_name} "
                "add column if not exists missing_required_axes text[] not null default '{}'::text[]"
            )
            for row in rows:
                source_row_id = row.get(args.id_column)
                if source_row_id in (None, ""):
                    continue
                axis_values = parse_jsonish(get_value(row, "classified_axis_values", "axis_values"), {})
                evidence = parse_jsonish(get_value(row, "classified_evidence", "evidence"), {})
                rule_ids = parse_jsonish(get_value(row, "classified_rule_ids", "rule_ids"), [])
                conflicts = parse_jsonish(get_value(row, "classified_conflicts", "conflicts"), [])
                missing_required_axes = parse_jsonish(
                    get_value(row, "classified_missing_required_axes", "missing_required_axes"),
                    [],
                )
                cursor.execute(
                    f"""
                    insert into {table_name}
                    (source_row_id, taxonomy_version, axis_values, confidence, evidence, rule_ids, review_status, conflicts, missing_required_axes)
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    on conflict (source_row_id) do update set
                      taxonomy_version = excluded.taxonomy_version,
                      axis_values = excluded.axis_values,
                      confidence = excluded.confidence,
                      evidence = excluded.evidence,
                      rule_ids = excluded.rule_ids,
                      review_status = excluded.review_status,
                      conflicts = excluded.conflicts,
                      missing_required_axes = excluded.missing_required_axes,
                      classified_at = now()
                    """,
                    (
                        source_row_id,
                        get_value(row, "classified_taxonomy_version", "taxonomy_version"),
                        json.dumps(axis_values, ensure_ascii=False),
                        get_value(row, "classified_confidence", "confidence") or None,
                        json.dumps(evidence, ensure_ascii=False),
                        rule_ids,
                        get_value(row, "classified_review_status", "review_status") or "needs_review",
                        conflicts,
                        missing_required_axes,
                    ),
                )
    print(f"loaded {len(rows)} classification rows into staging table {args.table}")


if __name__ == "__main__":
    main()

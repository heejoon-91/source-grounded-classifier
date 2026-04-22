#!/usr/bin/env python3
"""Create a derived output shaped by rule-defined classification columns.

This script does not mutate the source data. It keeps only a minimal set of
identity/display columns, expands rule axes into real columns, and adds audit
columns for review and traceability. When rules declare
taxonomy_design.strategy=representative_plus_attributes, it also validates that
the output has one single-value representative axis plus secondary/attribute
axes before writing anything.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from apply_rules import classify_row, load_rows


DEFAULT_IDENTITY_CANDIDATES = [
    "goods_name",
    "name",
    "title",
    "label",
    "subject",
]


def parse_csv_list(value: str | None) -> list[str] | None:
    if value is None:
        return None
    if value.strip() == "":
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


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


def quote_ident(identifier: str) -> str:
    parts = identifier.split(".")
    for part in parts:
        if not part or not part.replace("_", "").isalnum() or part[0].isdigit():
            raise SystemExit(f"Unsafe SQL identifier: {identifier}")
    return ".".join('"' + part.replace('"', '""') + '"' for part in parts)


def axis_names(rules: dict[str, Any]) -> list[str]:
    return list((rules.get("axes") or {}).keys())


def axis_is_multi(rules: dict[str, Any], axis_name: str) -> bool:
    return bool((rules.get("axes") or {}).get(axis_name, {}).get("multi_value"))


def validate_design_contract(rules: dict[str, Any]) -> None:
    """Fail fast when a declared taxonomy design contract is structurally invalid."""
    contract = rules.get("taxonomy_design") or {}
    if contract.get("strategy") != "representative_plus_attributes":
        return

    axes = rules.get("axes") or {}
    representative_axis = str(contract.get("representative_axis") or "")
    if not representative_axis or representative_axis.startswith("REPLACE_WITH"):
        raise SystemExit("taxonomy_design.representative_axis must name the single-value primary axis")
    if representative_axis not in axes:
        raise SystemExit(f"taxonomy_design.representative_axis is not defined in axes: {representative_axis}")

    primary_axis = axes[representative_axis]
    if primary_axis.get("multi_value"):
        raise SystemExit(f"Representative axis must be single-value: {representative_axis}")
    if not (primary_axis.get("required") or primary_axis.get("review_if_empty")):
        raise SystemExit(f"Representative axis must be required or review_if_empty: {representative_axis}")

    for axis_name in contract.get("secondary_axes") or []:
        if axis_name not in axes:
            raise SystemExit(f"taxonomy_design.secondary_axes contains undefined axis: {axis_name}")
        if axes[axis_name].get("multi_value"):
            raise SystemExit(f"Secondary axis should be single-value; use attribute_axes for multi-value tags: {axis_name}")

    for axis_name in contract.get("attribute_axes") or []:
        if axis_name not in axes:
            raise SystemExit(f"taxonomy_design.attribute_axes contains undefined axis: {axis_name}")
        if not axes[axis_name].get("multi_value"):
            raise SystemExit(f"Attribute axis should be multi-value or moved out of attribute_axes: {axis_name}")


def default_identity_columns(rows: list[dict[str, Any]], rules: dict[str, Any]) -> list[str]:
    configured = (rules.get("derived_output") or {}).get("identity_columns")
    if configured is not None:
        return [str(column) for column in configured]
    if not rows:
        return []
    first_row = rows[0]
    id_column = rules.get("id_column")
    for candidate in DEFAULT_IDENTITY_CANDIDATES:
        if candidate in first_row and candidate != id_column:
            return [candidate]
    return []


def build_schema(
    rows: list[dict[str, Any]],
    rules: dict[str, Any],
    identity_columns: list[str] | None,
    include_axis_values: bool,
) -> dict[str, Any]:
    id_column = rules.get("id_column")
    if not id_column:
        raise SystemExit("rules.json must include id_column")

    selected_identity_columns = identity_columns
    if selected_identity_columns is None:
        selected_identity_columns = default_identity_columns(rows, rules)
    selected_identity_columns = [column for column in selected_identity_columns if column != id_column]

    axes = axis_names(rules)
    overlap = sorted(set(selected_identity_columns) & set(axes))
    if overlap:
        raise SystemExit(f"Identity columns overlap derived axis columns: {', '.join(overlap)}")

    audit_columns = [
        "taxonomy_version",
        "confidence",
        "review_status",
        "missing_required_axes",
        "rule_ids",
        "evidence",
        "classified_at",
    ]
    if include_axis_values:
        audit_columns.insert(3, "axis_values")

    return {
        "taxonomy_version": rules.get("version", ""),
        "id_column": id_column,
        "identity_columns": ["source_row_id", *selected_identity_columns],
        "derived_columns": [
            {
                "name": axis_name,
                "role": str((rules.get("axes") or {}).get(axis_name, {}).get("role", "")),
                "multi_value": axis_is_multi(rules, axis_name),
                "required": bool((rules.get("axes") or {}).get(axis_name, {}).get("required")),
                "review_if_empty": bool((rules.get("axes") or {}).get(axis_name, {}).get("review_if_empty")),
            }
            for axis_name in axes
        ],
        "audit_columns": audit_columns,
        "taxonomy_design": rules.get("taxonomy_design", {}),
        "dropped_source_columns": (rules.get("derived_output") or {}).get("drop_source_columns", []),
    }


def derived_row(
    row: dict[str, Any],
    rules: dict[str, Any],
    schema: dict[str, Any],
    classified_at: str,
    include_axis_values: bool,
) -> dict[str, Any]:
    id_column = schema["id_column"]
    result = classify_row(row, rules)
    axis_values = result["axis_values"]

    output: dict[str, Any] = {"source_row_id": row.get(id_column, "")}
    for column in schema["identity_columns"]:
        if column == "source_row_id":
            continue
        output[column] = row.get(column, "")

    for column in schema["derived_columns"]:
        axis_name = column["name"]
        output[axis_name] = axis_values.get(axis_name, [] if column["multi_value"] else "")

    output["taxonomy_version"] = rules.get("version", "")
    output["confidence"] = result["confidence"]
    output["review_status"] = result["review_status"]
    if include_axis_values:
        output["axis_values"] = axis_values
    output["missing_required_axes"] = result["missing_required_axes"]
    output["rule_ids"] = result["rule_ids"]
    output["evidence"] = result["evidence"]
    output["classified_at"] = classified_at
    return output


def build_rows(
    source_rows: list[dict[str, Any]],
    rules: dict[str, Any],
    schema: dict[str, Any],
    include_axis_values: bool,
) -> list[dict[str, Any]]:
    classified_at = datetime.now(UTC).isoformat()
    return [derived_row(row, rules, schema, classified_at, include_axis_values) for row in source_rows]


def ordered_fields(schema: dict[str, Any]) -> list[str]:
    return [
        *schema["identity_columns"],
        *[column["name"] for column in schema["derived_columns"]],
        *schema["audit_columns"],
    ]


def write_csv(rows: list[dict[str, Any]], schema: dict[str, Any], output: Path) -> None:
    fields = ordered_fields(schema)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: serialize_csv_value(row.get(field)) for field in fields})


def write_jsonl(rows: list[dict[str, Any]], output: Path) -> None:
    with output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_json(rows: list[dict[str, Any]], output: Path) -> None:
    output.write_text(json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_output(rows: list[dict[str, Any]], schema: dict[str, Any], output: Path, output_type: str | None, overwrite: bool) -> None:
    if output.exists() and not overwrite:
        raise SystemExit(f"Output already exists: {output}. Use --overwrite to replace it.")
    output.parent.mkdir(parents=True, exist_ok=True)
    resolved_type = output_type or infer_output_type(output)
    if resolved_type == "csv":
        write_csv(rows, schema, output)
    elif resolved_type == "jsonl":
        write_jsonl(rows, output)
    elif resolved_type == "json":
        write_json(rows, output)
    else:
        raise ValueError(f"unsupported output type: {resolved_type}")


def postgres_column_type(schema: dict[str, Any], column: str) -> str:
    if column in {"evidence", "axis_values"}:
        return "jsonb"
    if column in {"rule_ids", "missing_required_axes"}:
        return "text[]"
    if column == "confidence":
        return "numeric"
    if column == "classified_at":
        return "timestamptz"
    for axis in schema["derived_columns"]:
        if axis["name"] == column and axis["multi_value"]:
            return "text[]"
    return "text"


def postgres_value(schema: dict[str, Any], column: str, value: Any) -> Any:
    if column in {"evidence", "axis_values"}:
        return json.dumps(value or {}, ensure_ascii=False)
    if column in {"rule_ids", "missing_required_axes"}:
        return value or []
    if column == "classified_at":
        return value
    if postgres_column_type(schema, column) == "text[]":
        return value or []
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def write_postgres(rows: list[dict[str, Any]], schema: dict[str, Any], dsn: str, table: str, replace: bool) -> None:
    if table.lower() in {"product", "user", "users", "order", "orders"}:
        raise SystemExit("Refusing to write to a likely source table. Use a derived/classified table name.")

    try:
        import psycopg2
    except ImportError as exc:
        raise SystemExit("psycopg2 is required for PostgreSQL derived table output") from exc

    table_name = quote_ident(table)
    fields = ordered_fields(schema)
    ddl_columns = []
    for field in fields:
        column_type = postgres_column_type(schema, field)
        suffix = " primary key" if field == "source_row_id" else ""
        if field == "classified_at":
            suffix = " not null"
        ddl_columns.append(f"{quote_ident(field)} {column_type}{suffix}")

    placeholders = ", ".join(["%s"] * len(fields))
    quoted_fields = ", ".join(quote_ident(field) for field in fields)
    update_fields = [field for field in fields if field != "source_row_id"]
    updates = ", ".join(f"{quote_ident(field)} = excluded.{quote_ident(field)}" for field in update_fields)

    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cursor:
            if replace:
                cursor.execute(f"drop table if exists {table_name}")
            cursor.execute(f"create table if not exists {table_name} ({', '.join(ddl_columns)})")
            for row in rows:
                values = [postgres_value(schema, field, row.get(field)) for field in fields]
                cursor.execute(
                    f"""
                    insert into {table_name} ({quoted_fields})
                    values ({placeholders})
                    on conflict (source_row_id) do update set {updates}
                    """,
                    values,
                )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-type", choices=["csv", "json", "jsonl"], required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--rules", required=True)
    parser.add_argument("--output")
    parser.add_argument("--output-type", choices=["csv", "json", "jsonl"])
    parser.add_argument("--identity-columns", help="Comma-separated source columns to keep, e.g. goods_name")
    parser.add_argument("--include-axis-values", action="store_true")
    parser.add_argument("--schema-output")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--skip-design-contract-check", action="store_true")
    parser.add_argument("--dsn")
    parser.add_argument("--table")
    parser.add_argument("--replace", action="store_true", help="Replace the PostgreSQL derived table")
    args = parser.parse_args()

    if not args.output and not (args.dsn and args.table):
        raise SystemExit("Provide --output or both --dsn and --table")

    source_rows = load_rows(Path(args.source), args.source_type)
    rules = json.loads(Path(args.rules).read_text(encoding="utf-8"))
    if not args.skip_design_contract_check:
        validate_design_contract(rules)
    identity_columns = parse_csv_list(args.identity_columns)
    schema = build_schema(source_rows, rules, identity_columns, args.include_axis_values)
    rows = build_rows(source_rows, rules, schema, args.include_axis_values)

    if args.schema_output:
        schema_path = Path(args.schema_output)
        if schema_path.exists() and not args.overwrite:
            raise SystemExit(f"Schema output already exists: {schema_path}. Use --overwrite to replace it.")
        schema_path.parent.mkdir(parents=True, exist_ok=True)
        schema_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.output:
        write_output(rows, schema, Path(args.output), args.output_type, args.overwrite)
        print(f"wrote {len(rows)} derived rows to {args.output}")

    if args.dsn and args.table:
        write_postgres(rows, schema, args.dsn, args.table, args.replace)
        print(f"loaded {len(rows)} derived rows into {args.table}")


if __name__ == "__main__":
    main()

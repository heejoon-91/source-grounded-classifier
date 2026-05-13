#!/usr/bin/env python3
"""Create a derived output shaped by rule-defined classification columns.

This script does not mutate the source data. It keeps only a minimal set of
identity/display columns, expands rule axes into real columns, and adds only
the requested audit columns. Full rule evidence can be written to a separate
audit output. When rules declare
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
    "product_id",
    "product_no",
    "goods_no",
    "sku",
    "goods_name",
    "product_name",
    "name",
    "title",
    "label",
    "subject",
]

DERIVED_AUDIT_COLUMN_GROUPS = {
    "none": [],
    "minimal": ["taxonomy_version", "confidence", "review_status", "classified_at"],
    "standard": [
        "taxonomy_version",
        "confidence",
        "review_status",
        "missing_required_axes",
        "rule_ids",
        "classified_at",
    ],
    "full": [
        "taxonomy_version",
        "confidence",
        "review_status",
        "axis_values",
        "missing_required_axes",
        "rule_ids",
        "evidence",
        "classified_at",
    ],
}

ALLOWED_DERIVED_AUDIT_COLUMNS = set(DERIVED_AUDIT_COLUMN_GROUPS["full"])

AUDIT_OUTPUT_FIELDS = [
    "source_row_id",
    "taxonomy_version",
    "axis_values",
    "confidence",
    "review_status",
    "conflicts",
    "missing_required_axes",
    "rule_ids",
    "evidence",
    "classified_at",
]


def parse_csv_list(value: str | None) -> list[str] | None:
    if value is None:
        return None
    if value.strip() == "":
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def normalize_list(value: Any, name: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return parse_csv_list(value) or []
    raise SystemExit(f"{name} must be a list or comma-separated string")


def derived_output_config(rules: dict[str, Any]) -> dict[str, Any]:
    config = rules.get("derived_output") or {}
    if not isinstance(config, dict):
        raise SystemExit("rules.derived_output must be an object")
    return config


def resolve_audit_columns(config_value: Any, include_axis_values: bool) -> list[str]:
    if config_value is None:
        columns = list(DERIVED_AUDIT_COLUMN_GROUPS["minimal"])
    elif isinstance(config_value, str) and config_value in DERIVED_AUDIT_COLUMN_GROUPS:
        columns = list(DERIVED_AUDIT_COLUMN_GROUPS[config_value])
    else:
        columns = normalize_list(config_value, "audit_columns")

    if include_axis_values and "axis_values" not in columns:
        columns.append("axis_values")

    invalid = sorted(set(columns) - ALLOWED_DERIVED_AUDIT_COLUMNS)
    if invalid:
        allowed = ", ".join(sorted(ALLOWED_DERIVED_AUDIT_COLUMNS))
        raise SystemExit(f"Unsupported derived audit columns: {', '.join(invalid)}. Allowed: {allowed}")

    deduped = []
    for column in columns:
        if column not in deduped:
            deduped.append(column)
    return deduped


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
    configured = derived_output_config(rules).get("identity_columns")
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
    audit_columns_config: Any,
) -> dict[str, Any]:
    id_column = rules.get("id_column")
    if not id_column:
        raise SystemExit("rules.json must include id_column")

    selected_identity_columns = identity_columns
    if selected_identity_columns is None:
        selected_identity_columns = default_identity_columns(rows, rules)
    config = derived_output_config(rules)
    drop_source_columns = normalize_list(config.get("drop_source_columns"), "drop_source_columns")

    axes = axis_names(rules)
    overlap = sorted(set(selected_identity_columns) & set(axes))
    if overlap:
        raise SystemExit(f"Identity columns overlap derived axis columns: {', '.join(overlap)}")

    dropped_identity = sorted(set(selected_identity_columns) & set(drop_source_columns))
    if dropped_identity:
        raise SystemExit(f"Identity columns cannot also be drop_source_columns: {', '.join(dropped_identity)}")

    if rows:
        available_columns = set().union(*(row.keys() for row in rows))
        missing_identity = [column for column in selected_identity_columns if column not in available_columns]
        if missing_identity:
            raise SystemExit(f"Identity columns not found in source rows: {', '.join(missing_identity)}")

    audit_columns = resolve_audit_columns(audit_columns_config, include_axis_values)

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
        "dropped_source_columns": drop_source_columns,
        "column_policy": {
            "shape": "thin_canonical_derived_table",
            "source_columns_kept": ["source_row_id", *selected_identity_columns],
            "source_columns_excluded": drop_source_columns,
        },
    }


def derived_row(
    row: dict[str, Any],
    rules: dict[str, Any],
    schema: dict[str, Any],
    classified_at: str,
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

    audit_values = {
        "taxonomy_version": rules.get("version", ""),
        "confidence": result["confidence"],
        "review_status": result["review_status"],
        "axis_values": axis_values,
        "missing_required_axes": result["missing_required_axes"],
        "rule_ids": result["rule_ids"],
        "evidence": result["evidence"],
        "classified_at": classified_at,
    }
    for column in schema["audit_columns"]:
        output[column] = audit_values[column]
    return output


def build_rows(
    source_rows: list[dict[str, Any]],
    rules: dict[str, Any],
    schema: dict[str, Any],
) -> list[dict[str, Any]]:
    classified_at = datetime.now(UTC).isoformat()
    return [derived_row(row, rules, schema, classified_at) for row in source_rows]


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


def write_dict_csv(rows: list[dict[str, Any]], fields: list[str], output: Path) -> None:
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


def build_audit_rows(source_rows: list[dict[str, Any]], rules: dict[str, Any], classified_at: str) -> list[dict[str, Any]]:
    id_column = rules.get("id_column")
    if not id_column:
        raise SystemExit("rules.json must include id_column")
    rows = []
    for row in source_rows:
        result = classify_row(row, rules)
        rows.append(
            {
                "source_row_id": row.get(id_column, ""),
                "taxonomy_version": rules.get("version", ""),
                "axis_values": result["axis_values"],
                "confidence": result["confidence"],
                "review_status": result["review_status"],
                "conflicts": result["conflicts"],
                "missing_required_axes": result["missing_required_axes"],
                "rule_ids": result["rule_ids"],
                "evidence": result["evidence"],
                "classified_at": classified_at,
            }
        )
    return rows


def write_audit_output(rows: list[dict[str, Any]], output: Path, output_type: str | None, overwrite: bool) -> None:
    if output.exists() and not overwrite:
        raise SystemExit(f"Audit output already exists: {output}. Use --overwrite to replace it.")
    output.parent.mkdir(parents=True, exist_ok=True)
    resolved_type = output_type or infer_output_type(output)
    if resolved_type == "csv":
        write_dict_csv(rows, AUDIT_OUTPUT_FIELDS, output)
    elif resolved_type == "jsonl":
        write_jsonl(rows, output)
    elif resolved_type == "json":
        write_json(rows, output)
    else:
        raise ValueError(f"unsupported audit output type: {resolved_type}")


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
    parser.add_argument(
        "--audit-columns",
        help="Derived-table audit columns: none, minimal, standard, full, or a comma-separated list",
    )
    parser.add_argument("--include-axis-values", action="store_true", help="Add axis_values to derived-table audit columns")
    parser.add_argument("--audit-output", help="Optional separate audit output with full evidence")
    parser.add_argument("--audit-output-type", choices=["csv", "json", "jsonl"])
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
    audit_columns_config = args.audit_columns
    if audit_columns_config is None:
        audit_columns_config = derived_output_config(rules).get("audit_columns")
    schema = build_schema(source_rows, rules, identity_columns, args.include_axis_values, audit_columns_config)
    rows = build_rows(source_rows, rules, schema)

    if args.schema_output:
        schema_path = Path(args.schema_output)
        if schema_path.exists() and not args.overwrite:
            raise SystemExit(f"Schema output already exists: {schema_path}. Use --overwrite to replace it.")
        schema_path.parent.mkdir(parents=True, exist_ok=True)
        schema_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.output:
        write_output(rows, schema, Path(args.output), args.output_type, args.overwrite)
        print(f"wrote {len(rows)} derived rows to {args.output}")

    if args.audit_output:
        classified_at = rows[0].get("classified_at") if rows else datetime.now(UTC).isoformat()
        audit_rows = build_audit_rows(source_rows, rules, str(classified_at))
        write_audit_output(audit_rows, Path(args.audit_output), args.audit_output_type, args.overwrite)
        print(f"wrote {len(audit_rows)} audit rows to {args.audit_output}")

    if args.dsn and args.table:
        write_postgres(rows, schema, args.dsn, args.table, args.replace)
        print(f"loaded {len(rows)} derived rows into {args.table}")


if __name__ == "__main__":
    main()

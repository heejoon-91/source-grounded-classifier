#!/usr/bin/env python3
"""Inspect PostgreSQL tables after connecting to a DB or restored dump."""

from __future__ import annotations

import argparse
import json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--schema", default="public")
    parser.add_argument("--output", default="-")
    args = parser.parse_args()

    try:
        import psycopg2
        import psycopg2.extras
    except ImportError as exc:
        raise SystemExit("psycopg2 is required for PostgreSQL schema inspection") from exc

    with psycopg2.connect(args.dsn) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                """
                select
                  c.table_name,
                  obj_description(format('%I.%I', c.table_schema, c.table_name)::regclass) as comment,
                  coalesce(s.n_live_tup, 0) as estimated_rows,
                  json_agg(
                    json_build_object(
                      'column', c.column_name,
                      'type', c.udt_name,
                      'nullable', c.is_nullable
                    )
                    order by c.ordinal_position
                  ) as columns
                from information_schema.columns c
                left join pg_stat_user_tables s
                  on s.schemaname = c.table_schema
                 and s.relname = c.table_name
                where c.table_schema = %s
                group by c.table_schema, c.table_name, s.n_live_tup
                order by coalesce(s.n_live_tup, 0) desc, c.table_name
                """,
                [args.schema],
            )
            tables = [dict(row) for row in cursor.fetchall()]

    payload = json.dumps({"schema": args.schema, "tables": tables}, ensure_ascii=False, indent=2)
    if args.output == "-":
        print(payload)
    else:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(payload + "\n")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Safely restore a PostgreSQL dump into a temporary database for profiling."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump", required=True)
    parser.add_argument("--database", required=True, help="Temporary database name, recommended prefix: tmp_")
    parser.add_argument("--owner", default=None)
    parser.add_argument("--allow-non-temp", action="store_true")
    args = parser.parse_args()

    dump = Path(args.dump)
    if not dump.exists():
        raise SystemExit(f"dump does not exist: {dump}")
    if not args.allow_non_temp and not args.database.startswith("tmp_"):
        raise SystemExit("database name must start with tmp_ unless --allow-non-temp is set")

    createdb = ["createdb", args.database]
    if args.owner:
        createdb.extend(["--owner", args.owner])
    run(createdb)

    if dump.suffix in {".dump", ".backup"}:
        run(["pg_restore", "--no-owner", "--no-privileges", "--dbname", args.database, str(dump)])
    else:
        run(["psql", "--dbname", args.database, "--file", str(dump)])

    print(f"restored {dump} into {args.database}")


if __name__ == "__main__":
    main()

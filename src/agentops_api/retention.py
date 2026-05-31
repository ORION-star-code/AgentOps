"""Command-line retention cleanup for local AgentOps SQLite stores."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from agentops_api.observability import DEFAULT_DB_PATH, TraceRepository
from agentops_api.privacy import load_retention_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clean up expired AgentOps trace data.")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--execute", action="store_true", help="Delete expired terminal runs.")
    parser.add_argument(
        "--retention-days",
        default=None,
        help="Override AGENTOPS_RETENTION_DAYS for this cleanup pass.",
    )
    args = parser.parse_args(argv)

    raw_days = args.retention_days or os.getenv("AGENTOPS_RETENTION_DAYS")
    retention_config = load_retention_config(raw_days)
    repository = TraceRepository(
        Path(args.db_path),
        retention_config=retention_config,
    )
    result = repository.cleanup_expired_runs(dry_run=not args.execute)
    print(json.dumps(_jsonable_result(result), ensure_ascii=False, indent=2))
    return 0


def _jsonable_result(result: Any) -> dict[str, Any]:
    payload = asdict(result)
    if payload["cutoff"] is not None:
        payload["cutoff"] = payload["cutoff"].isoformat()
    payload["enabled"] = payload["retention_days"] is not None
    payload["mode"] = "dry-run" if payload["dry_run"] else "execute"
    return payload


if __name__ == "__main__":
    raise SystemExit(main())

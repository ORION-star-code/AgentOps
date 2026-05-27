#!/usr/bin/env python3
"""Validate the lightweight project harness."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ALLOWED_STATES = {"not_started", "active", "blocked", "passing"}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    errors = []

    entry_exists = (root / "AGENTS.md").exists() or (root / "CLAUDE.md").exists()
    if not entry_exists:
        errors.append("Missing AGENTS.md or CLAUDE.md. Add an agent landing page with commands and rules.")

    for relative in ["PROGRESS.md", "DECISIONS.md", "docs/features.json", "docs/QUALITY.md"]:
        if not (root / relative).exists():
            errors.append(f"Missing {relative}. Create it so a fresh agent can continue safely.")

    features_path = root / "docs" / "features.json"
    if features_path.exists():
        try:
            data = json.loads(features_path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"docs/features.json is not valid JSON: {exc}")
        else:
            features = data.get("features")
            if not isinstance(features, list):
                errors.append("docs/features.json must contain a 'features' list.")
            elif len(features) < 3:
                errors.append("docs/features.json should contain at least three feature or work items.")
            else:
                active_count = 0
                seen_ids = set()
                for index, item in enumerate(features, 1):
                    prefix = f"features[{index}]"
                    if not isinstance(item, dict):
                        errors.append(f"{prefix} must be an object.")
                        continue
                    for key in ["id", "behavior", "verification", "state", "evidence"]:
                        if key not in item:
                            errors.append(f"{prefix} missing required key '{key}'.")
                    state = item.get("state")
                    if state not in ALLOWED_STATES:
                        errors.append(f"{prefix}.state must be one of {sorted(ALLOWED_STATES)}.")
                    if state == "active":
                        active_count += 1
                    feature_id = item.get("id")
                    if feature_id in seen_ids:
                        errors.append(f"Duplicate feature id: {feature_id}")
                    seen_ids.add(feature_id)
                    if "TODO" in str(item.get("behavior", "")).upper():
                        errors.append(f"{prefix}.behavior still contains TODO placeholder text.")
                    if "TODO" in str(item.get("verification", "")).upper():
                        errors.append(f"{prefix}.verification still contains TODO placeholder text.")
                if active_count > 1:
                    errors.append(f"WIP=1 violation: {active_count} features are active.")

    if errors:
        print("Harness validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Harness validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

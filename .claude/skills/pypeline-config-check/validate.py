#!/usr/bin/env python3
"""Validate every Pypeline YAML config against the Pydantic schema.

Runs without GStreamer — only requires `pydantic>=2` and `pyyaml`. Catches
field-type errors and unknown keys (every config model uses extra="forbid")
in seconds, instead of the 30s Docker rebuild round-trip.

Exit code: 0 if all configs validate, 1 otherwise.
"""

from __future__ import annotations

import sys
from pathlib import Path


def find_repo_root(start: Path) -> Path:
    """Walk up from `start` until we find Pypeline/pyproject.toml."""
    for ancestor in (start.resolve(), *start.resolve().parents):
        if (ancestor / "Pypeline" / "pyproject.toml").exists():
            return ancestor
    raise RuntimeError(
        f"Could not locate FishingStreams repo root from {start}. "
        "Expected Pypeline/pyproject.toml somewhere above this script."
    )


def main() -> int:
    repo_root = find_repo_root(Path(__file__))
    sys.path.insert(0, str(repo_root / "Pypeline"))

    from pydantic import ValidationError
    from pypeline.config import PipelineConfig

    config_dir = repo_root / "Pypeline" / "configs"
    yamls = sorted(config_dir.glob("*.yaml"))

    if not yamls:
        print(f"no YAML configs found under {config_dir.relative_to(repo_root)}")
        return 1

    failures = 0
    for path in yamls:
        rel = path.relative_to(repo_root)
        try:
            PipelineConfig.from_yaml(path)
            print(f"OK    {rel}")
        except ValidationError as e:
            failures += 1
            print(f"FAIL  {rel}")
            for err in e.errors():
                loc = ".".join(str(p) for p in err["loc"]) or "<root>"
                print(f"      {loc}: {err['msg']}")
        except Exception as e:
            failures += 1
            print(f"FAIL  {rel}")
            print(f"      {type(e).__name__}: {e}")

    print()
    passed = len(yamls) - failures
    print(f"{passed} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

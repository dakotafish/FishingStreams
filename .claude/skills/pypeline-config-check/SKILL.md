---
name: pypeline-config-check
description: Use when a Pypeline YAML config under Pypeline/configs/ or a Pydantic model under Pypeline/pypeline/config/ has been edited, before rebuilding the Docker stack — validates every YAML against the Pydantic schema on the host without spinning up GStreamer.
disable-model-invocation: true
---

# pypeline-config-check

Validate every `Pypeline/configs/*.yaml` against the Pydantic `PipelineConfig`
schema, on the host, without Docker.

## When to invoke

- After editing any `Pypeline/configs/*.yaml`
- After editing any `Pypeline/pypeline/config/*.py` (the schema itself)
- Before `docker compose up --build` — turns a 30s Docker round-trip into a <1s host check
- As part of release prep, alongside any other smoke tests

User-invoked only (`disable-model-invocation: true`). Claude does not auto-run
this; you decide when to verify.

## What it catches

Every config model uses `model_config = ConfigDict(extra="forbid")`, so a
single `PipelineConfig.from_yaml(path)` call exposes:

- Field-type errors (`latency_ms: "two hundred"` → `int_parsing`)
- Missing required fields (`source` / `video` / `sinks`)
- **Unknown keys** — typos like `bitrate_kpbs` or stale fields removed from
  the model

It does *not* exercise GStreamer or MediaMTX — those only fail at runtime
inside the container. This is a pre-flight schema check, not a smoke test.

## How to run

```bash
python3 .claude/skills/pypeline-config-check/validate.py
```

Requirements: `pydantic>=2` and `pyyaml`. Both are in `Pypeline/pyproject.toml`,
so any environment that can run the Pypeline tests can run this.

If you're using the project venv: `Pypeline/venv/bin/python3 .claude/skills/pypeline-config-check/validate.py`.

## Output

```
OK    Pypeline/configs/boat1.yaml

1 passed, 0 failed
```

On failure, each error reports the file, the dotted path into the config, and
the Pydantic error message:

```
FAIL  Pypeline/configs/boat1.yaml
      source.latency_ms: Input should be a valid integer, unable to parse string as an integer
      sinks.srt_publisher.enabld: Extra inputs are not permitted

0 passed, 1 failed
```

Exit code is `0` if every config validates, `1` otherwise — safe to chain
into pre-Docker scripts.

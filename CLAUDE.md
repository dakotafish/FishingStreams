# FishingStreams

Live-streaming pipeline for fishing boats. Path of a frame:

```
Phone (Moblin/Larix) ──SRT──▶ MediaMTX ──▶ GStreamer overlay ──▶ SRT / RTSP / file ──▶ OBS
```

## Directory layout

Three top-level directories, **not** alternatives — each owns a different concern.
Read this before grepping anywhere.

| Dir | Role |
|---|---|
| `Pypeline/` | **Active source of truth.** Python class-based GStreamer pipeline framework. All pipeline code changes go here. |
| `pypeline-stack/` | Deployment compose for `Pypeline/`. Owns the runtime `mediamtx.yml` and `overlays/`. Build context for the gstreamer service is `../Pypeline`. |
| `MVP/` | Original proof-of-concept (MediaMTX + bash GStreamer). Reference for protocol/setup details, not where new code lands. |

See `PROJECT_MAP.md` for the full file-level map (mermaid diagram + every file's purpose).

`pypeline-stack/mediamtx/mediamtx.yml` and `MVP/config/mediamtx.yml` are
**duplicated configs** today — keep them in sync until they're deduplicated.

## Pypeline architecture

- `pypeline/pipeline.py` — `OverlayPipeline` assembles a `Gst.Pipeline` in a
  strict **5-phase build**: (1) build → (2) add_to → (3) link_internal →
  (4) static links → (5) dynamic-pad wiring. New branches must honor this.
- `pypeline/branches/` — branch classes (source, video, audio, mux, tee, sinks).
  Implement `Branch` from `branches/base.py`.
- `pypeline/config/` — Pydantic v2 models. `PipelineConfig.from_yaml()` is the
  single entry point.
- `configs/*.yaml` — pipeline instances (one per boat). Validated against the
  Pydantic schema at load time.

Sinks are toggled by `enabled:` flags in the YAML — no code change needed to
disable a branch.

## Local dev constraint

**PyGObject + GStreamer plugins are container-only on macOS.** There is no
host-side run path. Two consequences:

- Verifying pipeline code = `docker compose up --build` from `pypeline-stack/`
  (or `MVP/` for the legacy stack). Round-trip is ~30s on first build, <2s after.
- Config-only edits can be validated **without Docker** via the
  `pypeline-config-check` skill (see below).

There are no tests and no CI — verification is manual today.

## `pypeline-config-check` skill

Host-side validator for `Pypeline/configs/*.yaml` against the Pydantic schema.
No GStreamer needed; only `pydantic>=2` and `pyyaml`.

**Run it whenever you've just edited:**
- a YAML under `Pypeline/configs/`, or
- a Pydantic model under `Pypeline/pypeline/config/`

**…before recommending `docker compose up --build`.** Catches type errors,
missing required fields, and unknown keys (typos like `bitrate_kpbs`,
`enabld`) in <1s instead of after a 30s rebuild.

```bash
python3 .claude/skills/pypeline-config-check/validate.py
```

Exit `0` = all configs valid, `1` = at least one failed. Users can also invoke
it via the `/pypeline-config-check` slash command (skill is user-only —
Claude does not auto-trigger it). Skill source:
`.claude/skills/pypeline-config-check/`.

## Port map (collide between stacks)

`MVP/` and `pypeline-stack/` both bind these ports. Run **only one stack at a
time**; `docker compose down` in the other first.

| Port | Proto | Purpose |
|---|---|---|
| 8890 | UDP | SRT — phone publishes here, OBS pulls processed stream from here |
| 8888 | TCP | MediaMTX HTTP API (`/v3/paths/list` for readiness checks) |
| 8889 | TCP | HLS preview |
| 8891 | UDP | Pypeline's direct SRT listener for OBS (bypasses mediamtx) |
| 8554 | TCP | In-process RTSP diagnostic server |

## MediaMTX stream-id convention (v1.9+)

Bare path names are rejected. Always use `action:pathname`:

- Publishers (phone): `publish:boat1`
- Readers (OBS, GStreamer source): `read:boat1` or `read:boat1-processed`

Boat-side capture publishes to `boat1`. The Pypeline gstreamer service reads
`read:boat1`, applies the overlay, and publishes back as `publish:boat1-processed`.
OBS reads `read:boat1-processed`.

## Conventions

- Pipeline code style: explicit phase ordering, `Optional[...]` attrs initialized
  to `None` and asserted before use, `print()` for runtime telemetry (no logging
  framework configured).
- Config style: every new branch field gets a default in the Pydantic model;
  YAMLs override only what they care about.
- Errors during link/state transitions are fatal — `RuntimeError` from
  `_build`, `main_loop.quit()` from bus error messages.

## Keep `PROJECT_MAP.md` in sync

Update `PROJECT_MAP.md` in the same change when you:

- add / remove / rename a top-level directory
- add / remove / rename a module under `Pypeline/pypeline/branches/` or `Pypeline/pypeline/config/`
- add / remove a service in either `docker-compose.yml`
- change the data-flow shape (new sink, new tee branch, new transcode stage)

Line-level code changes do **not** require a map update.

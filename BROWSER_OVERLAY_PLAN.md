# Browser Overlay Branch — Implementation Plan

Origin: `~/Downloads/browser-overlay-design-spec.md` + code-architect blueprint + risk verification.

This is a working plan. Delete after the feature lands.

## Goal

Bake a browser-rendered HTML overlay (the existing `catch-counter.html`) into the
republished SRT stream via an in-container Xvfb + Chromium + ximagesrc capture
chain that feeds a compositor. Opt-in per boat (`enabled: false` default).

## Architecture (when enabled)

```
SRT in (read:boat1) ─▶ source ─▶ video_decode (BGRA)
                                       │
                                       ▼ sink_0 (zorder 0)
                                  compositor ─▶ videoconvert ─▶ caps(BGRA) ─▶ scoreboard ─▶ video_encode ─▶ mux ─▶ tee ─▶ sinks
                                       ▲ sink_1 (zorder 1, alpha)
                                       │
                                  queue (decouple)
                                       ▲
                          caps(RGBA, fps) ─ videoconvert ─ ximagesrc (DISPLAY=:99, use-damage=false)
                                                              ▲
                                                         Xvfb :99
                                                              ▲
                                                         xcompmgr  (required for Chromium transparent visuals)
                                                              ▲
                                                         Chromium --kiosk --enable-transparent-visuals --app=http://localhost:8080/catch-counter.html
                                                              ▲
                                                         overlay-server  (python -m http.server on /overlays)
```

When `browser_overlay.enabled=false`, none of the new branches are instantiated and
the Phase 4 link reverts to the original `video_decode → scoreboard → video_encode`.

## Risk-verification deltas (applied to the architect blueprint)

1. **Chromium install path**: `chromium-browser` on Ubuntu 24.04 is a Snap stub
   that fails inside Docker. Use the **xtradeb PPA** (`ppa:xtradeb/apps`) which
   ships a real `.deb`. Binary name is `chromium`, not `chromium-browser`.
2. **Transparent visuals**: `--enable-transparent-visuals` requires a compositing
   manager (`_NET_WM_CM_S0` atom). Add **xcompmgr** to apt + a supervisord
   program at priority 1 alongside Xvfb.
3. **Overlay HTML**: `pypeline-stack/overlays/` is the directory mounted into
   the gstreamer container; `catch-counter.html` lives at `BrowserSources/` in
   the repo root. **Copy** (not move — OBS scenes outside this repo may still
   reference the BrowserSources path) into `pypeline-stack/overlays/`.

## Files to create

- `Pypeline/supervisord.conf` — supervisord with 5 programs:
  - priority 1: `Xvfb :99 -screen 0 1920x1080x24 -ac`
  - priority 1: `xcompmgr -n` (env DISPLAY=:99)
  - priority 2: `python3 /app/overlay_server.py --port 8080 --dir /overlays`
  - priority 3: `chromium --no-sandbox --disable-gpu --disable-dev-shm-usage --window-size=1920,1080 --window-position=0,0 --kiosk --enable-transparent-visuals --app=http://localhost:8080/catch-counter.html` (env DISPLAY=:99)
  - priority 4: existing `python3 /app/main.py --config /app/configs/boat1.yaml`
- `Pypeline/overlay_server.py` — stdlib `http.server` wrapper, `--port` + `--dir` CLI.
- `Pypeline/pypeline/branches/browser_overlay.py` — `BrowserOverlaySourceBranch`:
  - elements: `ximagesrc` → `videoconvert` → `capsfilter(RGBA,framerate=N/1)` → `queue`
  - output_pad: `queue.src`; no `input_pad` (source-only branch)
- `Pypeline/pypeline/branches/compositor.py` — `CompositorBranch`:
  - elements: `compositor` → `videoconvert` → `capsfilter(BGRA)`
  - `request_video_pad()` allocates sink_0, zorder=0
  - `request_overlay_pad()` allocates sink_1, zorder=1, alpha=1.0
  - output_pad: `capsfilter.src` (BGRA so downstream `scoreboard`/cairooverlay still works)
- `Pypeline/pypeline/config/browser_overlay.py` — `BrowserOverlayConfig`:
  - `enabled: bool = False`
  - `display_name: str = ":99"`
  - `framerate: int = Field(30, gt=0, le=60)`
  - `capture_endx: int = Field(1919, ge=0)`
  - `capture_endy: int = Field(1079, ge=0)`
  - Width/height/URL are owned by `supervisord.conf`, not by the YAML.
- `pypeline-stack/overlays/catch-counter.html` — copy from `BrowserSources/catch-counter.html`.

## Files to modify

- `Pypeline/Dockerfile` — add apt packages (`xvfb`, `x11-utils`, `xcompmgr`, `supervisor`,
  `software-properties-common`), add xtradeb PPA, install `chromium`, COPY
  `supervisord.conf` and `overlay_server.py`, change `ENTRYPOINT`/`CMD` to
  `supervisord -c /etc/supervisor/conf.d/supervisord.conf`.
- `pypeline-stack/docker-compose.yml` — add `DISPLAY=:99` to gstreamer service env.
- `Pypeline/pypeline/config/browser_overlay.py` — see above (created).
- `Pypeline/pypeline/config/pipeline.py` — register `browser_overlay` field with
  `default_factory=BrowserOverlayConfig`.
- `Pypeline/pypeline/config/__init__.py` — export `BrowserOverlayConfig`.
- `Pypeline/pypeline/branches/__init__.py` — export `BrowserOverlaySourceBranch` + `CompositorBranch`.
- `Pypeline/pypeline/pipeline.py` — import + Optional attrs + gated instantiation
  in `_build()` + conditional Phase-4 video-side link rewrite.
- `Pypeline/configs/boat1.yaml` — add `browser_overlay:` stanza with `enabled: false`.
- `PROJECT_MAP.md` — new branch/config files; new supervisord/overlay-server entries;
  updated mermaid diagram.

## Out of scope (v2)

- WebSocket push for live leaderboard (plug-in point is `overlay_server.py`).
- Fish-detection event triggers.
- Hardware encoding (nvenc/vaapi).
- Health-check script polling Xvfb for non-black frame before launching GStreamer
  (currently mitigated by conservative `startsecs` values).

## Verification path

1. Phase E — `python3 .claude/skills/pypeline-config-check/validate.py` exits 0.
2. Phase F — `docker compose up --build` from `pypeline-stack/`, boat1 with
   `enabled:false`. Pipeline must behave identically to today.
3. Enabled-mode end-to-end is deferred to a follow-up: flip the flag, rebuild,
   verify all five supervisord programs reach RUNNING and the republished
   `boat1-processed` stream shows the overlay composited on top.

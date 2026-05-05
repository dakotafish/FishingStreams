# FishyMedia MVP

Proof of concept for SRT ingest and delivery to OBS. A single MediaMTX container receives an SRT stream from a phone and re-serves it over SRT for OBS to consume.

```
Phone (Larix Broadcaster)
  └── SRT push ──► MediaMTX (Docker) ──► GStreamer ──► MediaMTX ──► Clients (OBS on local machine, a web page, or youtube)
```

---

## Prerequisites

- [Docker Desktop](https://docs.docker.com/desktop/setup/install/mac-install/) installed and running
- [OBS Studio](https://obsproject.com/) installed
- [Moblin](https://apps.apple.com/us/app/moblin/id1618764244) installed on your phone
- Phone and dev machine on the same WiFi network

---

## Start the Server

```bash
cd MVP/
docker compose up
```

First run builds the image (~30 seconds). Subsequent runs start in under 2 seconds.

Confirm it's ready — you should see both of these lines:

```
INF [HLS] listener opened on :8889
INF [SRT] listener opened on :8890 (UDP)
```

---

## Find Your Machine's LAN IP

The phone needs your machine's local network IP to connect.

**Mac:** System Settings → Wi-Fi → Details → IP Address

Or in the terminal:

```bash
ipconfig getifaddr en0
```

Example: `192.168.1.42`

---

## Phone Setup (Moblin)

In Moblin, navigate to the stream settings and configure an SRT connection with these values:

| Field | Value |
|---|---|
| Protocol | SRT |
| URL | `srt://192.168.1.42:8890` (use your actual LAN IP) |
| Stream ID | `publish:boat1` |
| Latency | `200` ms |
| Passphrase | *(leave empty)* |

Tap the go-live button to start streaming.

**Important:** The stream ID must be `publish:boat1`, not just `boat1`. MediaMTX v1.9+ requires the `action:pathname` format to distinguish publishers from readers.

---

## Verify the Stream Is Live

Before opening OBS, confirm MediaMTX received the stream:

```
http://localhost:8888/v3/paths/list
```

Look for `"boat1"` with `"ready": true`. If you don't see it, the phone isn't connected — check the LAN IP and that both devices are on the same network.

---

## OBS Setup

1. In OBS, click **+** under Sources → **Media Source**
2. Uncheck **Local File**
3. Configure:

| Field | Value |
|---|---|
| Input | `srt://localhost:8890?streamid=read:boat1-processed` |
| Reconnect Attempt | checked, 10 seconds |
| Close file/URL when inactive | unchecked |
| Network Buffering | 0 MB |

4. Click OK. The stream should appear within 1–3 seconds.

**Note:** OBS reads `boat1-processed` — the path GStreamer publishes after adding the overlay. The `read:` prefix tells MediaMTX we're consuming, not publishing. The raw `boat1` path is still available for debugging if you want to bypass the GStreamer stage.

---

## Ports

| Port | Protocol | Purpose |
|---|---|---|
| `8890` | UDP | SRT — phone pushes here, OBS pulls from here |
| `8888` | TCP | MediaMTX HTTP API (stream diagnostics) |
| `8889` | TCP | HLS preview (browser playback fallback) |

---

## HLS Browser Preview

While the phone is streaming, you can also watch in a browser (VLC or Safari — Chrome does not support HLS natively):

```
http://localhost:8889/boat1/index.m3u8
```

Latency will be higher than SRT (6–10 seconds) due to HLS segment buffering. This is a diagnostic tool, not the primary path.

---

## Lessons Learned

These issues came up during initial setup and are documented here to save future developers time.

**MediaMTX API and HLS cannot share a port.**
Both default to `:8888`. Assigning them the same address causes a `bind: address already in use` crash on startup. They must be on separate ports — API on `:8888`, HLS on `:8889`.

**MediaMTX v1.9+ requires `action:pathname` stream ID format.**
Bare stream IDs like `boat1` are rejected. Publishers must use `publish:boat1`; readers must use `read:boat1`. Configure Larix with `publish:boat1` and OBS with `streamid=read:boat1`.

**MediaMTX v1.9+ has authentication enabled by default.**
The API returns a login prompt out of the box. For MVP, disable it by setting `authMethod: internal` with a catch-all `user: any` / `pass: any` entry in `authInternalUsers`. The config option `authMethod: none` is not valid and crashes on startup.

**MediaMTX ARM release filenames differ from Docker's `TARGETARCH`.**
Docker BuildKit sets `TARGETARCH=arm64` on Apple Silicon, but MediaMTX GitHub releases use `arm64v8` in their filenames. The Dockerfile maps `arm64 → arm64v8` before constructing the download URL.

**`network_mode: host` does not work on Docker Desktop for Mac.**
Docker Desktop runs containers inside a Linux VM. Host networking does not expose container ports to the Mac's physical network interfaces. Use explicit port mappings instead.

---

## File Structure

```
MVP/
├── docker-compose.yml
├── readMe.md
├── mediamtx/
│   └── Dockerfile          Ubuntu 24.04 + MediaMTX binary
└── config/
    └── mediamtx.yml        SRT + HLS config, auth disabled
```

import json
import signal
import urllib.request
from time import sleep

import gi
gi.require_version("Gst", "1.0")
gi.require_version("GstRtspServer", "1.0")
from gi.repository import Gst, GLib, GstRtspServer

# diagnostic: set False to drop the audio branch entirely. isolates whether
# A/V timing at the mux is what's breaking HLS / downstream decoders.
INCLUDE_AUDIO = True

print("running overlay_pipeline.py")
print(f"INCLUDE_AUDIO={INCLUDE_AUDIO}")

# wait for the phone's stream to show up in mediamtx before building the pipeline
print("Waiting for MediaMTX path 'boat1' to be ready...")
while True:
    try:
        data = json.load(urllib.request.urlopen("http://mediamtx:8888/v3/paths/list", timeout=2))
        ready = {p["name"] for p in data.get("items", []) if p.get("ready")}
        if "boat1" in ready:
            break
    except Exception:
        pass
    sleep(2)
print("boat1 is live — starting GStreamer pipeline")

Gst.init(None)

main_loop = GLib.MainLoop()
pipeline = Gst.Pipeline.new("pipeline")


def make(factory, name, **props):
    """Create an element, set properties from kwargs, and add it to the pipeline.
    Property names use underscores (Python kwargs); GStreamer expects dashes."""
    element = Gst.ElementFactory.make(factory, name)
    if element is None:
        raise RuntimeError(f"failed to create {factory!r} — check plugin install (rsvg? libav?)")
    for key, value in props.items():
        element.set_property(key.replace("_", "-"), value)
    pipeline.add(element)
    return element


def make_caps(name, caps_str):
    return make("capsfilter", name, caps=Gst.Caps.from_string(caps_str))


# tee branch queues need generous sizing so a slow consumer (srtsink waiting on
# OBS, the RTSP bridge) never applies back-pressure to the tee and corrupts the
# other branches. 10s of video at 5Mbps ≈ 6MB, so 16MB is comfortable headroom.
def make_branch_queue(name):
    return make(
        "queue", name,
        max_size_buffers=0,
        max_size_time=10 * Gst.SECOND,
        max_size_bytes=16 * 1024 * 1024,
    )


# --- source: SRT stream from mediamtx (published by Moblin) ---
source = make("srtsrc", "src",
              uri="srt://mediamtx:8890?streamid=read:boat1",
              latency=200)


# --- demux: MPEG-TS → video ES (h265) + audio ES (aac) ---
demux = make("tsdemux", "demux")


# --- video branch: parse → decode → overlay → re-encode → parse ---
video_parse_in = make("h265parse", "video_parse_in")
video_decode = make("avdec_h265", "video_decode")
video_convert_pre = make("videoconvert", "video_convert_pre")
video_overlay = make("rsvgoverlay", "video_overlay", location="/overlays/placeholder.svg")
video_convert_post = make("videoconvert", "video_convert_post")
# force 4:2:0 chroma so x264enc picks High profile (not High 4:4:4, which HLS + OBS can't decode)
video_caps_i420 = make_caps("video_caps_i420", "video/x-raw,format=I420")
video_encode = make(
    "x264enc", "video_encode",
    tune="zerolatency",
    speed_preset="veryfast",
    bitrate=5000,      # kbps, match moblin's 5 Mbps
    key_int_max=30,    # 1s @ 30fps → fast OBS/VLC join
    bframes=0,
)
# config-interval=-1 re-inserts SPS/PPS on every IDR so mid-stream joiners see them
video_parse_out = make("h264parse", "video_parse_out", config_interval=-1)
# force byte-stream + AU alignment so mpegtsmux packs whole access units (with
# in-band SPS/PPS) into PES. Without this, h264parse may negotiate AVC/NAL
# alignment and SPS/PPS can end up out-of-band where VLC won't find them.
video_caps_h264 = make_caps("video_caps_h264", "video/x-h264,stream-format=byte-stream,alignment=au")
video_queue_out = make("queue", "video_queue_out")


# --- audio branch: passthrough, no decode/re-encode ---
if INCLUDE_AUDIO:
    audio_parse = make("aacparse", "audio_parse")
    audio_queue_out = make("queue", "audio_queue_out")


# --- mux + sink: re-pack MPEG-TS, publish back to mediamtx over SRT ---
# alignment=7 packs 7 TS packets (188*7 = 1316 bytes) per buffer — the canonical
# SRT / UDP payload size. without this, mpegtsmux emits 1-packet buffers that
# srtsink turns into tiny SRT messages; Docker's UDP forwarding drops/reorders
# them, which is what made VLC never see an intact IDR (no SPS/PPS) over SRT
# even though the RTSP path (which chunks via rtpmp2tpay) was fine.
mux = make("mpegtsmux", "mux", alignment=7)

# tee the muxed output four ways:
#   1. srtsink publishing to mediamtx (for HLS / future consumers)
#   2. filesink (diagnostic — same bytes as what srtsink emits)
#   3. srtsink in listener mode for OBS to connect directly, bypassing mediamtx
#      (mediamtx re-serves Moblin's H265 fine but corrupts our H264 re-serve)
#   4. appsink → in-process RTSP server bridge (see below)
tee = make("tee", "tee")
tee_srt_queue = make("queue", "tee_srt_queue")
tee_file_queue = make("queue", "tee_file_queue")
tee_listen_queue = make_branch_queue("tee_listen_queue")
tee_rtsp_queue = make_branch_queue("tee_rtsp_queue")

sink = make("srtsink", "sink",
            uri="srt://mediamtx:8890?streamid=publish:boat1-processed",
            latency=200)

file_sink = make("filesink", "file_sink", location="/logs/output.ts")

# listener sink for OBS — binds inside the container on :8891, docker-compose
# exposes it on the host. OBS connects as caller.
# latency=2000 gives SRT enough window to retransmit lost packets before they
# expire; 200ms was causing 6–12 packet gaps that ate whole IDRs.
listen_sink = make(
    "srtsink", "listen_sink",
    uri="srt://:8891?mode=listener&streamid=boat1-processed&latency=2000",
    latency=2000,
    wait_for_connection=False,
)
# 'async' is a Python reserved keyword so it can't go through kwargs — set it directly
listen_sink.set_property("async", False)

# 4th tee branch: bridge MPEG-TS bytes into an in-process RTSP server via
# appsink → appsrc. lets us test if the issue is SRT transport or the stream
# content itself — mpv/VLC/OBS can pull rtsp://<host>:8554/boat1-processed.
rtsp_appsink = make(
    "appsink", "rtsp_appsink",
    emit_signals=True,
    sync=False,
    max_buffers=200,
    drop=False,
)


# static links — everything except tsdemux → branch-heads, which are dynamic
source.link(demux)

if not Gst.Element.link_many(
    video_parse_in, video_decode, video_convert_pre, video_overlay,
    video_convert_post, video_caps_i420, video_encode, video_parse_out,
    video_caps_h264, video_queue_out, mux,
):
    raise RuntimeError("failed to link video branch")

if INCLUDE_AUDIO:
    if not Gst.Element.link_many(audio_parse, audio_queue_out, mux):
        raise RuntimeError("failed to link audio branch")

if not Gst.Element.link_many(mux, tee):
    raise RuntimeError("failed to link mux → tee")

# tee fans out — each branch is queue → sink
for branch_queue, branch_sink in (
    (tee_srt_queue, sink),
    (tee_file_queue, file_sink),
    (tee_listen_queue, listen_sink),
    (tee_rtsp_queue, rtsp_appsink),
):
    if not Gst.Element.link_many(tee, branch_queue, branch_sink):
        raise RuntimeError(f"failed to link tee branch {branch_queue.get_name()}")


def on_pad_added(_demux, pad):
    caps = pad.get_current_caps() or pad.query_caps()
    caps_str = caps.to_string() if caps else "unknown"
    print(f"[tsdemux pad-added] name={pad.get_name()} caps={caps_str}")

    structure = caps.get_structure(0) if caps else None
    media_type = structure.get_name() if structure else ""

    if media_type.startswith("video/"):
        target = video_parse_in.get_static_pad("sink")
    elif media_type.startswith("audio/"):
        if not INCLUDE_AUDIO:
            # route to a fakesink so tsdemux's audio pad has a consumer
            # (otherwise it emits not-linked flow errors and stalls the demuxer)
            print(f"[tsdemux pad-added] INCLUDE_AUDIO=False — routing audio to fakesink")
            audio_drop = Gst.ElementFactory.make("fakesink", None)
            audio_drop.set_property("sync", False)
            audio_drop.set_property("async", False)
            pipeline.add(audio_drop)
            audio_drop.sync_state_with_parent()
            target = audio_drop.get_static_pad("sink")
        else:
            target = audio_parse.get_static_pad("sink")
    else:
        print(f"[tsdemux pad-added] ignoring media_type={media_type}")
        return

    if target.is_linked():
        print(f"[tsdemux pad-added] target for {media_type} already linked — skipping")
        return

    result = pad.link(target)
    print(f"[tsdemux pad-added] link result for {media_type}: {result}")


demux.connect("pad-added", on_pad_added)


def on_message(_, msg):
    if msg.type == Gst.MessageType.EOS:
        print("End of stream")
        main_loop.quit()
    elif msg.type == Gst.MessageType.ERROR:
        err, debug = msg.parse_error()
        print(f"Error: {err.message} | {debug}")
        main_loop.quit()


bus = pipeline.get_bus()
bus.add_signal_watch()
bus.connect("message", on_message)

# graceful shutdown on SIGTERM/SIGINT — without this, docker compose down leaves
# srtsrc in a reconnect loop that floods mediamtx before the container dies
def _shutdown(*_):
    print("signal received, stopping pipeline")
    GLib.idle_add(main_loop.quit)
    return False

signal.signal(signal.SIGTERM, _shutdown)
signal.signal(signal.SIGINT, _shutdown)


# --- RTSP server (diagnostic) ---
# serves the muxed MPEG-TS from the 4th tee branch on rtsp://<host>:8554/boat1-processed.
# MediaFactory launches an appsrc → tsparse → rtpmp2tpay chain per-session; a
# shared factory means one internal pipeline feeds all clients, so we keep a
# single appsrc reference and push every appsink sample to it.
rtsp_appsrc_ref = {"src": None}

def on_rtsp_media_unprepared(_media):
    rtsp_appsrc_ref["src"] = None
    print("[rtsp] media unprepared — appsrc cleared")

def on_rtsp_media_configure(_factory, media):
    element = media.get_element()
    appsrc = element.get_by_name("rtsp_src")
    appsrc.set_property("is-live", True)
    appsrc.set_property("format", Gst.Format.TIME)
    appsrc.set_property("do-timestamp", True)
    rtsp_appsrc_ref["src"] = appsrc
    # unprepared is a signal on RTSPMedia (not the factory), so hook it here
    media.connect("unprepared", on_rtsp_media_unprepared)
    print("[rtsp] media configured — appsrc bound")

def on_new_sample(appsink):
    sample = appsink.emit("pull-sample")
    if sample is None:
        return Gst.FlowReturn.OK
    appsrc = rtsp_appsrc_ref["src"]
    if appsrc is not None:
        buf = sample.get_buffer()
        appsrc.emit("push-buffer", buf)
    return Gst.FlowReturn.OK

rtsp_appsink.connect("new-sample", on_new_sample)

rtsp_server = GstRtspServer.RTSPServer()
rtsp_server.set_service("8554")

rtsp_factory = GstRtspServer.RTSPMediaFactory()
rtsp_factory.set_launch(
    "( appsrc name=rtsp_src "
    "caps=video/mpegts,systemstream=true,packetsize=188 "
    "! tsparse set-timestamps=true ! rtpmp2tpay name=pay0 pt=33 )"
)
rtsp_factory.set_shared(True)
rtsp_factory.connect("media-configure", on_rtsp_media_configure)

rtsp_server.get_mount_points().add_factory("/boat1-processed", rtsp_factory)
rtsp_server.attach(None)
print("RTSP server listening on :8554/boat1-processed")


pipeline.set_state(Gst.State.PLAYING)
print("overlay pipeline is running!")

try:
    main_loop.run()
finally:
    pipeline.set_state(Gst.State.NULL)

import signal
from typing import Optional

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstRtspServer", "1.0")
from gi.repository import GLib, Gst

from .branches import (
    AacPassthroughBranch,
    Branch,
    FileRecorderSink,
    H265ToH264OverlayBranch,
    MpegTsMuxBranch,
    RtspBridgeSink,
    SrtListenerSink,
    SrtMpegTsSource,
    SrtPublisherSink,
    TeeFanout,
)
from .config import PipelineConfig
from .mediamtx import MediaMtxWaiter
from .rtsp_server import RtspServer


class OverlayPipeline:
    """Top-level pipeline assembler and runtime owner.

    Builds a Gst.Pipeline from a PipelineConfig, manages the bus watch,
    installs SIGINT/SIGTERM handlers, runs the GLib main loop, and tears
    everything down on exit.
    """

    def __init__(self, config: PipelineConfig) -> None:
        Gst.init(None)
        self.config = config
        self.gst_pipeline = Gst.Pipeline.new("overlay-pipeline")
        self.main_loop = GLib.MainLoop()

        self.source: Optional[SrtMpegTsSource] = None
        self.video: Optional[H265ToH264OverlayBranch] = None
        self.audio: Optional[AacPassthroughBranch] = None
        self.mux: Optional[MpegTsMuxBranch] = None
        self.tee: Optional[TeeFanout] = None
        self.rtsp_server: Optional[RtspServer] = None
        self.sinks: list[Branch] = []

        self._build()

    def _build(self) -> None:
        c = self.config

        self.source = SrtMpegTsSource(c.source)
        self.video = H265ToH264OverlayBranch(c.video)
        self.audio = AacPassthroughBranch(c.audio)
        self.mux = MpegTsMuxBranch(c.mux)
        self.tee = TeeFanout(c.sinks.default_queue)

        self.sinks = []
        if c.sinks.srt_publisher.enabled:
            self.sinks.append(SrtPublisherSink(c.sinks.srt_publisher))
        if c.sinks.file_recorder.enabled:
            self.sinks.append(FileRecorderSink(c.sinks.file_recorder))
        if c.sinks.srt_listener.enabled:
            self.sinks.append(SrtListenerSink(c.sinks.srt_listener))
        if c.sinks.rtsp_bridge.enabled:
            self.rtsp_server = RtspServer(c.rtsp_server)
            self.sinks.append(
                RtspBridgeSink(c.sinks.rtsp_bridge, self.rtsp_server)
            )

        non_sink_branches: list[Branch] = [
            self.source,
            self.video,
            self.audio,
            self.mux,
            self.tee,
        ]
        all_branches: list[Branch] = non_sink_branches + self.sinks

        # Phase 1: build (create + configure elements).
        for b in all_branches:
            b.build()

        # Phase 2: add every element to the pipeline before any linking.
        for b in all_branches:
            b.add_to(self.gst_pipeline)

        # Phase 3: intra-branch linking.
        for b in all_branches:
            b.link_internal()

        # Phase 4: inter-branch static links.
        ok = Gst.PadLinkReturn.OK
        if self.video.output_pad.link(self.mux.request_video_pad()) != ok:
            raise RuntimeError("video → mux link failed")
        if self.audio.output_pad.link(self.mux.request_audio_pad()) != ok:
            raise RuntimeError("audio → mux link failed")
        if self.mux.output_pad.link(self.tee.input_pad) != ok:
            raise RuntimeError("mux → tee link failed")
        for sink in self.sinks:
            self.tee.attach_sink(sink)

        # Phase 5: dynamic-pad wiring (tsdemux → video/audio branches).
        self.source.on_video_pad(self._link_video_pad)
        self.source.on_audio_pad(self._link_audio_pad)

    def _link_video_pad(self, pad: Gst.Pad) -> None:
        assert self.video is not None
        target = self.video.input_pad
        self._link_dynamic(pad, target, "video")

    def _link_audio_pad(self, pad: Gst.Pad) -> None:
        assert self.audio is not None
        target = self.audio.input_pad
        self._link_dynamic(pad, target, "audio")

    @staticmethod
    def _link_dynamic(src_pad: Gst.Pad, sink_pad: Gst.Pad, label: str) -> None:
        if sink_pad.is_linked():
            print(f"[{label} pad-added] target already linked — skipping")
            return
        result = src_pad.link(sink_pad)
        print(f"[{label} pad-added] link result: {result}")

    def run(self) -> None:
        """Wait for the source to be ready, then run the main loop."""
        bus = self.gst_pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._on_message)

        self._install_signal_handlers()

        if self.rtsp_server is not None:
            # The mount path comes from the bridge sink config; pull it out.
            assert self.config.sinks.rtsp_bridge.enabled
            self.rtsp_server.start(self.config.sinks.rtsp_bridge.mount_path)

        MediaMtxWaiter(self.config.source.wait_for).wait()

        print("overlay pipeline is running!")
        self.gst_pipeline.set_state(Gst.State.PLAYING)
        try:
            self.main_loop.run()
        finally:
            self.gst_pipeline.set_state(Gst.State.NULL)

    def _on_message(self, _bus: Gst.Bus, msg: Gst.Message) -> None:
        if msg.type == Gst.MessageType.EOS:
            print("End of stream")
            self.main_loop.quit()
        elif msg.type == Gst.MessageType.ERROR:
            err, debug = msg.parse_error()
            print(f"Error: {err.message} | {debug}")
            self.main_loop.quit()

    def _install_signal_handlers(self) -> None:
        def _shutdown(*_args: object) -> bool:
            print("signal received, stopping pipeline")
            GLib.idle_add(self.main_loop.quit)
            return False

        signal.signal(signal.SIGTERM, _shutdown)
        signal.signal(signal.SIGINT, _shutdown)

from typing import TYPE_CHECKING, Optional

from gi.repository import Gst

from ..config import (
    FileRecorderSinkConfig,
    RtspBridgeSinkConfig,
    SrtListenerSinkConfig,
    SrtPublisherSinkConfig,
)
from .base import Branch, make_element

if TYPE_CHECKING:
    from ..rtsp_server import RtspServer


class SrtPublisherSink(Branch):
    """srtsink that publishes the muxed TS back to MediaMTX."""

    def __init__(
        self,
        config: SrtPublisherSinkConfig,
        name: str = "srt_publisher",
    ) -> None:
        super().__init__(name)
        self.config = config
        self._sink: Optional[Gst.Element] = None

    def build(self) -> None:
        self._sink = self._track(make_element("srtsink", "srt_publisher_sink"))
        self._sink.set_property("uri", self.config.uri)
        self._sink.set_property("latency", self.config.latency_ms)

    def link_internal(self) -> None:
        return

    @property
    def input_pad(self) -> Gst.Pad:
        assert self._sink is not None
        return self._sink.get_static_pad("sink")


class FileRecorderSink(Branch):
    """filesink writing the muxed TS to disk for diagnostic playback."""

    def __init__(
        self,
        config: FileRecorderSinkConfig,
        name: str = "file_recorder",
    ) -> None:
        super().__init__(name)
        self.config = config
        self._sink: Optional[Gst.Element] = None

    def build(self) -> None:
        self._sink = self._track(make_element("filesink", "file_recorder_sink"))
        self._sink.set_property("location", self.config.location)

    def link_internal(self) -> None:
        return

    @property
    def input_pad(self) -> Gst.Pad:
        assert self._sink is not None
        return self._sink.get_static_pad("sink")


class SrtListenerSink(Branch):
    """srtsink in listener mode for OBS to connect directly.

    Builds the URI from the structured config rather than embedding the
    full string, so port / streamid / latency stay validated.
    """

    def __init__(
        self,
        config: SrtListenerSinkConfig,
        name: str = "srt_listener",
    ) -> None:
        super().__init__(name)
        self.config = config
        self._sink: Optional[Gst.Element] = None

    def build(self) -> None:
        c = self.config
        uri = (
            f"srt://:{c.port}?mode=listener"
            f"&streamid={c.stream_id}"
            f"&latency={c.latency_ms}"
        )
        self._sink = self._track(make_element("srtsink", "srt_listener_sink"))
        self._sink.set_property("uri", uri)
        self._sink.set_property("latency", c.latency_ms)
        self._sink.set_property("wait-for-connection", c.wait_for_connection)
        # async=False so srtsink doesn't hold up the pipeline state
        # transition while waiting for an SRT caller.
        self._sink.set_property("async", False)

    def link_internal(self) -> None:
        return

    @property
    def input_pad(self) -> Gst.Pad:
        assert self._sink is not None
        return self._sink.get_static_pad("sink")


class RtspBridgeSink(Branch):
    """appsink that forwards every sample into an in-process RTSP server.

    The RTSP server runs its own per-session pipeline; appsrc lives there,
    not here. We push buffers into whichever appsrc the server currently
    holds, with the server itself handling 'no client connected, no
    appsrc' as a no-op drop.
    """

    def __init__(
        self,
        config: RtspBridgeSinkConfig,
        rtsp_server: "RtspServer",
        name: str = "rtsp_bridge",
    ) -> None:
        super().__init__(name)
        self.config = config
        self.rtsp_server = rtsp_server
        self._appsink: Optional[Gst.Element] = None

    def build(self) -> None:
        self._appsink = self._track(make_element("appsink", "rtsp_bridge_appsink"))
        self._appsink.set_property("emit-signals", True)
        self._appsink.set_property("sync", False)
        self._appsink.set_property("max-buffers", self.config.appsink.max_buffers)
        self._appsink.set_property("drop", self.config.appsink.drop)
        self._appsink.connect("new-sample", self._on_new_sample)

    def link_internal(self) -> None:
        return

    def _on_new_sample(self, appsink: Gst.Element) -> Gst.FlowReturn:
        sample = appsink.emit("pull-sample")
        if sample is None:
            return Gst.FlowReturn.OK
        buf = sample.get_buffer()
        self.rtsp_server.push_buffer(buf)
        return Gst.FlowReturn.OK

    @property
    def input_pad(self) -> Gst.Pad:
        assert self._appsink is not None
        return self._appsink.get_static_pad("sink")

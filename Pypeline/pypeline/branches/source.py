from typing import Callable, Optional

from gi.repository import Gst

from ..config import SourceConfig
from .base import Branch, make_element

PadCallback = Callable[[Gst.Pad], None]


class SrtMpegTsSource(Branch):
    """SRT source feeding tsdemux.

    The branch is the producer side of the pipeline: srtsrc pulls MPEG-TS
    from MediaMTX, tsdemux splits the elementary streams. Both video and
    audio outputs are dynamic — tsdemux emits a 'pad-added' signal once
    it has identified each ES, so callers register their interest with
    on_video_pad / on_audio_pad and we hook the signal centrally.

    This hides the GStreamer pad-lifecycle quirk: the original script's
    pad-added handler had to know about every downstream branch directly;
    here, it dispatches to whichever callbacks were registered.
    """

    def __init__(self, config: SourceConfig, name: str = "source") -> None:
        super().__init__(name)
        self.config = config
        self._srtsrc: Optional[Gst.Element] = None
        self._demux: Optional[Gst.Element] = None
        self._video_callbacks: list[PadCallback] = []
        self._audio_callbacks: list[PadCallback] = []

    def build(self) -> None:
        self._srtsrc = self._track(make_element("srtsrc", "src"))
        self._srtsrc.set_property("uri", self.config.uri)
        self._srtsrc.set_property("latency", self.config.latency_ms)

        self._demux = self._track(make_element("tsdemux", "demux"))
        self._demux.connect("pad-added", self._on_pad_added)

    def link_internal(self) -> None:
        assert self._srtsrc is not None and self._demux is not None
        if not self._srtsrc.link(self._demux):
            raise RuntimeError("srtsrc → tsdemux link failed")

    def on_video_pad(self, callback: PadCallback) -> None:
        """Register a callback invoked once tsdemux exposes a video pad."""
        self._video_callbacks.append(callback)

    def on_audio_pad(self, callback: PadCallback) -> None:
        """Register a callback invoked once tsdemux exposes an audio pad."""
        self._audio_callbacks.append(callback)

    def _on_pad_added(self, _demux: Gst.Element, pad: Gst.Pad) -> None:
        caps = pad.get_current_caps() or pad.query_caps(None)
        caps_str = caps.to_string() if caps else "unknown"
        media_type = ""
        if caps is not None:
            structure = caps.get_structure(0)
            if structure is not None:
                media_type = structure.get_name()

        print(
            f"[{self.name} pad-added] name={pad.get_name()} "
            f"caps={caps_str} media_type={media_type}"
        )

        if media_type.startswith("video/"):
            for cb in self._video_callbacks:
                cb(pad)
        elif media_type.startswith("audio/"):
            for cb in self._audio_callbacks:
                cb(pad)
        else:
            print(f"[{self.name} pad-added] ignoring media_type={media_type}")

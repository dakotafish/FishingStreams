from typing import Optional

from gi.repository import Gst

from ..config import MuxConfig
from .base import Branch, make_element


class MpegTsMuxBranch(Branch):
    """mpegtsmux that combines video + audio into a single MPEG-TS.

    The mux uses request pads for inputs: one per elementary stream. We
    expose request_video_pad() / request_audio_pad() so callers don't
    need to know the underlying sink pad-template name.
    """

    def __init__(self, config: MuxConfig, name: str = "mux") -> None:
        super().__init__(name)
        self.config = config
        self._mux: Optional[Gst.Element] = None

    def build(self) -> None:
        self._mux = self._track(make_element("mpegtsmux", "mux"))
        self._mux.set_property("alignment", self.config.alignment)

    def link_internal(self) -> None:
        # Single element; nothing to link inside the branch.
        return

    def _request_pad(self) -> Gst.Pad:
        assert self._mux is not None, "build() must be called before requesting pads"
        pad = self._mux.request_pad_simple("sink_%d")
        if pad is None:
            raise RuntimeError(f"mpegtsmux refused a request pad on branch {self.name!r}")
        return pad

    def request_video_pad(self) -> Gst.Pad:
        """Request a sink pad for the video elementary stream."""
        return self._request_pad()

    def request_audio_pad(self) -> Gst.Pad:
        """Request a sink pad for the audio elementary stream."""
        return self._request_pad()

    @property
    def output_pad(self) -> Gst.Pad:
        assert self._mux is not None
        return self._mux.get_static_pad("src")

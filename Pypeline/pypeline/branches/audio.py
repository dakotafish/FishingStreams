from typing import Optional

from gi.repository import Gst

from ..config import AudioBranchConfig
from .base import Branch, make_element


class AacPassthroughBranch(Branch):
    """AAC parse → queue, no decode/re-encode.

    Audio comes off tsdemux already in AAC form. We only need aacparse to
    confirm framing and a queue to decouple the audio thread from video.
    """

    def __init__(
        self,
        config: AudioBranchConfig,
        name: str = "audio",
    ) -> None:
        super().__init__(name)
        self.config = config
        self._parse: Optional[Gst.Element] = None
        self._queue: Optional[Gst.Element] = None

    def build(self) -> None:
        self._parse = self._track(make_element("aacparse", "audio_parse"))
        self._queue = self._track(make_element("queue", "audio_queue_out"))

    def link_internal(self) -> None:
        assert self._parse is not None and self._queue is not None
        if not self._parse.link(self._queue):
            raise RuntimeError("aacparse → audio_queue link failed")

    @property
    def input_pad(self) -> Gst.Pad:
        assert self._parse is not None
        return self._parse.get_static_pad("sink")

    @property
    def output_pad(self) -> Gst.Pad:
        assert self._queue is not None
        return self._queue.get_static_pad("src")

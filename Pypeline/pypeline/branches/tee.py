from typing import Optional

from gi.repository import Gst

from ..config import TeeQueueConfig
from .base import Branch, make_element


class TeeFanout(Branch):
    """One-input, N-output fan-out: tee + a queue per attached sink.

    Each downstream sink gets its own queue with the configured limits so
    a slow sink (e.g. SRT listener with no caller connected) cannot
    back-pressure the tee and corrupt the other branches.
    """

    def __init__(
        self,
        queue_config: TeeQueueConfig,
        name: str = "tee",
    ) -> None:
        super().__init__(name)
        self.queue_config = queue_config
        self._tee: Optional[Gst.Element] = None
        self._pipeline: Optional[Gst.Pipeline] = None
        self._sink_count = 0

    def build(self) -> None:
        self._tee = self._track(make_element("tee", "tee"))

    def link_internal(self) -> None:
        # Tee has no internal links until sinks attach.
        return

    def add_to(self, pipeline: Gst.Pipeline) -> None:
        super().add_to(pipeline)
        # Remember the pipeline so attach_sink() can parent the queues it
        # creates lazily (one per sink).
        self._pipeline = pipeline

    def attach_sink(self, sink: Branch) -> None:
        """Wire a sink branch into the fanout: tee → queue → sink.

        The sink must already have been built and added to the pipeline.
        A queue with the configured limits is created and added inline.
        """
        assert self._tee is not None and self._pipeline is not None, (
            "TeeFanout.add_to(pipeline) must be called before attach_sink()"
        )
        if sink.input_pad is None:
            raise RuntimeError(
                f"sink branch {sink.name!r} has no input_pad; cannot attach to tee"
            )

        idx = self._sink_count
        self._sink_count += 1

        queue = make_element("queue", f"tee_queue_{sink.name}")
        queue.set_property("max-size-buffers", self.queue_config.max_buffers)
        queue.set_property(
            "max-size-time", self.queue_config.max_time_seconds * Gst.SECOND
        )
        queue.set_property("max-size-bytes", self.queue_config.max_bytes)

        if not self._pipeline.add(queue):
            raise RuntimeError(f"failed to add tee queue for {sink.name!r}")
        queue.sync_state_with_parent()

        # tee request pad → queue sink pad
        tee_src = self._tee.request_pad_simple("src_%u")
        if tee_src is None:
            raise RuntimeError(f"tee refused request pad #{idx} for {sink.name!r}")
        queue_sink = queue.get_static_pad("sink")
        if tee_src.link(queue_sink) != Gst.PadLinkReturn.OK:
            raise RuntimeError(f"tee → queue link failed for {sink.name!r}")

        # queue src pad → sink input pad
        if queue.get_static_pad("src").link(sink.input_pad) != Gst.PadLinkReturn.OK:
            raise RuntimeError(f"queue → {sink.name!r} link failed")

    @property
    def input_pad(self) -> Gst.Pad:
        assert self._tee is not None
        return self._tee.get_static_pad("sink")

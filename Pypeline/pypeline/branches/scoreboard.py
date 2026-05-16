"""ScoreboardOverlayBranch — cairooverlay driven by ScoreboardRenderer.

GStreamer glue only. All pixel-level drawing is delegated to the renderer
in ``pypeline/overlays/scoreboard_renderer.py``, which has zero GStreamer
imports and is therefore independently testable.

The branch is a single-element chain: ``cairooverlay``. Sits between
``VideoDecodeBranch`` (BGRA out) and ``VideoEncodeBranch`` (consumes any
videoconvert-friendly raw format, including BGRA).
"""
from typing import Optional

from gi.repository import Gst

from ..config import ScoreboardConfig
from ..overlays.scoreboard_renderer import ScoreboardRenderer, ScoreboardState
from .base import Branch, make_element


class ScoreboardOverlayBranch(Branch):
    """cairooverlay branch: BGRA in → scoreboard drawn → BGRA out.

    Scroll position is advanced from the cairooverlay buffer timestamp, so
    the scroll speed is frame-rate-independent and immune to pipeline stalls.
    """

    def __init__(
        self,
        config: ScoreboardConfig,
        name: str = "scoreboard",
    ) -> None:
        super().__init__(name)
        self.config = config
        self._overlay: Optional[Gst.Element] = None
        self._renderer = ScoreboardRenderer(config)

        self._x_offset: float = 0.0
        self._last_ts_ns: Optional[int] = None
        self._text_block_width: Optional[float] = None

    def build(self) -> None:
        self._overlay = self._track(make_element("cairooverlay", "scoreboard_cairo"))
        if self.config.enabled and self.config.anglers:
            self._overlay.connect("draw", self._on_draw)

    def link_internal(self) -> None:
        # Single element; nothing to link inside the branch.
        return

    @property
    def input_pad(self) -> Gst.Pad:
        assert self._overlay is not None, "build() must be called before input_pad"
        return self._overlay.get_static_pad("sink")

    @property
    def output_pad(self) -> Gst.Pad:
        assert self._overlay is not None, "build() must be called before output_pad"
        return self._overlay.get_static_pad("src")

    def _on_draw(
        self,
        overlay: Gst.Element,
        ctx: object,  # cairo.Context — typed loose to avoid host import requirement
        timestamp_ns: int,
        _duration_ns: int,
    ) -> None:
        """Called by cairooverlay once per frame on the streaming thread."""
        pad = overlay.get_static_pad("sink")
        caps = pad.get_current_caps()
        if caps is None:
            return
        s = caps.get_structure(0)
        ok_w, frame_width = s.get_int("width")
        ok_h, frame_height = s.get_int("height")
        if not ok_w or not ok_h:
            return

        if self._text_block_width is None:
            self._text_block_width = self._renderer.measure_text_width(ctx)
            print(
                f"[{self.name}] text block measured: "
                f"{self._text_block_width:.1f}px @ {frame_width}x{frame_height}"
            )

        if self._last_ts_ns is not None and timestamp_ns > self._last_ts_ns:
            dt_sec = (timestamp_ns - self._last_ts_ns) / 1e9
        else:
            dt_sec = 0.0
        self._last_ts_ns = timestamp_ns

        self._x_offset += self.config.scroll_speed_px_per_sec * dt_sec
        if self._text_block_width and self._x_offset >= self._text_block_width:
            self._x_offset -= self._text_block_width

        self._renderer.draw(
            ctx, frame_width, frame_height, ScoreboardState(x_offset=self._x_offset)
        )

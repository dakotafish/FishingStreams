"""CompositorBranch — alpha-composites main video + browser overlay.

Sits between ``VideoDecodeBranch`` (BGRA out) and ``ScoreboardOverlayBranch``
(BGRA in, via cairooverlay) when ``browser_overlay.enabled`` is true.

Element chain:

    compositor → videoconvert → capsfilter(BGRA)

The compositor has two request pads:

    sink_0  zorder=0   main video (background)
    sink_1  zorder=1   browser overlay (foreground, alpha=1.0)

zorder and alpha are properties on the ``GstCompositorPad`` (the request pad
object itself), not on the compositor element — this is the standard pattern
documented in the GStreamer compositor reference.

Compositor's negotiated output format depends on its inputs; the downstream
``cairooverlay`` strictly requires BGRA on little-endian, so we videoconvert +
capsfilter to BGRA before exposing ``output_pad``. This keeps the existing
scoreboard chain unchanged.

The compositor ``background`` property is set to BLACK (value 1) so any pixel
without a contributing input renders black instead of garbage.
"""
from typing import Optional

from gi.repository import Gst

from ..config import BrowserOverlayConfig
from .base import Branch, make_element


class CompositorBranch(Branch):
    """compositor with two request-pad inputs and a BGRA output."""

    def __init__(
        self,
        config: BrowserOverlayConfig,
        name: str = "compositor",
    ) -> None:
        super().__init__(name)
        self.config = config

        self._comp: Optional[Gst.Element] = None
        self._convert: Optional[Gst.Element] = None
        self._caps_bgra: Optional[Gst.Element] = None

    def build(self) -> None:
        self._comp = self._track(make_element("compositor", "compositor"))
        # GstCompositorBackground: 0=checker, 1=black, 2=white, 3=transparent.
        # Black is the safe default — any uncovered region of the output frame
        # falls back to black rather than the checker pattern.
        self._comp.set_property("background", 1)

        self._convert = self._track(make_element("videoconvert", "compositor_convert_bgra"))

        self._caps_bgra = self._track(make_element("capsfilter", "compositor_caps_bgra"))
        self._caps_bgra.set_property(
            "caps", Gst.Caps.from_string("video/x-raw,format=BGRA")
        )

    def link_internal(self) -> None:
        chain = [self._comp, self._convert, self._caps_bgra]
        for upstream, downstream in zip(chain, chain[1:]):
            if not upstream.link(downstream):
                raise RuntimeError(
                    f"link failed: {upstream.get_name()} → {downstream.get_name()}"
                )

    def _request_pad(self, zorder: int, alpha: float) -> Gst.Pad:
        assert self._comp is not None, "build() must be called before requesting pads"
        pad = self._comp.request_pad_simple("sink_%u")
        if pad is None:
            raise RuntimeError(f"compositor refused a request pad on branch {self.name!r}")
        pad.set_property("zorder", zorder)
        pad.set_property("alpha", alpha)
        return pad

    def request_video_pad(self) -> Gst.Pad:
        """Request the main-video input pad (sink_0, zorder=0)."""
        return self._request_pad(zorder=0, alpha=1.0)

    def request_overlay_pad(self) -> Gst.Pad:
        """Request the browser-overlay input pad (sink_1, zorder=1, alpha=1.0)."""
        return self._request_pad(zorder=1, alpha=1.0)

    @property
    def output_pad(self) -> Gst.Pad:
        assert self._caps_bgra is not None, "build() must be called before output_pad"
        return self._caps_bgra.get_static_pad("src")

"""BrowserOverlaySourceBranch — captures an in-container browser via ximagesrc.

Source-only branch (no upstream input). Reads the Xvfb display where Chromium
is rendering ``catch-counter.html`` and emits ``RGBA`` frames at the configured
framerate, with the chroma-key green keyed out so the compositor sees real
alpha. The downstream consumer is the ``CompositorBranch`` sink_1 pad.

Element chain:

    ximagesrc(use-damage=false) → videoconvert → alpha(method=green)
        → videoconvert → capsfilter(RGBA, fps) → queue

Why chroma keying instead of CSS transparency:
    ``--enable-transparent-visuals`` requires xcompmgr to publish the
    _NET_WM_CM_S0 selection AND a transparent viewport background. Chromium's
    viewport background defaults to opaque white in non-headless mode and
    there is no command-line flag that overrides it. The HTML overlay
    therefore renders against a #00ff00 background (set in the pipeline
    copy of catch-counter.html — the BrowserSources copy used by OBS stays
    transparent), and the ``alpha`` element keys that green out here.

``use-damage=false`` forces ximagesrc to emit full frames on every tick
rather than only changed regions, which the compositor requires.
"""
from typing import Optional

from gi.repository import Gst

from ..config import BrowserOverlayConfig
from .base import Branch, make_element


class BrowserOverlaySourceBranch(Branch):
    """Xvfb screen → RGBA frames → output queue."""

    def __init__(
        self,
        config: BrowserOverlayConfig,
        name: str = "browser_overlay",
    ) -> None:
        super().__init__(name)
        self.config = config

        self._src: Optional[Gst.Element] = None
        self._convert_pre: Optional[Gst.Element] = None
        self._alpha: Optional[Gst.Element] = None
        self._convert_post: Optional[Gst.Element] = None
        self._caps_rgba: Optional[Gst.Element] = None
        self._queue: Optional[Gst.Element] = None

    def build(self) -> None:
        self._src = self._track(make_element("ximagesrc", "browser_overlay_ximagesrc"))
        self._src.set_property("display-name", self.config.display_name)
        self._src.set_property("use-damage", False)
        self._src.set_property("show-pointer", False)
        self._src.set_property("startx", 0)
        self._src.set_property("starty", 0)
        self._src.set_property("endx", self.config.capture_endx)
        self._src.set_property("endy", self.config.capture_endy)

        self._convert_pre = self._track(make_element("videoconvert", "browser_overlay_convert_pre"))

        # alpha method=green: keys out the #00ff00 background of the
        # in-container catch-counter.html. Output has real per-pixel alpha
        # so the downstream compositor can blend the overlay correctly.
        self._alpha = self._track(make_element("alpha", "browser_overlay_chroma_key"))
        self._alpha.set_property("method", "green")

        self._convert_post = self._track(make_element("videoconvert", "browser_overlay_convert_post"))

        self._caps_rgba = self._track(make_element("capsfilter", "browser_overlay_caps_rgba"))
        self._caps_rgba.set_property(
            "caps",
            Gst.Caps.from_string(
                f"video/x-raw,format=RGBA,framerate={self.config.framerate}/1"
            ),
        )

        # Decouples ximagesrc's clock from the compositor so a slow compositor
        # cannot stall screen capture.
        self._queue = self._track(make_element("queue", "browser_overlay_queue"))

    def link_internal(self) -> None:
        chain = [self._src, self._convert_pre, self._alpha, self._convert_post, self._caps_rgba, self._queue]
        for upstream, downstream in zip(chain, chain[1:]):
            if not upstream.link(downstream):
                raise RuntimeError(
                    f"link failed: {upstream.get_name()} → {downstream.get_name()}"
                )

    @property
    def output_pad(self) -> Gst.Pad:
        assert self._queue is not None, "build() must be called before output_pad"
        return self._queue.get_static_pad("src")

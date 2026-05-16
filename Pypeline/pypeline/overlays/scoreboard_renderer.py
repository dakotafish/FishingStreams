"""Pure-Python Cairo renderer for the scrolling scoreboard strip.

No GStreamer imports. Receives a cairo.Context and a scroll-state snapshot;
draws the strip. The renderer is stateless across calls — given the same
inputs it produces identical output, which makes it trivially testable with
``cairo.ImageSurface`` alone (no GStreamer environment needed).

The owning ``ScoreboardOverlayBranch`` is responsible for advancing
``ScoreboardState.x_offset`` between frames using the cairooverlay buffer
timestamp; the renderer just paints what it's told.
"""
from dataclasses import dataclass
from typing import TYPE_CHECKING

try:
    import cairo
except ImportError:  # pragma: no cover — pycairo absent on macOS host
    cairo = None  # type: ignore[assignment]

if TYPE_CHECKING:
    import cairo as _cairo  # noqa: F401  (typing-only re-import)

from ..config.scoreboard import AnglerEntry, ScoreboardConfig


@dataclass(frozen=True)
class ScoreboardState:
    """Snapshot of scroll position passed to the renderer each frame."""

    x_offset: float  # current pixel offset; the leading copy starts at frame_w - x_offset


class ScoreboardRenderer:
    """Draws a horizontally scrolling scoreboard strip onto a Cairo context."""

    def __init__(self, config: ScoreboardConfig) -> None:
        self.config = config
        self._ticker_text: str = self._build_ticker_text(
            config.anglers, config.entry_separator
        )

    @staticmethod
    def _build_ticker_text(entries: list[AnglerEntry], separator: str) -> str:
        """Flatten the angler list into a single repeating scroll string.

        Format: ``#1  D. Johnson  22pts   |   #2  E. Harold  20pts   | ...``.
        Trailing separator is appended so the loop seam is invisible.
        """
        if not entries:
            return ""
        parts = [f"#{e.rank}  {e.name}  {e.points:g}pts" for e in entries]
        return separator.join(parts) + separator

    def measure_text_width(self, ctx: "cairo.Context") -> float:
        """Return the cursor-advance width of one full ticker string.

        Caller uses this to know when to wrap ``state.x_offset``. Returns
        ``x_advance`` rather than ``width`` so trailing whitespace in the
        separator (which advances the pen but does not ink) is included —
        otherwise the wrap collapses the trailing gap and the seam is visible.
        """
        self._apply_font(ctx)
        return ctx.text_extents(self._ticker_text).x_advance

    def draw(
        self,
        ctx: "cairo.Context",
        frame_width: int,
        frame_height: int,
        state: ScoreboardState,
    ) -> None:
        """Paint the scoreboard strip for one frame.

        Args:
            ctx: Cairo context for the current frame (origin at top-left).
            frame_width: Frame width in pixels.
            frame_height: Frame height in pixels.
            state: Current scroll position.
        """
        cfg = self.config
        strip_y = frame_height - cfg.strip_height_px

        ctx.save()
        ctx.set_source_rgba(0.0, 0.0, 0.0, cfg.background_alpha)
        ctx.rectangle(0, strip_y, frame_width, cfg.strip_height_px)
        ctx.fill()
        ctx.restore()

        self._apply_font(ctx)
        extents = ctx.text_extents(self._ticker_text)
        # Vertically centre the glyph bounding box: top of box = strip top + (strip - h)/2.
        # show_text() draws baseline-up, so the baseline y solves to:
        #     text_y = strip_y + strip_h/2 - y_bearing - height/2
        # (y_bearing is negative for ascenders, so this subtracts upward).
        text_y = (
            strip_y + cfg.strip_height_px / 2.0 - extents.y_bearing - extents.height / 2.0
        )

        ctx.save()
        ctx.rectangle(0, strip_y, frame_width, cfg.strip_height_px)
        ctx.clip()

        r, g, b = cfg.text_color_rgb
        ctx.set_source_rgba(r, g, b, 1.0)

        # Draw two consecutive copies so the wrap point is invisible: as copy 1
        # exits the left edge, copy 2 has already entered from the right.
        # Spacing uses x_advance (cursor-advance, includes trailing whitespace)
        # so the inter-copy gap matches the trailing separator in the string.
        advance = extents.x_advance
        x = frame_width - state.x_offset
        for _ in range(2):
            ctx.move_to(x, text_y)
            ctx.show_text(self._ticker_text)
            x += advance

        ctx.restore()

    def _apply_font(self, ctx: "cairo.Context") -> None:
        cfg = self.config
        ctx.select_font_face(
            cfg.font_family,
            cairo.FONT_SLANT_NORMAL,
            cairo.FONT_WEIGHT_NORMAL,
        )
        # cairooverlay surfaces are 1 unit = 1 pixel, so convert pt → px at 96 dpi.
        ctx.set_font_size(cfg.font_size_pt * 96.0 / 72.0)

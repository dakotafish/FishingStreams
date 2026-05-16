from pydantic import BaseModel, ConfigDict, Field


class AnglerEntry(BaseModel):
    """A single row in the scrolling scoreboard ticker."""

    model_config = ConfigDict(extra="forbid")

    rank: int = Field(..., description="Rank position (1 = first place).", ge=1)
    name: str = Field(..., description="Angler display name.")
    points: float = Field(..., description="Current point total.", ge=0)


class ScoreboardConfig(BaseModel):
    """Horizontally scrolling scoreboard burned into the video stream via cairooverlay.

    The branch is always wired into the video chain when this config is present
    (cairooverlay always sits between decode and encode). ``enabled=False``
    keeps the element in the pipeline but skips connecting the draw signal,
    so the overlay becomes a transparent passthrough.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    anglers: list[AnglerEntry] = Field(
        default_factory=list,
        description="Ordered list of angler entries rendered in the ticker.",
    )
    strip_height_px: int = Field(
        60,
        description="Height of the bottom scoreboard strip in pixels.",
        gt=0,
    )
    background_alpha: float = Field(
        0.65,
        description="Alpha of the semi-transparent black background (0.0 invisible — 1.0 opaque).",
        ge=0.0,
        le=1.0,
    )
    font_size_pt: float = Field(
        32.0,
        description="Font size in points for the ticker text.",
        gt=0,
    )
    font_family: str = Field(
        "DejaVu Sans",
        description="Cairo font family. DejaVu Sans is installed in the Pypeline Docker image.",
    )
    scroll_speed_px_per_sec: float = Field(
        120.0,
        description="Right-to-left scroll speed in pixels per second.",
        gt=0,
    )
    entry_separator: str = Field(
        "   |   ",
        description="String inserted between rendered angler entries.",
    )
    text_color_rgb: tuple[float, float, float] = Field(
        (1.0, 1.0, 1.0),
        description="RGB text color, each component 0.0–1.0.",
    )

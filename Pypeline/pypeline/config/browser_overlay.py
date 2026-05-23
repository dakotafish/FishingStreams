from pydantic import BaseModel, ConfigDict, Field


class BrowserOverlayConfig(BaseModel):
    """Headless browser overlay composited into the video chain.

    When ``enabled``, the pipeline grows two branches:

    - ``BrowserOverlaySourceBranch``: ximagesrc captures the in-container
      Xvfb display where Chromium is rendering ``catch-counter.html``.
    - ``CompositorBranch``: alpha-composites the captured overlay over the
      decoded main video, then emits BGRA for the existing scoreboard chain.

    Xvfb resolution and the Chromium URL are owned by ``Pypeline/supervisord.conf``,
    not by this YAML — there is no point in exposing them per-boat when the
    same Docker image runs every boat. The fields here only configure
    ``ximagesrc`` behaviour.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(
        False,
        description=(
            "Opt-in. When false, none of the browser-overlay branches are "
            "instantiated and the video chain reverts to the direct "
            "video_decode → scoreboard link."
        ),
    )
    display_name: str = Field(
        ":99",
        description=(
            "X11 display ximagesrc reads from. Must match Xvfb in "
            "Pypeline/supervisord.conf."
        ),
    )
    framerate: int = Field(
        30,
        description=(
            "ximagesrc capture framerate. Can be set below the main stream "
            "framerate to reduce CPU when overlay content changes slowly."
        ),
        gt=0,
        le=60,
    )
    capture_endx: int = Field(
        1919,
        description="ximagesrc endx (inclusive); typically width - 1.",
        ge=0,
    )
    capture_endy: int = Field(
        1079,
        description="ximagesrc endy (inclusive); typically height - 1.",
        ge=0,
    )

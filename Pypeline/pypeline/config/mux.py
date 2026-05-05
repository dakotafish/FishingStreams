from pydantic import BaseModel, ConfigDict, Field


class MuxConfig(BaseModel):
    """mpegtsmux settings.

    The mux re-packs the re-encoded H.264 video and passthrough AAC audio
    back into an MPEG-TS stream that fans out to every sink.
    """

    model_config = ConfigDict(extra="forbid")

    alignment: int = Field(
        7,
        description=(
            "TS packets per output buffer. 7 packs 7*188 = 1316 bytes — "
            "the canonical SRT/UDP payload size. Without this, mpegtsmux "
            "emits 1-packet buffers; Docker UDP forwarding then drops or "
            "reorders them, and VLC loses SPS/PPS on IDRs over SRT."
        ),
        ge=1,
    )

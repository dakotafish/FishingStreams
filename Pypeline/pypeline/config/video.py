from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EncoderConfig(BaseModel):
    """x264enc settings.

    The defaults reproduce the original pipeline's H.264 re-encode profile,
    which is tuned for low-latency live HLS / OBS / VLC consumption.
    """

    model_config = ConfigDict(extra="forbid")

    bitrate_kbps: int = Field(
        5000,
        description="kbps. Match Moblin's 5 Mbps source bitrate so the re-encode is roughly transparent.",
        gt=0,
    )
    keyframe_interval: int = Field(
        30,
        description=(
            "Max GOP size in frames. 1s @ 30fps gives mid-stream joiners "
            "(OBS/VLC) a fast lock-on to the next IDR."
        ),
        gt=0,
    )
    bframes: int = Field(
        0,
        description=(
            "B-frame count. zerolatency tuning requires 0; B-frames also "
            "break HLS join behaviour for some players."
        ),
        ge=0,
    )
    tune: Literal["zerolatency"] = Field(
        "zerolatency",
        description="x264enc tune preset. Only zerolatency is supported here.",
    )
    speed_preset: Literal[
        "ultrafast",
        "superfast",
        "veryfast",
        "faster",
        "fast",
        "medium",
    ] = Field(
        "veryfast",
        description="x264enc speed-preset. veryfast hits 5 Mbps comfortably on the boat hardware.",
    )


class VideoDecodeBranchConfig(BaseModel):
    """H.265 decode → raw BGRA. Output format is fixed by the branch.

    The branch outputs BGRA because cairooverlay (the next stage) requires
    ``video/x-raw,format=BGRA`` on little-endian. No tunables today; exists
    as a named extension point so future decode-side knobs (HW decode,
    deinterlace, color range) have an obvious home.
    """

    model_config = ConfigDict(extra="forbid")


class VideoEncodeBranchConfig(BaseModel):
    """Raw video → H.264 with an SVG overlay in the middle.

    Element chain (inside the branch):

        videoconvert → rsvgoverlay → videoconvert →
        capsfilter(I420) → x264enc → h264parse →
        capsfilter(byte-stream/au) → queue
    """

    model_config = ConfigDict(extra="forbid")

    overlay_path: str = Field(
        "/overlays/placeholder.svg",
        description="Filesystem path to the SVG that rsvgoverlay renders on top of every frame.",
    )
    encoder: EncoderConfig = Field(
        default_factory=EncoderConfig,
        description="x264enc settings for the H.264 re-encode.",
    )
    raw_format: Literal["I420"] = Field(
        "I420",
        description=(
            "Raw video format forced before x264enc. I420 (4:2:0) so "
            "x264enc picks Main/High profile, not High 4:4:4 — the latter "
            "is undecodable by HLS clients and OBS."
        ),
    )
    h264_stream_format: Literal["byte-stream"] = Field(
        "byte-stream",
        description=(
            "H264 stream format after h264parse. byte-stream + alignment=au "
            "ensures mpegtsmux packs whole access units (with in-band SPS/PPS) "
            "into PES; AVC alignment hides SPS/PPS out-of-band where VLC misses them."
        ),
    )
    h264_alignment: Literal["au"] = Field(
        "au",
        description="Access-unit alignment after h264parse, paired with byte-stream format.",
    )
    h264_config_interval: int = Field(
        -1,
        description=(
            "h264parse config-interval property. -1 re-inserts SPS/PPS on "
            "every IDR so mid-stream joiners always see them."
        ),
    )

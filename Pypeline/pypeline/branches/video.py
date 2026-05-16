"""Video decode and encode branches.

Originally a single ``H265ToH264OverlayBranch``; split so a Cairo overlay
branch can sit between decode (raw BGRA out) and encode (raw video in,
H.264 out).

Element chain across the three branches:

    VideoDecodeBranch:
        h265parse → avdec_h265 → videoconvert → capsfilter(BGRA)

    ScoreboardOverlayBranch (in branches/scoreboard.py):
        cairooverlay

    VideoEncodeBranch:
        videoconvert → rsvgoverlay → videoconvert →
        capsfilter(I420) → x264enc → h264parse →
        capsfilter(byte-stream/au) → queue
"""
from typing import Optional

from gi.repository import Gst

from ..config import VideoDecodeBranchConfig, VideoEncodeBranchConfig
from .base import Branch, make_element


class VideoDecodeBranch(Branch):
    """H.265 in → raw BGRA out.

    Outputs BGRA so the downstream cairooverlay (which requires BGRA on
    little-endian) can attach without an extra format-conversion pair.
    """

    def __init__(
        self,
        config: VideoDecodeBranchConfig,
        name: str = "video_decode",
    ) -> None:
        super().__init__(name)
        self.config = config

        self._parse_in: Optional[Gst.Element] = None
        self._decode: Optional[Gst.Element] = None
        self._convert: Optional[Gst.Element] = None
        self._caps_bgra: Optional[Gst.Element] = None

    def build(self) -> None:
        self._parse_in = self._track(make_element("h265parse", "video_parse_in"))
        self._decode = self._track(make_element("avdec_h265", "video_avdec_h265"))
        self._convert = self._track(make_element("videoconvert", "video_convert_to_bgra"))

        self._caps_bgra = self._track(make_element("capsfilter", "video_caps_bgra"))
        self._caps_bgra.set_property(
            "caps", Gst.Caps.from_string("video/x-raw,format=BGRA")
        )

    def link_internal(self) -> None:
        chain = [self._parse_in, self._decode, self._convert, self._caps_bgra]
        for upstream, downstream in zip(chain, chain[1:]):
            if not upstream.link(downstream):
                raise RuntimeError(
                    f"link failed: {upstream.get_name()} → {downstream.get_name()}"
                )

    @property
    def input_pad(self) -> Gst.Pad:
        assert self._parse_in is not None, "build() must be called before input_pad"
        return self._parse_in.get_static_pad("sink")

    @property
    def output_pad(self) -> Gst.Pad:
        assert self._caps_bgra is not None, "build() must be called before output_pad"
        return self._caps_bgra.get_static_pad("src")


class VideoEncodeBranch(Branch):
    """Raw video in → H.264 MPEG-TS-ready out, with the existing SVG overlay.

    Accepts whatever raw format upstream provides (BGRA from the scoreboard,
    or anything ``videoconvert`` can adapt). The first ``videoconvert`` feeds
    rsvgoverlay an RGBA-family format; the second converts back to I420 for
    x264enc.
    """

    def __init__(
        self,
        config: VideoEncodeBranchConfig,
        name: str = "video_encode",
    ) -> None:
        super().__init__(name)
        self.config = config

        self._convert_pre: Optional[Gst.Element] = None
        self._overlay: Optional[Gst.Element] = None
        self._convert_post: Optional[Gst.Element] = None
        self._caps_i420: Optional[Gst.Element] = None
        self._encode: Optional[Gst.Element] = None
        self._parse_out: Optional[Gst.Element] = None
        self._caps_h264: Optional[Gst.Element] = None
        self._queue_out: Optional[Gst.Element] = None

    def build(self) -> None:
        self._convert_pre = self._track(make_element("videoconvert", "video_convert_pre"))

        self._overlay = self._track(make_element("rsvgoverlay", "video_svg_overlay"))
        self._overlay.set_property("location", self.config.overlay_path)

        self._convert_post = self._track(make_element("videoconvert", "video_convert_post"))

        self._caps_i420 = self._track(make_element("capsfilter", "video_caps_i420"))
        self._caps_i420.set_property(
            "caps",
            Gst.Caps.from_string(f"video/x-raw,format={self.config.raw_format}"),
        )

        enc = self.config.encoder
        self._encode = self._track(make_element("x264enc", "video_encode"))
        self._encode.set_property("tune", enc.tune)
        self._encode.set_property("speed-preset", enc.speed_preset)
        self._encode.set_property("bitrate", enc.bitrate_kbps)
        self._encode.set_property("key-int-max", enc.keyframe_interval)
        self._encode.set_property("bframes", enc.bframes)

        self._parse_out = self._track(make_element("h264parse", "video_parse_out"))
        self._parse_out.set_property("config-interval", self.config.h264_config_interval)

        self._caps_h264 = self._track(make_element("capsfilter", "video_caps_h264"))
        self._caps_h264.set_property(
            "caps",
            Gst.Caps.from_string(
                f"video/x-h264,stream-format={self.config.h264_stream_format},"
                f"alignment={self.config.h264_alignment}"
            ),
        )

        self._queue_out = self._track(make_element("queue", "video_queue_out"))

    def link_internal(self) -> None:
        chain = [
            self._convert_pre,
            self._overlay,
            self._convert_post,
            self._caps_i420,
            self._encode,
            self._parse_out,
            self._caps_h264,
            self._queue_out,
        ]
        for upstream, downstream in zip(chain, chain[1:]):
            if not upstream.link(downstream):
                raise RuntimeError(
                    f"link failed: {upstream.get_name()} → {downstream.get_name()}"
                )

    @property
    def input_pad(self) -> Gst.Pad:
        assert self._convert_pre is not None, "build() must be called before input_pad"
        return self._convert_pre.get_static_pad("sink")

    @property
    def output_pad(self) -> Gst.Pad:
        assert self._queue_out is not None, "build() must be called before output_pad"
        return self._queue_out.get_static_pad("src")

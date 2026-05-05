from typing import Optional

from gi.repository import Gst

from ..config import VideoBranchConfig
from .base import Branch, make_element


class H265ToH264OverlayBranch(Branch):
    """H.265 in → SVG overlay → H.264 out.

    Element chain:

        h265parse → avdec_h265 → videoconvert → rsvgoverlay →
        videoconvert → capsfilter(I420) → x264enc → h264parse →
        capsfilter(byte-stream/au) → queue

    The two videoconverts and the I420 capsfilter sit either side of the
    overlay because rsvgoverlay needs an RGBA-friendly format, while
    x264enc must consume I420 (4:2:0) to pick a downstream-decodable
    profile. The post-encode capsfilter forces byte-stream + AU alignment
    so mpegtsmux packs whole access units (with in-band SPS/PPS) into PES.
    """

    def __init__(
        self,
        config: VideoBranchConfig,
        name: str = "video",
    ) -> None:
        super().__init__(name)
        self.config = config

        self._parse_in: Optional[Gst.Element] = None
        self._decode: Optional[Gst.Element] = None
        self._convert_pre: Optional[Gst.Element] = None
        self._overlay: Optional[Gst.Element] = None
        self._convert_post: Optional[Gst.Element] = None
        self._caps_i420: Optional[Gst.Element] = None
        self._encode: Optional[Gst.Element] = None
        self._parse_out: Optional[Gst.Element] = None
        self._caps_h264: Optional[Gst.Element] = None
        self._queue_out: Optional[Gst.Element] = None

    def build(self) -> None:
        self._parse_in = self._track(make_element("h265parse", "video_parse_in"))
        self._decode = self._track(make_element("avdec_h265", "video_decode"))
        self._convert_pre = self._track(make_element("videoconvert", "video_convert_pre"))

        self._overlay = self._track(make_element("rsvgoverlay", "video_overlay"))
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
            self._parse_in,
            self._decode,
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
        assert self._parse_in is not None, "build() must be called before input_pad"
        return self._parse_in.get_static_pad("sink")

    @property
    def output_pad(self) -> Gst.Pad:
        assert self._queue_out is not None, "build() must be called before output_pad"
        return self._queue_out.get_static_pad("src")

from pydantic import BaseModel, ConfigDict, Field


class RtspServerConfig(BaseModel):
    """In-process GstRtspServer settings.

    Only consulted when SinksConfig.rtsp_bridge.enabled is True.
    """

    model_config = ConfigDict(extra="forbid")

    port: int = Field(
        8554,
        description="TCP port the RTSP server listens on inside the container.",
        ge=1,
        le=65535,
    )
    factory_launch: str = Field(
        (
            "( appsrc name=rtsp_src "
            "caps=video/mpegts,systemstream=true,packetsize=188 "
            "! tsparse set-timestamps=true ! rtpmp2tpay name=pay0 pt=33 )"
        ),
        description=(
            "gst-launch syntax for the per-session media pipeline. The "
            "appsrc named 'rtsp_src' is the bridge target; pay0 is the "
            "RTP payloader exposed to clients."
        ),
    )
    factory_shared: bool = Field(
        True,
        description=(
            "If True, one internal pipeline feeds all clients. Required "
            "for the appsink->appsrc bridge: we keep a single appsrc "
            "reference and push every appsink sample to it."
        ),
    )

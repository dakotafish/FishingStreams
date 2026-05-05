from pydantic import BaseModel, ConfigDict, Field


class TeeQueueConfig(BaseModel):
    """Per-branch queue limits attached to every tee output.

    Generous limits stop a slow downstream from back-pressuring the tee,
    which would corrupt the other (faster) branches. 10s of video at
    5 Mbps is roughly 6 MB, so 16 MiB is comfortable headroom.
    """

    model_config = ConfigDict(extra="forbid")

    max_buffers: int = Field(
        0,
        description="Max queued buffers (0 = unlimited).",
        ge=0,
    )
    max_time_seconds: int = Field(
        10,
        description="Max queued time in seconds; converted to ns at apply time.",
        ge=0,
    )
    max_bytes: int = Field(
        16 * 1024 * 1024,
        description="Max queued bytes; 16 MiB matches the original sizing.",
        ge=0,
    )


class SrtPublisherSinkConfig(BaseModel):
    """Publish the muxed MPEG-TS back to MediaMTX over SRT.

    This is what feeds MediaMTX's HLS preview and any future MediaMTX-fronted
    consumers.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    uri: str = Field(
        ...,
        description=(
            "SRT publish URI, e.g. "
            "srt://mediamtx:8890?streamid=publish:boat1-processed."
        ),
    )
    latency_ms: int = Field(
        200,
        description="srtsink latency property in ms.",
        ge=0,
    )


class FileRecorderSinkConfig(BaseModel):
    """Diagnostic filesink: writes the same bytes as the SRT publisher.

    Useful for offline ffprobe / VLC playback when SRT/HLS misbehaves.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    location: str = Field(
        "/logs/output.ts",
        description="Filesystem path the muxed TS is written to.",
    )


class SrtListenerSinkConfig(BaseModel):
    """SRT listener for OBS to connect directly, bypassing MediaMTX.

    MediaMTX re-serves Moblin's H.265 fine but corrupts our H.264 re-serve,
    so OBS connects here as a caller instead.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    port: int = Field(
        8891,
        description="UDP port the listener binds to inside the container.",
        ge=1,
        le=65535,
    )
    stream_id: str = Field(
        "boat1-processed",
        description="SRT streamid the caller (OBS) supplies on connect.",
    )
    latency_ms: int = Field(
        2000,
        description=(
            "SRT retransmission window. 200ms caused 6-12 packet gaps "
            "that ate whole IDRs; 2000ms is generous but reliable."
        ),
        ge=0,
    )
    wait_for_connection: bool = Field(
        False,
        description=(
            "If True, srtsink blocks pipeline rollout until a caller "
            "connects. We default False so the pipeline starts even if "
            "OBS is not running yet."
        ),
    )


class RtspBridgeAppsinkConfig(BaseModel):
    """Tuning for the appsink that bridges main pipeline → in-process RTSP."""

    model_config = ConfigDict(extra="forbid")

    max_buffers: int = Field(
        200,
        description="Max samples queued inside appsink before producers block.",
        ge=1,
    )
    drop: bool = Field(
        False,
        description=(
            "If True, appsink drops oldest samples when full instead of "
            "blocking. False matches the original (back-pressure preferred)."
        ),
    )


class RtspBridgeSinkConfig(BaseModel):
    """4th tee branch: appsink → in-process RTSP server."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    mount_path: str = Field(
        "/boat1-processed",
        description="RTSP mount, e.g. rtsp://<host>:8554/boat1-processed.",
    )
    appsink: RtspBridgeAppsinkConfig = Field(
        default_factory=RtspBridgeAppsinkConfig,
        description="Tuning for the appsink that feeds the RTSP server.",
    )


class SinksConfig(BaseModel):
    """Container for all four tee-fanout sinks plus the shared queue config."""

    model_config = ConfigDict(extra="forbid")

    default_queue: TeeQueueConfig = Field(
        default_factory=TeeQueueConfig,
        description="Queue limits applied to every tee branch.",
    )
    srt_publisher: SrtPublisherSinkConfig
    file_recorder: FileRecorderSinkConfig = Field(
        default_factory=FileRecorderSinkConfig,
    )
    srt_listener: SrtListenerSinkConfig = Field(
        default_factory=SrtListenerSinkConfig,
    )
    rtsp_bridge: RtspBridgeSinkConfig = Field(
        default_factory=RtspBridgeSinkConfig,
    )

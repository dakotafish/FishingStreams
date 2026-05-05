from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class MediaMtxWaitConfig(BaseModel):
    """Wait for a MediaMTX path to become ready before starting the pipeline.

    Without this, srtsrc connects to a path that does not yet exist and
    floods MediaMTX with reconnect attempts.
    """

    model_config = ConfigDict(extra="forbid")

    api_url: str = Field(
        "http://mediamtx:8888",
        description="Base URL of the MediaMTX HTTP API. /v3/paths/list is appended.",
    )
    path_name: str = Field(
        ...,
        description="MediaMTX path name to wait for (e.g. 'boat1').",
    )
    poll_interval_seconds: float = Field(
        2.0,
        description="Seconds between API polls while the path is not yet ready.",
        gt=0,
    )
    request_timeout_seconds: float = Field(
        2.0,
        description="Per-request HTTP timeout for the readiness poll.",
        gt=0,
    )
    timeout_seconds: Optional[float] = Field(
        None,
        description="Overall wait timeout. None = wait forever (matches original).",
    )


class SourceConfig(BaseModel):
    """SRT source feeding tsdemux.

    Mirrors the upstream Moblin → MediaMTX SRT publish; we read it back
    out of MediaMTX as MPEG-TS and demux into video (H.265) + audio (AAC).
    """

    model_config = ConfigDict(extra="forbid")

    uri: str = Field(
        ...,
        description="SRT URI for srtsrc, e.g. srt://mediamtx:8890?streamid=read:boat1.",
    )
    latency_ms: int = Field(
        200,
        description="srtsrc latency property in ms; SRT retransmission window.",
        ge=0,
    )
    wait_for: MediaMtxWaitConfig = Field(
        ...,
        description="Readiness check before the pipeline is built.",
    )

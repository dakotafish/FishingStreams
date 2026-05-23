from pathlib import Path
from typing import Union

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .audio import AudioBranchConfig
from .browser_overlay import BrowserOverlayConfig
from .mux import MuxConfig
from .rtsp import RtspServerConfig
from .scoreboard import ScoreboardConfig
from .sinks import SinksConfig
from .source import SourceConfig
from .video import VideoDecodeBranchConfig, VideoEncodeBranchConfig


class PipelineConfig(BaseModel):
    """Root configuration for a single OverlayPipeline instance."""

    model_config = ConfigDict(extra="forbid")

    source: SourceConfig
    video_decode: VideoDecodeBranchConfig = Field(default_factory=VideoDecodeBranchConfig)
    video_encode: VideoEncodeBranchConfig
    scoreboard: ScoreboardConfig = Field(default_factory=ScoreboardConfig)
    browser_overlay: BrowserOverlayConfig = Field(default_factory=BrowserOverlayConfig)
    audio: AudioBranchConfig = Field(default_factory=AudioBranchConfig)
    mux: MuxConfig = Field(default_factory=MuxConfig)
    sinks: SinksConfig
    rtsp_server: RtspServerConfig = Field(default_factory=RtspServerConfig)

    @classmethod
    def from_yaml(cls, path: Union[str, Path]) -> "PipelineConfig":
        """Load and validate a YAML config file.

        Validation is strict: unknown keys raise instead of being silently
        ignored, so typos in the YAML surface immediately at startup.
        """
        with open(path, "r") as f:
            raw = yaml.safe_load(f)
        return cls.model_validate(raw)

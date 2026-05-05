from pathlib import Path
from typing import Union

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .audio import AudioBranchConfig
from .mux import MuxConfig
from .rtsp import RtspServerConfig
from .sinks import SinksConfig
from .source import SourceConfig
from .video import VideoBranchConfig


class PipelineConfig(BaseModel):
    """Root configuration for a single OverlayPipeline instance."""

    model_config = ConfigDict(extra="forbid")

    source: SourceConfig
    video: VideoBranchConfig
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

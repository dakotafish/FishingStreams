from pydantic import BaseModel, ConfigDict


class AudioBranchConfig(BaseModel):
    """AAC passthrough — parse only, no decode/re-encode.

    The branch is always present (the original's INCLUDE_AUDIO toggle and
    its fakesink fallback have been removed). If the upstream stream lacks
    an audio elementary stream, tsdemux simply will not raise an audio pad
    and aacparse will sit idle.
    """

    model_config = ConfigDict(extra="forbid")

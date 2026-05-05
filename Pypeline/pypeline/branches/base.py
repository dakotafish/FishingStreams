from abc import ABC, abstractmethod
from typing import Optional

from gi.repository import Gst


def make_element(factory_name: str, element_name: Optional[str] = None) -> Gst.Element:
    """Create a GStreamer element or raise with a clear message.

    The original script raises a generic 'failed to create an element' error
    that does not say *which* element failed; in practice the failure is
    almost always a missing plugin (rsvgoverlay needs gst-plugins-bad,
    avdec_h265 needs gst-libav). We name the factory in the error so the
    fix is obvious.
    """
    element = Gst.ElementFactory.make(factory_name, element_name)
    if element is None:
        raise RuntimeError(
            f"failed to create GStreamer element '{factory_name}' "
            f"(name={element_name!r}). Is the plugin installed?"
        )
    return element


class Branch(ABC):
    """A self-contained chain of GStreamer elements.

    Each Branch owns one or more elements, exposes an input pad (where
    upstream connects), and optionally an output pad (where downstream
    connects). Terminal sinks return None for output_pad.

    Lifecycle, called by the OverlayPipeline orchestrator in order:

        branch.build()                  # create + configure elements
        branch.add_to(pipeline)         # parent everything to the pipeline
        branch.link_internal()          # link pads inside the branch

    After all branches have been added, the orchestrator wires
    inter-branch links using input_pad / output_pad.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._elements: list[Gst.Element] = []
        self._built = False

    @abstractmethod
    def build(self) -> None:
        """Create elements and set their properties."""

    @abstractmethod
    def link_internal(self) -> None:
        """Link the branch's elements to each other."""

    @property
    def input_pad(self) -> Optional[Gst.Pad]:
        """Sink pad where upstream connects, or None for source-only branches.

        Sources (e.g. SrtMpegTsSource) have no input pad. Branches with
        request-pad inputs (e.g. MpegTsMuxBranch) override with a method
        like request_video_pad() instead and leave this None.
        """
        return None

    @property
    def output_pad(self) -> Optional[Gst.Pad]:
        """Source pad where downstream connects, or None for terminal sinks."""
        return None

    def add_to(self, pipeline: Gst.Pipeline) -> None:
        """Parent every owned element to ``pipeline``."""
        for el in self._elements:
            if not pipeline.add(el):
                raise RuntimeError(
                    f"failed to add element {el.get_name()!r} to pipeline "
                    f"(branch={self.name!r}); already parented?"
                )

    def _track(self, element: Gst.Element) -> Gst.Element:
        """Append an element to the owned list and return it for chaining."""
        self._elements.append(element)
        return element

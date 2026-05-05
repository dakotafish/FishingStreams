from typing import Optional

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstRtspServer", "1.0")
from gi.repository import Gst, GstRtspServer

from .config import RtspServerConfig


class RtspServer:
    """In-process GstRtspServer that serves bytes pushed in from outside.

    The server's MediaFactory launches an appsrc → tsparse → rtpmp2tpay
    pipeline per session. With factory_shared=True, every client shares
    one media instance, so we keep a single appsrc reference and push the
    same buffers to it from outside (e.g. from RtspBridgeSink's appsink
    new-sample callback).
    """

    def __init__(self, config: RtspServerConfig) -> None:
        self.config = config
        self._server: Optional[GstRtspServer.RTSPServer] = None
        self._factory: Optional[GstRtspServer.RTSPMediaFactory] = None
        self._current_appsrc: Optional[Gst.Element] = None

    def start(self, mount_path: str) -> None:
        """Build and attach the server to the default GLib main context.

        Must be called after Gst.init() and before the main loop runs.
        """
        self._server = GstRtspServer.RTSPServer()
        self._server.set_service(str(self.config.port))

        self._factory = GstRtspServer.RTSPMediaFactory()
        self._factory.set_launch(self.config.factory_launch)
        self._factory.set_shared(self.config.factory_shared)
        self._factory.connect("media-configure", self._on_media_configure)

        self._server.get_mount_points().add_factory(mount_path, self._factory)
        self._server.attach(None)
        print(
            f"RTSP server listening on :{self.config.port}{mount_path}"
        )

    def push_buffer(self, buffer: Gst.Buffer) -> None:
        """Push a buffer into the per-session appsrc, if one is bound.

        Drops silently when no client is connected (no appsrc yet) — that
        matches the original behaviour and avoids stalling upstream.
        """
        appsrc = self._current_appsrc
        if appsrc is None:
            return
        appsrc.emit("push-buffer", buffer)

    def _on_media_configure(
        self,
        _factory: GstRtspServer.RTSPMediaFactory,
        media: GstRtspServer.RTSPMedia,
    ) -> None:
        element = media.get_element()
        appsrc = element.get_by_name("rtsp_src")
        if appsrc is None:
            print("[rtsp] media configured but appsrc 'rtsp_src' not found in factory_launch")
            return
        appsrc.set_property("is-live", True)
        appsrc.set_property("format", Gst.Format.TIME)
        appsrc.set_property("do-timestamp", True)
        self._current_appsrc = appsrc
        media.connect("unprepared", self._on_media_unprepared)
        print("[rtsp] media configured — appsrc bound")

    def _on_media_unprepared(self, _media: GstRtspServer.RTSPMedia) -> None:
        self._current_appsrc = None
        print("[rtsp] media unprepared — appsrc cleared")

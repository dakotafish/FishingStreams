import json
import time
import urllib.request
from typing import Iterable

from .config import MediaMtxWaitConfig


class MediaMtxTimeout(RuntimeError):
    """Raised when a MediaMtxWaiter times out waiting for a path."""


class MediaMtxWaiter:
    """Block until a MediaMTX path is published and ready.

    The original script polled http://mediamtx:8888/v3/paths/list every
    2s with a 2s timeout, ignoring all errors. We preserve that loop but
    add an optional overall timeout so a misconfigured pipeline does not
    hang forever in CI / dev.
    """

    def __init__(self, config: MediaMtxWaitConfig) -> None:
        self.config = config

    def wait(self) -> None:
        c = self.config
        url = f"{c.api_url.rstrip('/')}/v3/paths/list"
        print(f"Waiting for MediaMTX path '{c.path_name}' to be ready... ({url})")

        deadline = (
            None
            if c.timeout_seconds is None
            else time.monotonic() + c.timeout_seconds
        )

        while True:
            ready = False
            try:
                with urllib.request.urlopen(url, timeout=c.request_timeout_seconds) as resp:
                    data = json.load(resp)
                ready = c.path_name in self._ready_paths(data.get("items", []))
            except Exception:
                pass

            if ready:
                print(f"{c.path_name} is live — starting GStreamer pipeline")
                return

            if deadline is not None and time.monotonic() > deadline:
                raise MediaMtxTimeout(
                    f"MediaMTX path {c.path_name!r} not ready after "
                    f"{c.timeout_seconds}s"
                )
            time.sleep(c.poll_interval_seconds)

    @staticmethod
    def _ready_paths(items: Iterable[dict]) -> set[str]:
        return {p["name"] for p in items if p.get("ready")}

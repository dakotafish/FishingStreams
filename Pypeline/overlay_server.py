"""Tiny static HTTP server for the in-container browser overlay.

Serves files out of a single directory (default: /overlays) on a single port
(default: 8080). Chromium, also running in the container, loads
``http://localhost:8080/catch-counter.html`` against this server.

v2 hook: replace ``SimpleHTTPRequestHandler`` with a handler that also
upgrades WebSocket connections so we can push live state (catch counts,
fish-detection events) to the overlay instead of polling a remote API.
"""

import argparse
import functools
import http.server


def main() -> None:
    ap = argparse.ArgumentParser(description="Static file server for the browser overlay.")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--dir", default="/overlays", help="Directory to serve.")
    args = ap.parse_args()

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=args.dir)
    with http.server.ThreadingHTTPServer(("0.0.0.0", args.port), handler) as httpd:
        print(f"[overlay-server] serving {args.dir} on port {args.port}", flush=True)
        httpd.serve_forever()


if __name__ == "__main__":
    main()

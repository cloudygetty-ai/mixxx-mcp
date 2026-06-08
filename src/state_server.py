"""
state_server.py — Lightweight HTTP state ingestion server

Replaces OSC (which requires Mixxx to be built with liblo).
Mixxx's QJSEngine supports XMLHttpRequest, so the companion JS script
POSTs control changes to this server instead of UDP.

Endpoint: POST http://127.0.0.1:57121/state
Body: JSON { "group": "[Channel1]", "key": "play", "value": 1.0 }

Also exposes:
  GET /state              → full state snapshot (JSON)
  GET /state/<group>/<key> → single value

Runs in a daemon thread — zero overhead when idle.
"""

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional
from .osc_listener import OscStateStore

log = logging.getLogger("mixxx-mcp.state_server")


class _Handler(BaseHTTPRequestHandler):
    store: OscStateStore  # injected at class level

    def log_message(self, fmt, *args):
        log.debug(fmt, *args)

    # ── POST /state ────────────────────────────────────────────────────────
    def do_POST(self):
        if self.path != "/state":
            self._send(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            data = json.loads(body)
            group = data["group"]
            key   = data["key"]
            value = data["value"]
            self.store.set(group, key, value)
            log.debug("STATE ← %s/%s = %s", group, key, value)
            self._send(200, {"ok": True})
        except Exception as e:
            log.warning("state POST error: %s", e)
            self._send(400, {"error": str(e)})

    # ── GET /state ─────────────────────────────────────────────────────────
    def do_GET(self):
        parts = self.path.strip("/").split("/")
        if parts[0] != "state":
            self._send(404, {"error": "not found"})
            return
        if len(parts) == 1:
            # Full snapshot
            self._send(200, self.store.snapshot())
        elif len(parts) == 3:
            # /state/<group>/<key>  — group brackets encoded as URL path
            group = f"[{parts[1]}]"
            key   = parts[2]
            val   = self.store.get(group, key)
            if val is None:
                self._send(404, {"error": "no data"})
            else:
                self._send(200, {"group": group, "key": key, "value": val})
        else:
            self._send(400, {"error": "use /state or /state/GroupName/key"})

    def _send(self, code: int, data: dict):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


class StateServer:
    """HTTP server that ingests Mixxx control state from the JS bridge."""

    def __init__(self, store: OscStateStore, host: str = "127.0.0.1", port: int = 57121):
        self.store = store
        self.host  = host
        self.port  = port
        self._thread: Optional[threading.Thread] = None

    def start(self):
        _Handler.store = self.store
        server = HTTPServer((self.host, self.port), _Handler)
        self._thread = threading.Thread(
            target=server.serve_forever, daemon=True, name="state-server"
        )
        self._thread.start()
        log.info("State server listening on http://%s:%d/state", self.host, self.port)

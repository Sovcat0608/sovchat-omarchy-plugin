"""Bounded SSE invalidation reader. Bearer stays in headers, never QML or URLs."""
import json
import threading
import urllib.request
from api import API_ORIGIN, NoRedirect


class Events:
    def __init__(self, token, loop, changed):
        self.stopped = threading.Event()
        self.response = None
        self.token = token
        self.loop, self.changed = loop, changed
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        opener = urllib.request.build_opener(NoRedirect())
        while not self.stopped.is_set():
            try:
                request = urllib.request.Request(API_ORIGIN + "/api/messages/stream", headers={
                    "Authorization": "Bearer " + self.token, "Accept": "text/event-stream",
                    "X-SovChat-App-Variant": "omarchy"})
                with opener.open(request, timeout=20) as response:
                    self.response = response
                    while not self.stopped.is_set():
                        line = response.readline(262145)
                        if not line or len(line) > 262144: break
                        if line.startswith(b"data: "):
                            value = json.loads(line[6:])
                            if isinstance(value, dict) and value.get("type") not in ("ping", "connected"):
                                self.loop.call_soon_threadsafe(self.changed.set)
            except Exception:
                pass  # No server response or credentials go to shell logs.
            finally:
                self.response = None
            if not self.stopped.is_set():
                self.loop.call_soon_threadsafe(self.changed.set)
                self.stopped.wait(3)

    def close(self):
        self.stopped.set()
        # A bounded read timeout lets the daemon exit without blocking controls.
        # Only this thread owns/closes its response; no cross-thread buffered I/O.

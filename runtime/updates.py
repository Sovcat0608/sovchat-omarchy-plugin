"""Read-only plugin release checks; never download or execute an update."""

import re
import shutil
import subprocess

from api import ApiError, Transport

REPOSITORY = "Sovcat0608/sovchat-omarchy-plugin"
LATEST_URL = "https://api.github.com/repos/" + REPOSITORY + "/releases/latest"
UPDATE_COMMAND = "omarchy plugin update com.sovchat.omarchy"


def version(value, development=False):
    if not isinstance(value, str):
        raise ApiError("INVALID_RESPONSE")
    pattern = r"v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    if development:
        pattern += r"(?:-dev\.\d+)?"
    match = re.fullmatch(pattern, value)
    if not match or any(len(part) > 8 for part in match.groups()):
        raise ApiError("INVALID_RESPONSE")
    return tuple(int(part) for part in match.groups())


class Updates:
    def __init__(self, installed, transport=None, notify=None):
        self.installed = installed
        self.transport = transport or Transport()
        self.notify = notify or self.desktop_notice
        self.notified = set()

    @staticmethod
    def desktop_notice(latest):
        executable = shutil.which("notify-send")
        if not executable:
            return False
        try:
            subprocess.run([executable, "--app-name=SovChat", "--",
                            "SovChat plugin update available",
                            "Version " + latest + ". Open SovChat in the bar to review."],
                           check=True, timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except (OSError, subprocess.SubprocessError):
            return False

    def check(self):
        status, payload = self.transport.request(LATEST_URL, headers={
            "Accept": "application/vnd.github+json", "User-Agent": "SovChat-Omarchy-Plugin",
        })
        if status != 200:
            raise ApiError("NETWORK")
        if payload.get("draft") is not False or payload.get("prerelease") is not False:
            raise ApiError("INVALID_RESPONSE")
        tag = payload.get("tag_name")
        remote = version(tag)
        local = version(self.installed, development=True)
        latest = ".".join(map(str, remote))
        # A matching stable release supersedes a development preview.
        available = remote > local or (remote == local and "-dev." in self.installed)
        if available and latest not in self.notified and self.notify(latest):
            self.notified.add(latest)
        return {"available": available, "latest": latest, "command": UPDATE_COMMAND}

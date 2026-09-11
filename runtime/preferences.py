"""Private local preferences. Never stores account data or credentials."""
import json
import os
from pathlib import Path
import stat
import tempfile
from api import ApiError

DEFAULTS = {"input": "", "output": "", "noiseSuppression": True,
            "echoCancellation": True, "autoGainControl": True, "afkMinutes": 0, "outputVolume": 1.0}


def validated(data):
    if not isinstance(data, dict) or set(data) - DEFAULTS.keys(): raise ApiError("BAD_INPUT")
    for key, value in data.items():
        if key in ("input", "output"):
            if not isinstance(value, str) or len(value) > 512 or "\x00" in value: raise ApiError("BAD_INPUT")
        elif key == "outputVolume":
            if type(value) not in (int, float) or not 0 <= value <= 1: raise ApiError("BAD_INPUT")
        elif key == "afkMinutes":
            if type(value) is not int or not 0 <= value <= 120: raise ApiError("BAD_INPUT")
        elif type(value) is not bool: raise ApiError("BAD_INPUT")
    return dict(DEFAULTS, **data)


class Preferences:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else Path.home() / ".config/sovchat-omarchy"
        self.path = self.directory / "preferences.json"

    def load(self):
        try:
            info = self.path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_size > 4096: return dict(DEFAULTS)
            if hasattr(os, "getuid") and (info.st_uid != os.getuid() or info.st_mode & 0o077): return dict(DEFAULTS)
            return validated(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError, ApiError): return dict(DEFAULTS)

    def save(self, values):
        value = validated(values)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        info = self.directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or (hasattr(os, "getuid") and (info.st_uid != os.getuid() or info.st_mode & 0o022)):
            raise ApiError("BAD_INPUT")
        fd, name = tempfile.mkstemp(prefix=".preferences-", dir=self.directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                json.dump(value, output)
                output.flush()
                os.fsync(output.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name): os.unlink(name)

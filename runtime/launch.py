"""Select an explicitly installed plugin runtime; never download on plugin load."""
import os
from pathlib import Path
import sys

broker = Path(__file__).resolve().with_name("broker.py")
base = Path.home() / ".local/share/sovchat-omarchy/runtimes"
current = base / "current"
python = Path(sys.executable)
if current.is_symlink():
    target = current.resolve()
    if target.parent == base.resolve() and target.is_dir() and target.stat().st_uid == os.getuid():
        candidate = target / "bin/python"
        if candidate.is_file():
            python = candidate
            os.environ["SOVCHAT_NATIVE_VOICE_PREVIEW"] = "1"
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.execv(str(python), [str(python), "-B", "-u", str(broker)])

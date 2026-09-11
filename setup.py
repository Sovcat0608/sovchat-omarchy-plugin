"""Explicit native plugin setup/rollback. No sudo, system package changes or UI launch."""
import argparse
import hashlib
import os
from pathlib import Path
import platform
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import venv


def require_qt_imageformats():
    # Custom avatars from the shared desktop service are WebP. Qt's base image
    # handlers do not include that decoder on a minimal Omarchy installation.
    result = subprocess.run(["qmake6", "-query", "QT_INSTALL_PLUGINS"],
                            check=True, capture_output=True, text=True, timeout=5)
    plugins = Path(result.stdout.strip())
    if not plugins.is_absolute() or not (plugins / "imageformats/libqwebp.so").is_file():
        raise SystemExit("Missing Qt WebP decoder. Install qt6-imageformats explicitly, then rerun setup. Custom SovChat avatars require it.")


def owned_directory(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
        raise SystemExit("Unsafe runtime directory; expected your own non-writable-by-others directory.")


def link_atomic(base, name, target):
    if target.parent != base.resolve() or not target.is_dir(): raise SystemExit("Invalid runtime target.")
    temporary = base / (".link-" + secrets.token_hex(8))
    temporary.symlink_to(target.name, target_is_directory=True)
    os.replace(temporary, base / name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheelhouse", type=Path, help="Use an existing verified wheel directory without network access")
    parser.add_argument("--rollback", action="store_true", help="Select the previous native dependency runtime; does not change plugin source")
    args = parser.parse_args()
    if sys.platform != "linux" or platform.machine() != "x86_64" or sys.version_info[:2] != (3, 14):
        raise SystemExit("This lock targets Omarchy x86_64 with Python 3.14. No unsupported runtime was installed.")
    if os.getuid() == 0: raise SystemExit("Run as your desktop user, not root.")
    root = Path(__file__).resolve().parent
    base = Path.home() / ".local/share/sovchat-omarchy/runtimes"
    owned_directory(base)
    current = (base / "current").resolve() if (base / "current").is_symlink() else None
    if args.rollback:
        previous = base / "previous"
        if not previous.is_symlink(): raise SystemExit("No previous runtime is available.")
        target = previous.resolve()
        link_atomic(base, "current", target)
        if current: link_atomic(base, "previous", current)
        print("Previous runtime selected. Reload SovChat; plugin source was not changed.")
        return
    required = ("qmake6", "make", "g++", "pactl", "pw-dump")
    missing = [name for name in required if not shutil.which(name)]
    if missing: raise SystemExit("Install these native prerequisites explicitly first: " + ", ".join(missing))
    require_qt_imageformats()
    try:
        import gi
        gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import GdkPixbuf
        gi.require_version("Gst", "1.0")
        from gi.repository import Gst
        Gst.init(None)
        elements = ("pipewiresrc", "pulsesink", "appsrc", "appsink", "volume", "videoconvert", "videoscale", "videorate")
        missing = [name for name in elements if Gst.ElementFactory.find(name) is None]
        if missing: raise SystemExit("Missing GStreamer components: " + ", ".join(missing))
    except (ImportError, ValueError):
        raise SystemExit("Install python-gobject, gdk-pixbuf2, gstreamer, gst-plugins-base, gst-plugins-good and gst-plugin-pipewire explicitly first.")
    lock = root / "runtime/requirements.lock"
    digest = hashlib.sha256(lock.read_bytes()).hexdigest()[:12]
    target = Path(tempfile.mkdtemp(prefix="py314-" + digest + "-", dir=base))
    print("Preparing plugin-owned runtime; the current runtime remains selected until validation passes.")
    venv.EnvBuilder(with_pip=True, system_site_packages=True).create(target)
    python = target / "bin/python"
    command = [str(python), "-m", "pip", "--isolated", "install", "--ignore-installed", "--no-deps",
               "--require-hashes", "--only-binary=:all:", "-r", str(lock)]
    if args.wheelhouse: command += ["--no-index", "--find-links", str(args.wheelhouse.resolve(strict=True))]
    subprocess.run(command, check=True)
    subprocess.run([str(python), "-B", "-c", "from livekit import rtc; import dbus_next, gi; assert hasattr(rtc, 'PlatformAudio'); assert hasattr(rtc, 'VideoStream')"], check=True)
    build = Path(tempfile.mkdtemp(prefix="sovchat-video-"))
    subprocess.run([sys.executable, "-B", str(root / "build_video.py"), "--plugin-root", str(root), "--build-dir", str(build)], check=True)
    if current: link_atomic(base, "previous", current)
    link_atomic(base, "current", target.resolve())
    print("Native runtime and video bridge ready. Reload the Omarchy shell to use them.")
    print("Older runtime/build directories are retained; no user data or installed app was removed.")


if __name__ == "__main__": main()

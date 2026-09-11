#!/usr/bin/env python3
"""Explicit, offline native video build. Does not install packages or use sudo."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--plugin-root", type=Path, required=True)
parser.add_argument("--build-dir", type=Path, required=True)
args = parser.parse_args()
root = args.plugin_root.resolve(strict=True)
bridge = root / "bridge"
if bridge.resolve().parent != root or bridge.is_symlink():
    raise SystemExit("The bridge directory must be inside this plugin, not a symlink.")
project = bridge / "sovchatvideo.pro"
if not project.is_file() or any(c.isspace() for c in str(bridge)):
    raise SystemExit("A plugin source tree and a path without whitespace are required.")
build = args.build_dir.resolve()
if build == root or root in build.parents:
    raise SystemExit("Build outside the watched plugin source tree.")
for command in ("qmake6", "make", "g++"):
    if not shutil.which(command): raise SystemExit(f"Missing {command}; install build dependencies explicitly.")
build.mkdir(parents=True, exist_ok=True)
subprocess.run(["qmake6", str(project)], cwd=build, check=True)
subprocess.run(["make", "-j2"], cwd=build, check=True)
binary = build / "libsovchatvideo.so"
if not binary.is_file(): raise SystemExit("Native video build produced no library.")
with tempfile.NamedTemporaryFile(dir=bridge, prefix=".video-", delete=False) as output:
    temporary = Path(output.name)
    with binary.open("rb") as source: shutil.copyfileobj(source, output)
os.chmod(temporary, 0o755)
os.replace(temporary, bridge / binary.name)
# Quickshell remaps relative imports to qs: URLs. Qt cannot dlopen a qs: URL;
# the supported qmldir plugin path must point at the installed local library.
with tempfile.NamedTemporaryFile(dir=bridge, prefix=".qmldir-", mode="w", encoding="utf-8", delete=False) as output:
    temporary = Path(output.name)
    output.write(f"module bridge\nplugin sovchatvideo {bridge}\n")
os.chmod(temporary, 0o644)
os.replace(temporary, bridge / "qmldir")
print("Native video module built for the installed Qt version.")

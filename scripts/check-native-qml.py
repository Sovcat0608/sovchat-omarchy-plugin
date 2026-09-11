"""Parse candidate QML with Qt's actual parser; this is not an Omarchy host test."""

import argparse
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qmlformat", required=True, type=Path)
    args = parser.parse_args()
    executable = args.qmlformat.resolve(strict=True)
    root = Path(__file__).resolve().parents[1]
    failures = 0
    for path in sorted((root / "native-plugin").glob("*.qml")):
        result = subprocess.run([str(executable), str(path)], capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=20)
        if result.returncode != 0 or not result.stdout.strip():
            failures += 1
            print(f"FAIL {path.name}: {result.stderr}", file=sys.stderr)
        else:
            print(f"PASS {path.name} (syntax only)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

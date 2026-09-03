#!/usr/bin/python3

import json
import os
import stat
import struct
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


class MarketplacePresentationTests(unittest.TestCase):
    def test_preview_is_marketplace_ready(self):
        preview = PLUGIN_ROOT / "preview.png"
        source = PLUGIN_ROOT / "preview-source.svg"

        self.assertTrue(preview.is_file())
        self.assertTrue(source.is_file())
        self.assertLessEqual(preview.stat().st_size, 50 * 1024 * 1024)

        header = preview.read_bytes()[:24]
        self.assertEqual(header[:8], b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", header[16:24])
        self.assertEqual((width, height), (1600, 900))
        self.assertLessEqual(width * height, 40_000_000)

        source_text = source.read_text(encoding="utf-8")
        self.assertIn('role="img"', source_text)
        self.assertIn("<title", source_text)
        self.assertIn("<desc", source_text)
        self.assertIn("open signup", source_text.lower())

    def test_readme_explains_try_install_and_limits(self):
        readme = (PLUGIN_ROOT / "README.md").read_text(encoding="utf-8")
        lower = readme.lower()

        self.assertIn("## quick start", lower)
        self.assertIn(
            "omarchy plugin add https://github.com/Sovcat0608/sovchat-omarchy-plugin.git --enable",
            readme,
        )
        self.assertIn(
            "omarchy plugin remove com.sovchat.omarchy --yes",
            readme,
        )
        self.assertIn("https://sovchat.com/app", readme)
        self.assertIn("open signup", lower)
        self.assertIn("server-enforced", lower)
        self.assertIn("500-account", lower)
        self.assertRegex(lower, r"no access\s*(?:>\s*)?code")
        self.assertNotRegex(lower, r"beta[- ]enabled|beta access|access code required")
        self.assertIn("x86_64", lower)
        self.assertIn("pipewire", lower)
        self.assertIn("system audio", lower)
        self.assertIn("129 mb", lower)

    def test_manifest_is_discoverable(self):
        manifest = json.loads(
            (PLUGIN_ROOT / "manifest.json").read_text(encoding="utf-8"),
        )
        description = manifest["description"].lower()

        self.assertLessEqual(len(manifest["description"]), 500)
        self.assertIn("voice rooms", description)
        self.assertIn("text chat", description)
        self.assertIn("screen and application sharing", description)
        self.assertIn("screen-share", manifest["barWidget"]["aliases"])
        self.assertIn("open signup", description)
        self.assertIn("500-account", description)

    @unittest.skipUnless(os.name == "posix", "Git executable mode is relevant on Linux")
    def test_helpers_are_executable(self):
        for relative_path in (
            "bin/sovchat-control",
            "bin/sovchat-safe-install.py",
        ):
            mode = (PLUGIN_ROOT / relative_path).stat().st_mode
            self.assertTrue(mode & stat.S_IXUSR, relative_path)


if __name__ == "__main__":
    unittest.main()

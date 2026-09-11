"""Minimal Omarchy must include Qt's optional decoder for shared WebP avatars."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("native_setup", Path(__file__).resolve().parents[1] / "native-plugin/setup.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class SetupTests(unittest.TestCase):
    def test_missing_webp_decoder_is_actionable(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(setup.subprocess, "run", return_value=SimpleNamespace(stdout=folder)):
                with self.assertRaisesRegex(SystemExit, "qt6-imageformats"):
                    setup.require_qt_imageformats()

    def test_decoder_is_checked_under_installed_qt_plugin_path(self):
        with tempfile.TemporaryDirectory() as folder:
            imageformats = Path(folder) / "imageformats"
            imageformats.mkdir()
            (imageformats / "libqwebp.so").touch()
            with patch.object(setup.subprocess, "run", return_value=SimpleNamespace(stdout=folder + "\n")) as command:
                setup.require_qt_imageformats()
            self.assertEqual(command.call_args.args[0], ["qmake6", "-query", "QT_INSTALL_PLUGINS"])
            self.assertEqual(command.call_args.kwargs["timeout"], 5)

    def test_failed_qt_query_does_not_install_dependencies(self):
        with patch.object(setup.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "qmake6")):
            with self.assertRaises(subprocess.CalledProcessError): setup.require_qt_imageformats()


if __name__ == "__main__": unittest.main()

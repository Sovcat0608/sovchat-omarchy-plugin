"""Native preferences are local, bounded and credential-free."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock

os.environ["SOVCHAT_NATIVE_DISABLE_KEYRING"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "native-plugin/runtime"))
from api import ApiError
from preferences import Preferences, DEFAULTS, validated
from video import VideoSession


class PreferencesTests(unittest.TestCase):
    def test_round_trip_is_private_and_contains_only_supported_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            prefs = Preferences(directory)
            value = validated({"input": "qa-input", "afkMinutes": 15, "noiseSuppression": False})
            prefs.save(value)
            self.assertEqual(prefs.load(), value)
            self.assertEqual(set(json.loads(prefs.path.read_text())), set(DEFAULTS))
            if hasattr(os, "getuid"): self.assertEqual(prefs.path.stat().st_mode & 0o777, 0o600)

    def test_unknown_keys_credentials_and_invalid_values_cannot_be_saved(self):
        for value in ({"token": "secret"}, {"afkMinutes": True}, {"afkMinutes": -1},
                      {"afkMinutes": 121}, {"noiseSuppression": "true"}, {"input": "x" * 513}):
            with self.assertRaises(ApiError): validated(value)

    def test_corrupt_preferences_fall_back_without_affecting_session(self):
        with tempfile.TemporaryDirectory() as directory:
            prefs = Preferences(directory)
            prefs.path.write_text("not JSON")
            self.assertEqual(prefs.load(), DEFAULTS)

    def test_symlink_preference_file_is_never_read(self):
        if not hasattr(os, "getuid"): self.skipTest("Linux ownership boundary")
        with tempfile.TemporaryDirectory() as directory:
            prefs = Preferences(directory)
            other = Path(directory) / "other"
            other.write_text(json.dumps(dict(DEFAULTS, afkMinutes=10)))
            other.chmod(0o600)
            prefs.path.symlink_to(other)
            self.assertEqual(prefs.load(), DEFAULTS)


class CaptureAuthorizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_quality_never_opens_portal(self):
        factory = Mock()
        video = VideoSession(Mock(), Mock(), capture_factory=factory)
        with self.assertRaises(ApiError): await video.start("monitor", quality="8k")
        factory.assert_not_called()

    async def test_quota_recheck_happens_after_picker_and_before_publication(self):
        capture = Mock(open=AsyncMock(), close=AsyncMock(), fps=30)
        rtc, room = Mock(), Mock()
        video = VideoSession(rtc, room, capture_factory=lambda: capture)
        async def refuse():
            capture.open.assert_awaited_once_with("window")
            rtc.VideoSource.assert_not_called()
            raise ApiError("STREAM_LIMIT")
        with self.assertRaises(ApiError): await video.start("window", authorize=refuse, quality="480p")
        self.assertEqual((capture.width, capture.height), (854, 480))
        capture.close.assert_awaited_once()
        room.local_participant.publish_track.assert_not_called()
        self.assertFalse(video.pending)
        self.assertIsNone(video.capture)


if __name__ == "__main__": unittest.main()

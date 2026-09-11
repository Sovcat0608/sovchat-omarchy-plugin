"""Selected app audio, image bounds, adaptive pacing and stream-audio privacy."""
import os
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
os.environ["SOVCHAT_NATIVE_DISABLE_KEYRING"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "native-plugin/runtime"))
from api import ApiError
from app_audio import applications, selected_link_only
from images_native import dimensions
from media import Media
from video import adaptive_rate, VideoSession


class BoundsTests(unittest.TestCase):
    def test_avatar_dimensions_are_bounded_before_native_decode(self):
        prefix = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
        self.assertEqual(dimensions(prefix + struct.pack(">II", 600, 400), "image/png"), (600, 400))
        for size in ((0, 100), (1000000, 1), (10000, 10000)):
            with self.assertRaises(ApiError): dimensions(prefix + struct.pack(">II", *size), "image/png")
        with self.assertRaises(ApiError): dimensions(b"<svg/>", "image/svg+xml")

    def test_auto_frame_rate_reduces_quickly_and_recovers_slowly(self):
        self.assertEqual(adaptive_rate(60, True, 2, 60), (30, 0))
        self.assertEqual(adaptive_rate(15, True, 0, 60), (15, 0))
        self.assertEqual(adaptive_rate(30, False, 0, 60), (30, 1))
        self.assertEqual(adaptive_rate(30, False, 2, 60), (45, 0))
        self.assertEqual(adaptive_rate(30, False, 2, 30), (30, 0))

    def test_capture_requires_links_from_selected_application_only(self):
        target = {"id": 1, "info": {"props": {"object.serial": 101}}}
        capture = {"id": 2, "info": {"props": {"node.name": "qa-capture"}}}
        link = {"type": "PipeWire:Interface:Link", "info": {"input-node-id": 2, "output-node-id": 1}}
        self.assertTrue(selected_link_only([target, capture, link], "qa-capture", "101"))
        self.assertFalse(selected_link_only([target, capture], "qa-capture", "101"))
        extra = {"type": "PipeWire:Interface:Link", "info": {"input-node-id": 2, "output-node-id": 99}}
        self.assertFalse(selected_link_only([target, capture, link, extra], "qa-capture", "101"))

    def test_unwatched_stream_audio_is_never_subscribed(self):
        rtc = SimpleNamespace(TrackSource=SimpleNamespace(SOURCE_SCREENSHARE_AUDIO=3))
        media = Media(rtc=rtc)
        owner = SimpleNamespace(identity="owner")
        other = SimpleNamespace(identity="other")
        audio = SimpleNamespace(source=3)
        self.assertFalse(media.wants_audio(audio, owner))
        media.video = SimpleNamespace(watching="selected", publications=lambda: [(SimpleNamespace(sid="selected"), owner)])
        self.assertTrue(media.wants_audio(audio, owner))
        self.assertFalse(media.wants_audio(audio, other))
        media.deafened = True
        self.assertFalse(media.wants_audio(audio, owner))


class CaptureTests(unittest.IsolatedAsyncioTestCase):
    async def test_audio_stop_failure_still_stops_and_closes_screen(self):
        video = VideoSession(Mock(), Mock())
        audio = SimpleNamespace(stop_local=Mock(side_effect=RuntimeError("audio failure")), close=AsyncMock())
        capture = SimpleNamespace(stop_local=Mock(), close=AsyncMock())
        track = Mock()
        video.audio, video.capture, video.pending_track = audio, capture, track
        await video.stop()
        track.mute.assert_called_once()
        capture.stop_local.assert_called_once()
        capture.close.assert_awaited_once()
        audio.close.assert_awaited_once()

    async def test_application_close_failure_still_mutes_and_releases_source(self):
        from share_audio import ShareAudio
        audio = ShareAudio(Mock(), Mock())
        audio.capture = SimpleNamespace(close=Mock(side_effect=RuntimeError("capture failure")))
        source = SimpleNamespace(clear_queue=Mock(), aclose=AsyncMock())
        track = Mock()
        audio.source, audio.track = source, track
        await audio.close()
        track.mute.assert_called_once()
        source.clear_queue.assert_called_once()
        source.aclose.assert_awaited_once()

    async def test_audio_source_choices_exclude_mic_output_mix_and_sovchat(self):
        def node(serial, name, kind, pid=123456789):
            return {"id": serial, "info": {"props": {"object.serial": serial, "application.name": name, "media.class": kind, "application.process.id": pid}}}
        nodes = [node(1, "Music", "Stream/Output/Audio"), node(2, "Microphone", "Audio/Source"),
                 node(3, "Speakers", "Audio/Sink"), node(4, "SovChat-playback", "Stream/Output/Audio"),
                 node(5, "Own source", "Stream/Output/Audio", os.getpid())]
        with patch("app_audio.graph", new=AsyncMock(return_value=nodes)):
            self.assertEqual(await applications(), [{"id": "1", "name": "Music", "nodeId": 1}])

    async def test_screen_stop_also_closes_application_audio(self):
        video = VideoSession(Mock(), SimpleNamespace(local_participant=SimpleNamespace(unpublish_track=AsyncMock())))
        audio = SimpleNamespace(stop_local=Mock(), close=AsyncMock())
        video.audio = audio
        await video.stop()
        audio.stop_local.assert_called_once()
        audio.close.assert_awaited_once()
        self.assertIsNone(video.audio)

    async def test_pending_video_track_is_muted_before_async_cleanup(self):
        video = VideoSession(Mock(), Mock())
        video.pending_track = Mock()
        video.stop_share_local()
        video.pending_track.mute.assert_called_once()


if __name__ == "__main__": unittest.main()

"""Native video teardown contracts; fake tracks only, no device or network use."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "native-plugin/runtime"))
from media import Media
from video import VideoSession


class VideoTests(unittest.IsolatedAsyncioTestCase):
    def session(self):
        room = SimpleNamespace(remote_participants={}, local_participant=SimpleNamespace(
            unpublish_track=AsyncMock()))
        return VideoSession(SimpleNamespace(), room)

    async def test_stopping_own_share_keeps_watched_video(self):
        video = self.session()
        buffer = Mock()
        video.buffer, video.watching = buffer, "remote-stream"
        video.capture = Mock(close=AsyncMock())
        video.source = SimpleNamespace(aclose=AsyncMock())
        video.publication = SimpleNamespace(sid="own-stream", track=Mock())
        await video.stop()
        self.assertIs(video.buffer, buffer)
        buffer.close.assert_not_called()
        self.assertEqual(video.watching, "remote-stream")
        video.room.local_participant.unpublish_track.assert_awaited_once_with("own-stream")

    async def test_full_local_stop_closes_capture_and_display_immediately(self):
        video = self.session()
        capture, buffer, track = Mock(), Mock(), Mock()
        video.capture, video.buffer = capture, buffer
        video.publication = SimpleNamespace(track=track)
        video.stop_local()
        capture.stop_local.assert_called_once()
        buffer.close.assert_called_once()
        track.mute.assert_called_once()
        self.assertIsNone(video.buffer)

    async def test_source_failure_still_unpublishes_and_allows_retry(self):
        video = self.session()
        video.capture = Mock(close=AsyncMock())
        video.source = SimpleNamespace(aclose=AsyncMock(side_effect=RuntimeError("test failure")))
        video.publication = SimpleNamespace(sid="own-stream", track=Mock())
        with self.assertRaises(RuntimeError):
            await video.stop()
        video.room.local_participant.unpublish_track.assert_awaited_once()
        self.assertIsNone(video.capture)
        self.assertIsNone(video.source)
        self.assertIsNone(video.publication)

    async def test_shutdown_waits_for_detached_video_cleanup(self):
        media = Media()
        finished = []
        async def cleanup(): finished.append(True)
        media.schedule_cleanup(cleanup())
        await media.shutdown()
        self.assertEqual(finished, [True])
        self.assertFalse(media.cleanup_tasks)


if __name__ == "__main__": unittest.main()

"""LiveKit screen publication and one explicitly selected native video receiver."""
import asyncio
import importlib.util
from pathlib import Path

from api import ApiError
from frames import FrameBuffer
from portal import PortalCapture
from share_audio import ShareAudio


def adaptive_rate(current, limited, healthy, maximum):
    if limited: return max(15, current // 2), 0
    healthy += 1
    return (min(maximum, current + 15), 0) if healthy >= 3 else (current, healthy)


def renderer_available():
    return (Path(__file__).resolve().parent.parent / "bridge/libsovchatvideo.so").is_file()


def capture_available():
    return renderer_available() and all(importlib.util.find_spec(name) is not None for name in ("gi", "dbus_next"))


class VideoSession:
    def __init__(self, rtc, room, capture_factory=PortalCapture, buffer_factory=FrameBuffer):
        self.rtc, self.room = rtc, room
        self.capture_factory, self.buffer_factory = capture_factory, buffer_factory
        self.capture = None
        self.source = None
        self.publication = None
        self.feed = None
        self.receiver = None
        self.buffer = None
        self.watching = ""
        self.pending = False
        self.closed = False
        self.failure = ""
        self.reported_bytes = 0
        self.audio = None
        self.on_watch_changed = lambda: None
        self.pacer = None
        self.quality = ""
        self.pending_track = None
        self.publication_uncertain = False

    def publications(self):
        return [(publication, participant)
                for participant in self.room.remote_participants.values()
                for publication in participant.track_publications.values()
                if publication.source == self.rtc.TrackSource.SOURCE_SCREENSHARE]

    def state(self):
        return {
            "sharing": self.publication is not None,
            "screenPending": self.pending,
            "videoError": self.failure,
            "sharingAudio": self.audio is not None and self.audio.publication is not None,
            "shareQuality": self.quality,
            "shareFps": self.capture.fps if self.capture is not None else 0,
            "shareAudioError": self.audio.error if self.audio is not None else "",
            "watching": self.watching,
            "frameName": self.buffer.name if self.buffer is not None else "",
            "streams": [{"id": publication.sid, "nickname": str(participant.name or "Participant")[:100]}
                        for publication, participant in self.publications()][:16],
        }

    async def start(self, source_type, authorize=None, quality="720p", audio_node="", fps=30):
        if self.closed or self.capture is not None:
            raise ApiError("BAD_INPUT")
        sizes = {"auto": (1280, 720, 6_000_000), "480p": (854, 480, 1_200_000), "720p": (1280, 720, 6_000_000), "1080p": (1920, 1080, 12_000_000), "1440p": (2560, 1440, 18_000_000)}
        if quality not in sizes or type(fps) is not int or fps not in (15, 30, 60): raise ApiError("BAD_INPUT")
        self.quality = quality
        self.publication_uncertain = False
        self.pending = True
        self.reported_bytes = 0
        self.failure = ""
        capture = self.capture_factory()
        capture.width, capture.height, bitrate = sizes[quality]
        capture.fps = fps
        self.capture = capture
        try:
            await capture.open(source_type)
            if self.closed or self.capture is not capture: raise ApiError("CANCELLED")
            if audio_node:
                self.audio = ShareAudio(self.rtc, self.room)
                await self.audio.prepare(audio_node)
            if authorize is not None: await authorize()
            if self.closed or self.capture is not capture: raise ApiError("CANCELLED")
            self.source = self.rtc.VideoSource(capture.width, capture.height, is_screencast=True)
            track = self.rtc.LocalVideoTrack.create_video_track("screen", self.source)
            self.pending_track = track
            track.mute()
            options = self.rtc.TrackPublishOptions(source=self.rtc.TrackSource.SOURCE_SCREENSHARE,
                                                 simulcast=False)
            options.video_encoding.max_bitrate = bitrate
            options.video_encoding.max_framerate = capture.fps
            self.publication_uncertain = True
            self.publication = await asyncio.wait_for(self.room.local_participant.publish_track(track, options), 15)
            if self.closed or self.capture is not capture: raise ApiError("CANCELLED")
            if self.audio is not None: await self.audio.publish()
            if self.closed or self.capture is not capture: raise ApiError("CANCELLED")
            self.publication_uncertain = False
            track.unmute()
            self.pending_track = None
            self.pending = False
            self.feed = asyncio.create_task(self.publish_frames(capture))
            if quality == "auto": self.pacer = asyncio.create_task(self.adapt(capture, fps))
        except BaseException:
            await self.stop()
            raise

    async def adapt(self, capture, maximum):
        healthy = 0
        while self.capture is capture and self.publication is not None:
            await asyncio.sleep(3)
            try:
                track = self.publication.track
                stats = await asyncio.wait_for(track.get_stats(), 2)
                # Pinned native SDK enum: NONE=0, CPU=1, BANDWIDTH=2, OTHER=3.
                limited = any(s.outbound_rtp.outbound.quality_limitation_reason in (1, 2) for s in stats if s.HasField("outbound_rtp"))
                if self.capture is capture:
                    capture.fps, healthy = adaptive_rate(capture.fps, limited, healthy, maximum)
            except Exception:
                healthy = 0

    async def publish_frames(self, capture):
        try:
            async for data in capture.frames():
                if self.closed or self.capture is not capture: break
                frame = self.rtc.VideoFrame(capture.width, capture.height, self.rtc.VideoBufferType.RGBA, data)
                self.source.capture_frame(frame)
        except asyncio.CancelledError:
            raise
        except Exception:
            self.failure = "Screen sharing stopped. Select a source again to retry."
        finally:
            if self.capture is capture:
                await self.stop()

    async def stop(self):
        try: self.stop_share_local()
        except Exception: self.failure = "Screen cleanup required closing its source."
        audio, self.audio = self.audio, None
        capture, self.capture = self.capture, None
        source, self.source = self.source, None
        self.pending_track = None
        publication, self.publication = self.publication, None
        feed, self.feed = self.feed, None
        pacer, self.pacer = self.pacer, None
        self.pending = False
        if pacer is not None:
            pacer.cancel()
            await asyncio.gather(pacer, return_exceptions=True)
        if feed is not None and feed is not asyncio.current_task():
            feed.cancel()
            await asyncio.gather(feed, return_exceptions=True)
        try:
            try:
                if audio is not None: await audio.close()
            finally:
                if capture is not None: await capture.close()
        finally:
            try:
                if source is not None: await source.aclose()
            finally:
                if publication is not None:
                    try: await asyncio.wait_for(self.room.local_participant.unpublish_track(publication.sid), 3)
                    except Exception: pass

    async def watch(self, sid):
        await self.unwatch()
        if not sid: return
        if self.closed or not renderer_available(): raise ApiError("CAPTURE_UNAVAILABLE")
        for publication, _ in self.publications():
            if publication.sid == sid:
                self.watching = sid
                self.on_watch_changed()
                publication.set_subscribed(True)
                if publication.track is not None: self.subscribed(publication.track, publication)
                return
        raise ApiError("BAD_INPUT")

    async def usage_bytes(self):
        publication = self.publication
        if publication is None or publication.track is None: return 0
        try:
            stats = await asyncio.wait_for(publication.track.get_stats(), 2)
            total = sum(stat.outbound_rtp.sent.bytes_sent for stat in stats if stat.HasField("outbound_rtp"))
            delta = max(0, total - self.reported_bytes)
            self.reported_bytes = total
            return min(delta, 5 * 1024 * 1024 * 1024)
        except Exception:
            return 0

    def subscribed(self, track, publication):
        if not self.closed and publication.sid == self.watching and self.receiver is None:
            self.receiver = asyncio.create_task(self.receive(track, publication.sid))

    async def receive(self, track, sid):
        stream = None
        buffer = None
        heartbeat = None
        try:
            stream = self.rtc.VideoStream(track, capacity=1, format=self.rtc.VideoBufferType.RGBA)
            buffer = self.buffer_factory()
            self.buffer = buffer
            async def keep_static_frame():
                while self.buffer is buffer and not self.closed and sid == self.watching:
                    await asyncio.sleep(0.5)
                    publication = next((p for p, _ in self.publications() if p.sid == sid), None)
                    if (publication is not None and publication.track is not None and not publication.muted
                            and self.room.connection_state == self.rtc.ConnectionState.CONN_CONNECTED):
                        buffer.touch()
            heartbeat = asyncio.create_task(keep_static_frame())
            async for event in stream:
                if self.closed or sid != self.watching: break
                frame = event.frame
                # Reject oversized frames before making a Python copy; decoder
                # subscription quality limits will be added during media QA.
                if frame.width > 2560 or frame.height > 1440: continue
                buffer.write(frame.width, frame.height, frame.data)
        except asyncio.CancelledError:
            raise
        except Exception:
            self.failure = "Video playback stopped. Select the stream again to retry."
        finally:
            if heartbeat is not None:
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)
            if buffer is not None: buffer.close()
            if self.buffer is buffer: self.buffer = None
            if stream is not None: await stream.aclose()

    async def unwatch(self):
        sid, self.watching = self.watching, ""
        self.on_watch_changed()
        for publication, _ in self.publications():
            if publication.sid == sid: publication.set_subscribed(False)
        task, self.receiver = self.receiver, None
        if self.buffer is not None:
            self.buffer.close()
            self.buffer = None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def close(self):
        self.closed = True
        try: await self.stop()
        finally: await self.unwatch()

    def stop_local(self):
        # Stop pixels and local display before waiting on portal/network cleanup.
        try: self.stop_share_local()
        finally:
            buffer, self.buffer = self.buffer, None
            if buffer is not None: buffer.close()

    def stop_share_local(self):
        # Ending our publication must not interrupt a stream we are watching.
        actions = []
        if self.audio is not None: actions.append(self.audio.stop_local)
        if self.pending_track is not None: actions.append(self.pending_track.mute)
        if self.capture is not None: actions.append(self.capture.stop_local)
        if self.publication is not None and self.publication.track is not None:
            actions.append(self.publication.track.mute)
        failures = []
        for action in actions:
            try: action()
            except Exception as error: failures.append(error)
        if failures: raise failures[0]

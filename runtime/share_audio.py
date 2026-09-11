"""One explicitly selected application's audio, tied to screen-share lifetime."""
import asyncio
from app_audio import ApplicationAudio
from api import ApiError


class ShareAudio:
    def __init__(self, rtc, room):
        self.rtc, self.room = rtc, room
        self.capture = ApplicationAudio()
        self.source = self.publication = self.feed = None
        self.track = None
        self.error = ""

    async def prepare(self, serial):
        try:
            await self.capture.open(serial)
            self.source = self.rtc.AudioSource(48000, 2, queue_size_ms=120)
            self.track = self.rtc.LocalAudioTrack.create_audio_track("application-audio", self.source)
            self.track.mute()
        except BaseException:
            await self.close()
            raise

    async def publish(self):
        try:
            options = self.rtc.TrackPublishOptions(source=self.rtc.TrackSource.SOURCE_SCREENSHARE_AUDIO)
            self.publication = await asyncio.wait_for(self.room.local_participant.publish_track(self.track, options), 15)
            if self.capture.closed: raise ApiError("CANCELLED")
            self.track.unmute()
            self.feed = asyncio.create_task(self.frames())
        except BaseException:
            await self.close()
            raise

    async def frames(self):
        try:
            async for raw in self.capture.frames():
                frame = self.rtc.AudioFrame(raw, 48000, 2, len(raw) // 4)
                await asyncio.wait_for(self.source.capture_frame(frame), 1)
        except asyncio.CancelledError: raise
        except Exception:
            self.error = "Application audio stopped. Select its source again to resume audio."
        finally:
            await self.close()

    def stop_local(self):
        actions = [self.capture.close]
        if self.track is not None: actions.append(self.track.mute)
        if self.publication is not None and self.publication.track is not None: actions.append(self.publication.track.mute)
        if self.source is not None: actions.append(self.source.clear_queue)
        failures = []
        for action in actions:
            try: action()
            except Exception as error: failures.append(error)
        if failures: raise failures[0]

    async def close(self):
        try: self.stop_local()
        except Exception: self.error = "Application audio cleanup required closing its source."
        feed, self.feed = self.feed, None
        source, self.source = self.source, None
        publication, self.publication = self.publication, None
        self.track = None
        if feed is not None and feed is not asyncio.current_task():
            feed.cancel()
            await asyncio.gather(feed, return_exceptions=True)
        try:
            if source is not None: await source.aclose()
        finally:
            if publication is not None:
                try: await asyncio.wait_for(self.room.local_participant.unpublish_track(publication.sid), 3)
                except Exception: pass

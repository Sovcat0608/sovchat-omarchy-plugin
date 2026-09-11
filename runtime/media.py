"""Plugin-owned native LiveKit voice. Physical-device QA is still required.

There is deliberately no browser, Electron process, amplitude gate, server key,
or speculative screen-capture fallback. Capture requires an explicit join.
"""

import asyncio
import importlib.util

from api import ApiError
from video import VideoSession, capture_available, renderer_available
from audio_native import set_output_muted, device_rows
from playback import Playback
from preferences import DEFAULTS, validated


class Media:
    def __init__(self, enabled=False, rtc=None):
        self.enabled = enabled
        self.rtc = rtc
        self.room = None
        self.audio = None
        self.source = None
        self.track = None
        self.pending_track = None
        self.connecting = False
        self.muted = True
        self.video = None
        self.cleanup_tasks = set()
        self.playback = None
        self.deafened = False
        self.options = dict(DEFAULTS)
        self.afk = False

    def available(self):
        if not self.enabled:
            return False
        try:
            return self.rtc is not None or importlib.util.find_spec("livekit.rtc") is not None
        except ModuleNotFoundError:
            return False

    def state(self):
        result = {"available": self.available(), "connected": self.track is not None, "connecting": self.connecting,
                  "muted": self.muted, "deafened": self.deafened, "audioOptions": dict(self.options),
                  "screenSharingAvailable": self.available() and capture_available(),
                  "videoRenderer": self.available() and renderer_available()}
        if self.video is not None: result.update(self.video.state())
        if self.playback is not None:
            result["volumes"] = dict(self.playback.volumes)
            result["audioError"] = self.playback.error
        return result

    async def join(self, url, token):
        if not self.available():
            raise ApiError("MEDIA_UNAVAILABLE")
        await self.leave()
        self.connecting = True
        try:
            if self.rtc is None:
                from livekit import rtc
                self.rtc = rtc
            rtc = self.rtc
            if not hasattr(rtc, "PlatformAudio"):
                raise ApiError("MEDIA_UNAVAILABLE")
            self.audio = rtc.PlatformAudio()
            if self.options["input"]: self.audio.set_recording_device(self.options["input"])
            if self.options["output"]: self.audio.set_playout_device(self.options["output"])
            if hasattr(rtc, "AudioStream"):
                self.playback = Playback(rtc, self.options["output"])
                self.playback.set_master(self.options["outputVolume"])
                await self.playback.start()
                reference = next((device for device in self.audio.playout_devices()
                                  if self.playback.sink_name in device.id or self.playback.sink_name in device.name), None)
                if reference is None: raise ApiError("MEDIA_FAILED")
                self.audio.set_playout_device(reference.id)
            room = rtc.Room()
            self.room = room
            if hasattr(rtc, "VideoStream"):
                self.video = VideoSession(rtc, room)
                self.video.on_watch_changed = self.sync_audio_subscriptions
            # Audio auto-subscribes; video is fetched only when explicitly watched.
            @room.on("track_published")
            def on_track(publication, participant):
                if self.room is room and publication.kind == rtc.TrackKind.KIND_AUDIO:
                    publication.set_subscribed(self.wants_audio(publication, participant))

            @room.on("track_subscribed")
            def on_subscribed(track, publication, participant):
                if self.room is room and self.playback is not None and publication.kind == rtc.TrackKind.KIND_AUDIO:
                    self.playback.add(track, publication, participant)
                if self.room is room and self.video is not None:
                    self.video.subscribed(track, publication)

            @room.on("track_unpublished")
            def on_unpublished(publication, participant):
                if self.room is room and self.playback is not None: self.playback.remove(publication.sid)
                if self.room is room and self.video is not None and self.video.watching == publication.sid:
                    self.schedule_cleanup(self.video.unwatch())

            @room.on("track_unsubscribed")
            def on_unsubscribed(track, publication, participant):
                if self.room is room and self.playback is not None: self.playback.remove(publication.sid)
                if self.room is room and self.video is not None and self.video.watching == publication.sid:
                    self.schedule_cleanup(self.video.unwatch())

            @room.on("disconnected")
            def on_disconnected(*_):
                # A delayed event from an old room must not close a newer
                # call's devices. A current disconnect also releases the room
                # guard so the user can switch rooms or retry normally.
                if self.room is room:
                    self.room = None
                    self.release_capture()

            await asyncio.wait_for(self.room.connect(url, token, rtc.RoomOptions(auto_subscribe=False)), 20)
            for participant in self.room.remote_participants.values():
                for publication in participant.track_publications.values():
                    if publication.kind == rtc.TrackKind.KIND_AUDIO:
                        publication.set_subscribed(self.wants_audio(publication, participant))
            # Default WebRTC AEC/NS/AGC; RNNoise replacement is not a shipped decision.
            if hasattr(rtc, "PlatformAudioOptions"):
                self.source = self.audio.create_audio_source(options=rtc.PlatformAudioOptions(
                    echo_cancellation=self.options["echoCancellation"], noise_suppression=self.options["noiseSuppression"],
                    auto_gain_control=self.options["autoGainControl"]))
            else:
                self.source = self.audio.create_audio_source()
            track = rtc.LocalAudioTrack.create_audio_track("microphone", self.source)
            self.pending_track = track
            track.mute()
            options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
            await asyncio.wait_for(room.local_participant.publish_track(track, options), 15)
            if self.room is not room: raise ApiError("MEDIA_FAILED")
            self.track, self.pending_track = track, None
            self.connecting = False
            self.muted = True
            return self.state()
        except BaseException:
            await self.leave()
            raise
        finally:
            self.connecting = False

    def set_muted(self, muted):
        if not self.track or not isinstance(muted, bool):
            raise ApiError("BAD_INPUT")
        self.track.mute() if muted else self.track.unmute()
        self.muted = muted
        self.metadata()
        return self.state()

    def metadata(self):
        import json
        if self.room is not None and hasattr(self.room.local_participant, "set_metadata"):
            self.schedule_cleanup(self.room.local_participant.set_metadata(json.dumps(
                {"isSelfMuted": self.muted, "isSelfDeafened": self.deafened, "isAfk": self.afk})))

    async def set_deafened(self, value):
        if self.room is None or type(value) is not bool: raise ApiError("BAD_INPUT")
        if self.playback is not None: self.playback.set_deafened(value)
        else: await set_output_muted(value)
        self.deafened = value
        self.sync_audio_subscriptions()
        self.metadata()
        return self.state()

    def set_volume(self, data):
        if self.playback is None: raise ApiError("MEDIA_UNAVAILABLE")
        self.playback.set_volume(data.get("participantId"), data.get("volume"))
        return self.state()

    def wants_audio(self, publication, participant):
        if self.deafened: return False
        source = getattr(self.rtc.TrackSource, "SOURCE_SCREENSHARE_AUDIO", -999)
        if getattr(publication, "source", None) != source: return True
        # Never play an unwatched participant's application audio.
        return self.video is not None and any(p.sid == self.video.watching and owner.identity == participant.identity
                                              for p, owner in self.video.publications())

    def sync_audio_subscriptions(self):
        if self.room is None: return
        for participant in self.room.remote_participants.values():
            for publication in participant.track_publications.values():
                if publication.kind == self.rtc.TrackKind.KIND_AUDIO:
                    publication.set_subscribed(self.wants_audio(publication, participant))

    def devices(self):
        if not self.available(): raise ApiError("MEDIA_UNAVAILABLE")
        if self.rtc is None:
            from livekit import rtc
            self.rtc = rtc
        audio = self.audio or self.rtc.PlatformAudio()
        try: return {"inputs": device_rows(audio.recording_devices()), "outputs": device_rows(audio.playout_devices())}
        finally:
            if self.audio is None: audio.close()

    def configure(self, data):
        if self.room is not None: raise ApiError("MEDIA_BUSY")
        self.options = validated(dict(self.options, **data))
        return self.state()

    def release_capture(self):
        # Always release both handles, including partially initialized joins.
        failures = []
        def cleanup(action):
            try: action()
            except Exception as error: failures.append(error)
        if self.pending_track is not None: cleanup(self.pending_track.mute)
        self.pending_track = None
        self.connecting = False
        if self.track is not None: cleanup(self.track.mute)
        playback, self.playback = self.playback, None
        if playback is not None:
            cleanup(playback.stop_local)
            self.schedule_cleanup(playback.close())
        video, self.video = self.video, None
        if video is not None:
            cleanup(video.stop_local)
            self.schedule_cleanup(video.close())
        self.track = None
        self.muted = True
        self.deafened = False
        source, self.source = self.source, None
        audio, self.audio = self.audio, None
        if source is not None: cleanup(source.close)
        if audio is not None: cleanup(audio.close)
        if failures: raise failures[0]

    def schedule_cleanup(self, operation):
        task = asyncio.create_task(operation)
        self.cleanup_tasks.add(task)
        def finished(value):
            self.cleanup_tasks.discard(value)
            if not value.cancelled(): value.exception()
        task.add_done_callback(finished)

    async def leave(self):
        room, self.room = self.room, None
        try:
            self.release_capture()
        finally:
            if room is not None:
                try:
                    await asyncio.wait_for(room.disconnect(), 5)
                except Exception:
                    pass  # Capture is already stopped; never prevent shutdown.
        return self.state()

    async def shutdown(self):
        try:
            await self.leave()
        finally:
            tasks = list(self.cleanup_tasks)
            if tasks:
                try:
                    await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 6)
                except asyncio.TimeoutError:
                    pass  # Local capture and display handles were closed first.

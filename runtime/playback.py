"""Per-participant native playback; SDK echo reference is routed to a private sink.

No system default device, other application volume, or microphone source changes.
"""
import asyncio
import os
import re
import secrets
from api import ApiError


async def pulse(*args):
    process = await asyncio.create_subprocess_exec("pactl", *args, stdout=asyncio.subprocess.PIPE,
                                                  stderr=asyncio.subprocess.DEVNULL)
    try:
        output, _ = await asyncio.wait_for(process.communicate(), 3)
        if process.returncode or len(output) > 1024 * 1024: raise ApiError("MEDIA_FAILED")
        return output.decode()
    finally:
        if process.returncode is None: process.kill(); await process.wait()


def private_modules(output):
    result = []
    for line in output.splitlines():
        fields = line.split("\t", 3)
        if len(fields) < 3 or not fields[0].isdecimal() or fields[1] != "module-null-sink": continue
        match = re.search(r"(?:^|\s)sink_name=sovchat_ref_([1-9]\d{0,9})_[a-f0-9]{8}(?:\s|$)", fields[2])
        if match and int(match[1]) < 2**31: result.append((fields[0], int(match[1])))
    return result


class Playback:
    def __init__(self, rtc, device=""):
        import gi
        gi.require_version("Gst", "1.0")
        from gi.repository import Gst
        Gst.init(None)
        self.Gst, self.rtc, self.device = Gst, rtc, device
        self.sink_name = "sovchat_ref_" + str(os.getpid()) + "_" + secrets.token_hex(4)
        self.module = None
        self.tracks, self.tasks, self.volumes = {}, {}, {}
        self.deafened = False
        self.master = 1.0
        self.closed = False
        self.error = ""

    async def start(self):
        if not self.device:
            self.device = (await pulse("get-default-sink")).strip()
            if not self.device or len(self.device) > 512: raise ApiError("MEDIA_FAILED")
        # Remove only stale private reference sinks from crashed SovChat helpers.
        # Pulse 17 JSON can omit module IDs; the documented short listing has
        # explicit IDs. Never unload by module name (that would affect all sinks).
        for module_id, pid in private_modules(await pulse("list", "short", "modules")):
            try: os.kill(pid, 0)
            except ProcessLookupError: await pulse("unload-module", module_id)
            except PermissionError: pass
        result = (await pulse("load-module", "module-null-sink", "sink_name=" + self.sink_name,
                              "sink_properties=device.description=" + self.sink_name)).strip()
        if not result.isdecimal(): raise ApiError("MEDIA_FAILED")
        self.module = result

    def add(self, track, publication, participant):
        if self.closed or publication.sid in self.tasks: return
        source = getattr(getattr(self.rtc, "TrackSource", None), "SOURCE_SCREENSHARE_AUDIO", -999)
        identity = "$stream" if getattr(publication, "source", None) == source else participant.identity
        self.tasks[publication.sid] = asyncio.create_task(self.receive(track, publication.sid, identity))

    async def receive(self, track, sid, identity):
        Gst = self.Gst
        stream = None
        pipeline = None
        try:
            pipeline = Gst.parse_launch("appsrc name=pcm is-live=true format=time do-timestamp=true block=false max-bytes=19200 leaky-type=downstream ! queue max-size-buffers=4 max-size-bytes=0 max-size-time=0 leaky=downstream ! audioconvert ! audioresample ! volume name=gain ! pulsesink name=output buffer-time=60000 latency-time=20000")
            source, volume = pipeline.get_by_name("pcm"), pipeline.get_by_name("gain")
            source.set_property("caps", Gst.Caps.from_string("audio/x-raw,format=S16LE,layout=interleaved,rate=48000,channels=2"))
            output = pipeline.get_by_name("output")
            if self.device: output.set_property("device", self.device)
            output.set_property("stream-properties", Gst.Structure.new_from_string("props,application.name=(string)SovChat,media.name=(string)SovChat-playback"))
            self.tracks[sid] = (identity, pipeline, volume)
            volume.set_property("volume", self.gain(identity))
            if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE: raise ApiError("MEDIA_FAILED")
            stream = self.rtc.AudioStream(track, capacity=2, sample_rate=48000, num_channels=2, frame_size_ms=10)
            async for event in stream:
                if self.closed: break
                if pipeline.get_bus().pop_filtered(Gst.MessageType.ERROR | Gst.MessageType.EOS): raise ApiError("MEDIA_FAILED")
                frame = event.frame
                raw = bytes(frame.data)
                if not raw or len(raw) > 19200: raise ApiError("MEDIA_FAILED")
                buffer = Gst.Buffer.new_allocate(None, len(raw), None)
                buffer.fill(0, raw)
                buffer.duration = frame.samples_per_channel * Gst.SECOND // 48000
                if source.emit("push-buffer", buffer) != Gst.FlowReturn.OK: break
        except asyncio.CancelledError:
            raise
        except Exception:
            self.error = "A participant's playback stopped. Leave and rejoin voice to recover."
        finally:
            self.tracks.pop(sid, None)
            self.tasks.pop(sid, None)
            if pipeline is not None: pipeline.set_state(Gst.State.NULL)
            if stream is not None: await stream.aclose()

    def remove(self, sid):
        if sid in self.tracks: self.tracks[sid][1].set_state(self.Gst.State.NULL)
        task = self.tasks.get(sid)
        if task: task.cancel()

    def set_volume(self, identity, value):
        if not isinstance(identity, str) or len(identity) > 191 or type(value) not in (int, float) or not 0 <= value <= 2:
            raise ApiError("BAD_INPUT")
        self.volumes[identity] = value
        for user, _, volume in self.tracks.values():
            if user == identity: volume.set_property("volume", self.gain(user))

    def gain(self, identity):
        return 0.0 if self.deafened else self.master * self.volumes.get(identity, 1.0)

    def set_master(self, value):
        if type(value) not in (int, float) or not 0 <= value <= 1: raise ApiError("BAD_INPUT")
        self.master = value
        for user, _, volume in self.tracks.values(): volume.set_property("volume", self.gain(user))

    def set_deafened(self, value):
        self.deafened = value
        for user, _, volume in self.tracks.values(): volume.set_property("volume", self.gain(user))

    def stop_local(self):
        self.closed = True
        for _, pipeline, _ in self.tracks.values(): pipeline.set_state(self.Gst.State.NULL)
        for task in self.tasks.values(): task.cancel()

    async def close(self):
        self.stop_local()
        await asyncio.gather(*list(self.tasks.values()), return_exceptions=True)
        if self.module is not None:
            module, self.module = self.module, None
            try: await pulse("unload-module", module)
            except Exception: pass

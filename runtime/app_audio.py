"""Explicit selected-application PipeWire capture; never a default microphone/mix."""
import asyncio
import json
import os
import secrets
import time
from api import ApiError


async def graph():
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec("pw-dump", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        raw, _ = await asyncio.wait_for(proc.communicate(), 3)
        if proc.returncode or len(raw) > 4 * 1024 * 1024: raise ApiError("CAPTURE_UNAVAILABLE")
        return json.loads(raw)
    except (OSError, ValueError, asyncio.TimeoutError):
        raise ApiError("CAPTURE_UNAVAILABLE") from None
    finally:
        if proc is not None and proc.returncode is None: proc.kill(); await proc.wait()


async def applications():
    result = []
    for node in await graph():
        props = node.get("info", {}).get("props", {})
        name = str(props.get("application.name") or props.get("node.description") or props.get("node.name") or "Application")[:100]
        serial = str(props.get("object.serial", ""))
        if (props.get("media.class") == "Stream/Output/Audio"
            and str(props.get("application.process.id")) != str(os.getpid())
            and "sovchat" not in name.lower() and serial.isdecimal() and len(serial) <= 20):
            result.append({"id": serial, "name": name, "nodeId": node["id"]})
    return result[:32]


def selected_link_only(nodes, capture_name, selected_serial):
    target = next((node["id"] for node in nodes if str(node.get("info", {}).get("props", {}).get("object.serial")) == selected_serial), None)
    capture = next((node["id"] for node in nodes if node.get("info", {}).get("props", {}).get("node.name") == capture_name), None)
    links = [node["info"] for node in nodes if node.get("type") == "PipeWire:Interface:Link" and node.get("info", {}).get("input-node-id") == capture]
    return target is not None and capture is not None and bool(links) and all(link.get("output-node-id") == target for link in links)


class ApplicationAudio:
    def __init__(self):
        self.pipeline = self.sink = None
        self.closed = False
        self.first = None

    async def open(self, serial):
        if not isinstance(serial, str) or not serial.isdecimal() or len(serial) > 20: raise ApiError("BAD_INPUT")
        if not any(app["id"] == serial for app in await applications()): raise ApiError("CAPTURE_UNAVAILABLE")
        import gi
        gi.require_version("Gst", "1.0")
        from gi.repository import Gst
        Gst.init(None)
        self.Gst = Gst
        capture_name = "sovchat-audio-" + secrets.token_hex(8)
        try:
            self.pipeline = Gst.parse_launch("pipewiresrc name=input do-timestamp=true ! audioconvert ! audioresample ! audio/x-raw,format=S16LE,channels=2,rate=48000 ! appsink name=pcm max-buffers=2 drop=true sync=false")
            source = self.pipeline.get_by_name("input")
            source.set_property("client-name", "SovChat application audio")
            source.set_property("target-object", serial)
            source.set_property("on-disconnect", 2)
            source.set_property("stream-properties", Gst.Structure.new_from_string(
                "props,stream.capture.sink=(boolean)true,stream.dont-reconnect=(boolean)true,node.dont-fallback=(boolean)true,node.name=(string)" + capture_name))
            self.sink = self.pipeline.get_by_name("pcm")
            if self.pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE: raise ApiError("CAPTURE_FAILED")
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                value = self.pull()
                if value is not None:
                    if not selected_link_only(await graph(), capture_name, serial): raise ApiError("CAPTURE_FAILED")
                    self.first = value
                    return
                await asyncio.sleep(0.01)
            raise ApiError("CAPTURE_FAILED")
        except BaseException:
            self.close()
            raise

    def pull(self):
        if self.closed or self.pipeline is None: raise ApiError("CAPTURE_FAILED")
        if self.pipeline.get_bus().pop_filtered(self.Gst.MessageType.ERROR | self.Gst.MessageType.EOS): raise ApiError("CAPTURE_FAILED")
        sample = self.sink.emit("try-pull-sample", 0)
        if sample is None: return None
        buffer = sample.get_buffer()
        size = buffer.get_size()
        if not 0 < size <= 38400 or size % 4: raise ApiError("CAPTURE_FAILED")
        return buffer.extract_dup(0, size)

    async def frames(self):
        last = time.monotonic()
        while not self.closed:
            raw, self.first = self.first, None
            if raw is None: raw = self.pull()
            if raw is not None:
                last = time.monotonic()
                # Bounded 20ms chunks; never keep a speech/activity gate or repeat audio.
                for offset in range(0, len(raw), 3840): yield raw[offset:offset + 3840]
            elif time.monotonic() - last > 5:
                raise ApiError("CAPTURE_FAILED")
            await asyncio.sleep(0.005)

    def close(self):
        self.closed = True
        pipeline, self.pipeline = self.pipeline, None
        self.sink = self.first = None
        if pipeline is not None: pipeline.set_state(self.Gst.State.NULL)

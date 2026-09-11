"""One explicit ScreenCast grant and bounded in-memory PipeWire frame consumer."""

import asyncio
import os
import secrets
import time

from api import ApiError

DEST = "org.freedesktop.portal.Desktop"
PATH = "/org/freedesktop/portal/desktop"
IFACE = "org.freedesktop.portal.ScreenCast"


class PortalCapture:
    def __init__(self):
        self.bus = None
        self.session = None
        self.pending = None
        self.fd = None
        self.pipeline = None
        self.sink = None
        self.responses = {}
        self.closed = asyncio.Event()
        self.width = 1280
        self.height = 720
        self.fps = 30

    async def call(self, path, interface, member, signature="", body=None):
        from dbus_next import Message, MessageType
        response = await asyncio.wait_for(self.bus.call(Message(
            destination=DEST, path=path, interface=interface, member=member,
            signature=signature, body=body or [])), 10)
        if response.message_type == MessageType.ERROR:
            raise ApiError("CAPTURE_FAILED")
        return response

    def message(self, message):
        from dbus_next import MessageType
        if message.message_type != MessageType.SIGNAL:
            return
        if message.interface == "org.freedesktop.portal.Session" and message.member == "Closed" and message.path == self.session:
            self.closed.set()
        if message.interface == "org.freedesktop.portal.Request" and message.member == "Response":
            future = self.responses.get(message.path)
            if future is not None and not future.done():
                future.set_result(message.body)

    async def request(self, member, signature, body, options):
        from dbus_next import Variant
        token = "sovchat_" + secrets.token_hex(16)
        sender = self.bus.unique_name[1:].replace(".", "_")
        path = "/org/freedesktop/portal/desktop/request/" + sender + "/" + token
        self.pending = path
        response = asyncio.get_running_loop().create_future()
        self.responses[path] = response
        try:
            # Subscribe before the method call: some portals answer immediately.
            reply = await self.call(PATH, IFACE, member, signature,
                                    body + [dict(options, handle_token=Variant("s", token))])
            if reply.body != [path]:
                raise ApiError("CAPTURE_FAILED")
            code, result = await asyncio.wait_for(response, 90)
            if code != 0:
                raise ApiError("CAPTURE_CANCELLED" if code == 1 else "CAPTURE_FAILED")
            self.pending = None
            return result
        finally:
            self.responses.pop(path, None)

    async def open(self, source="monitor"):
        if source not in {"monitor", "window"} or self.bus is not None or self.closed.is_set():
            raise ApiError("BAD_INPUT")
        from dbus_next import Message, MessageType, Variant
        from dbus_next.aio import MessageBus
        import gi
        gi.require_version("Gst", "1.0")
        from gi.repository import Gst
        self.Gst = Gst
        Gst.init(None)
        try:
            self.bus = await MessageBus(negotiate_unix_fd=True).connect()
            self.bus.add_message_handler(self.message)
            for interface in ("org.freedesktop.portal.Request", "org.freedesktop.portal.Session"):
                result = await self.bus.call(Message(destination="org.freedesktop.DBus",
                    path="/org/freedesktop/DBus", interface="org.freedesktop.DBus", member="AddMatch",
                    signature="s", body=["type='signal',sender='org.freedesktop.portal.Desktop',interface='" + interface + "'"]))
                if result.message_type == MessageType.ERROR:
                    raise ApiError("CAPTURE_FAILED")
            properties = (await self.call(PATH, "org.freedesktop.DBus.Properties", "GetAll", "s", [IFACE])).body[0]
            source_type = 1 if source == "monitor" else 2
            if not properties["AvailableSourceTypes"].value & source_type:
                raise ApiError("CAPTURE_UNAVAILABLE")
            created = await self.request("CreateSession", "a{sv}", [], {
                "session_handle_token": Variant("s", "sovchat_" + secrets.token_hex(16))})
            self.session = created["session_handle"].value
            cursor = 2 if properties["AvailableCursorModes"].value & 2 else 1
            await self.request("SelectSources", "oa{sv}", [self.session], {
                "types": Variant("u", source_type), "multiple": Variant("b", False),
                "cursor_mode": Variant("u", cursor)})
            started = await self.request("Start", "osa{sv}", [self.session, ""], {})
            streams = started["streams"].value
            if len(streams) != 1:
                raise ApiError("CAPTURE_FAILED")
            node, props = streams[0]
            if "source_type" in props and props["source_type"].value != source_type:
                raise ApiError("CAPTURE_FAILED")
            reply = await self.call(PATH, IFACE, "OpenPipeWireRemote", "oa{sv}", [self.session, {}])
            try:
                index = reply.body[0]
                if type(index) is not int or not 0 <= index < len(reply.unix_fds):
                    raise ApiError("CAPTURE_FAILED")
                self.fd = os.dup(reply.unix_fds[index])
            finally:
                for fd in reply.unix_fds:
                    os.close(fd)
            self.pipeline = Gst.Pipeline.new("sovchat-screen")
            names = ("pipewiresrc", "videoconvert", "videoscale", "videorate", "appsink")
            elements = [Gst.ElementFactory.make(name, None) for name in names]
            if any(element is None for element in elements):
                raise ApiError("CAPTURE_UNAVAILABLE")
            capture, convert, scale, rate, self.sink = elements
            capture.set_property("fd", self.fd)
            serial = props.get("pipewire-serial")
            if serial is not None and capture.find_property("target-object"):
                capture.set_property("target-object", str(serial.value))
            else:
                capture.set_property("path", str(node))
            capture.set_property("do-timestamp", True)
            if capture.find_property("on-disconnect"):
                capture.set_property("on-disconnect", 2)
            scale.set_property("add-borders", True)
            rate.set_property("drop-only", True)
            self.sink.set_property("caps", Gst.Caps.from_string(
                f"video/x-raw,format=RGBA,width={self.width},height={self.height},framerate={self.fps}/1"))
            self.sink.set_property("max-buffers", 1)
            self.sink.set_property("drop", True)
            self.sink.set_property("sync", False)
            for element in elements: self.pipeline.add(element)
            for left, right in zip(elements, elements[1:]):
                if not left.link(right): raise ApiError("CAPTURE_FAILED")
            if self.pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
                raise ApiError("CAPTURE_FAILED")
            return self
        except BaseException:
            await self.close()
            raise

    async def frames(self):
        started = time.monotonic()
        latest = None
        while not self.closed.is_set():
            if self.pipeline.get_bus().pop_filtered(self.Gst.MessageType.ERROR | self.Gst.MessageType.EOS):
                raise ApiError("CAPTURE_FAILED")
            sample = self.sink.emit("try-pull-sample", 0)
            if sample is not None:
                buffer = sample.get_buffer()
                size = self.width * self.height * 4
                if buffer.get_size() != size: raise ApiError("CAPTURE_FAILED")
                latest = buffer.extract_dup(0, size)
            elif latest is None and time.monotonic() - started > 8:
                raise ApiError("CAPTURE_FAILED")
            # Wayland captures are damage-driven: an unchanged window may emit
            # nothing further. Keep a bounded cadence while the grant and source
            # are alive; portal closure / PipeWire disconnect still stop the feed.
            if latest is not None:
                yield latest
            await asyncio.sleep(1 / self.fps)

    def stop_local(self):
        self.closed.set()
        pipeline, self.pipeline = self.pipeline, None
        self.sink = None
        if pipeline is not None:
            pipeline.set_state(self.Gst.State.NULL)
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    async def close(self):
        self.stop_local()
        if self.bus is not None:
            for path, interface in ((self.pending, "org.freedesktop.portal.Request"),
                                    (self.session, "org.freedesktop.portal.Session")):
                if path:
                    try: await asyncio.wait_for(self.call(path, interface, "Close"), 2)
                    except Exception: pass
            self.pending = self.session = None
            self.bus.remove_message_handler(self.message)
            self.bus.disconnect()
            self.bus = None

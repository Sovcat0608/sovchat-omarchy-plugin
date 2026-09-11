"""Bounded command lanes: safety controls never queue behind HTTP or a picker."""

import asyncio

CONTROL_OPS = frozenset({"voice-mute", "voice-leave", "voice-deafen", "voice-idle", "screen-stop", "screen-unwatch", "logout"})
MEDIA_START_OPS = frozenset({"voice-join", "screen-start"})


class CommandRunner:
    def __init__(self, broker, emit):
        self.broker = broker
        self.emit = emit
        self.normal = None
        self.control = None
        self.controls = {}
        self.normal_op = None
        self.ids = set()

    def reject(self, request_id, code):
        self.emit({"id": request_id, "ok": False, "code": code,
                   "error": "Another action is still completing." if code == "BUSY"
                   else "The action was interrupted. Check its result before retrying."})

    async def submit(self, request):
        request_id = request.get("id") if isinstance(request, dict) else None
        if type(request_id) is not int or not 0 <= request_id <= 2147483647:
            self.emit(await self.broker.reply(request))
            return
        if request_id in self.ids:
            raise ValueError("Duplicate command ID")
        op = request.get("op")
        priority = op in CONTROL_OPS if isinstance(op, str) else False
        lane = "control" if priority else "normal"
        pending = self.controls.get(op) if priority else self.normal
        if pending is not None and not pending.done():
            self.reject(request_id, "BUSY")
            return
        # Do not start account/room/media mutations during a safety transition.
        if (not priority and any(not task.done() for task in self.controls.values())) or (
                priority and "logout" in self.controls and not self.controls["logout"].done()):
            self.reject(request_id, "BUSY")
            return
        if priority and self.normal is not None and not self.normal.done():
            if op == "logout" or (op in {"voice-leave", "screen-stop"} and self.normal_op in MEDIA_START_OPS):
                self.normal.cancel()
        self.ids.add(request_id)
        if not priority:
            self.normal_op = op
        task = asyncio.create_task(self.run(request, lane))
        setattr(self, lane, task)
        if priority: self.controls[op] = task

    async def run(self, request, lane):
        try:
            self.emit(await self.broker.reply(request))
        except asyncio.CancelledError:
            self.reject(request["id"], "CANCELLED")
            raise
        finally:
            self.ids.discard(request["id"])
            if lane == "control" and self.controls.get(request["op"]) is asyncio.current_task():
                self.controls.pop(request["op"], None)

    async def close(self):
        tasks = [task for task in [self.normal, *self.controls.values()] if task is not None]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

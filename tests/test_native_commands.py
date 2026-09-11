"""Priority controls and late-worker credential isolation; no network or devices."""

import asyncio
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "native-plugin/runtime"))
from api import Api
from broker import Broker
from commands import CommandRunner


class CommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_mute_preempts_slow_refresh_without_cancelling_it(self):
        gate = asyncio.Event()
        replies = []
        class Fake:
            async def reply(self, request):
                if request["op"] == "refresh": await gate.wait()
                return {"id": request["id"], "ok": True}
        runner = CommandRunner(Fake(), replies.append)
        await runner.submit({"id": 1, "op": "refresh"})
        await runner.submit({"id": 2, "op": "voice-mute"})
        await asyncio.wait_for(runner.control, 0.2)
        self.assertEqual([r["id"] for r in replies], [2])
        self.assertFalse(runner.normal.done())
        gate.set()
        await runner.normal
        self.assertEqual([r["id"] for r in replies], [2, 1])
        await runner.close()

    async def test_leave_cancels_pending_join_and_bounds_command_lanes(self):
        started = asyncio.Event()
        replies = []
        class Fake:
            async def reply(self, request):
                if request["op"] == "voice-join":
                    started.set()
                    await asyncio.Future()
                return {"id": request["id"], "ok": True}
        runner = CommandRunner(Fake(), replies.append)
        await runner.submit({"id": 1, "op": "voice-join"})
        await started.wait()
        await runner.submit({"id": 2, "op": "send"})
        self.assertEqual(replies[0]["code"], "BUSY")
        await runner.submit({"id": 3, "op": "voice-leave"})
        await asyncio.wait_for(runner.control, 0.2)
        await asyncio.gather(runner.normal, return_exceptions=True)
        self.assertTrue(any(r.get("code") == "CANCELLED" for r in replies))
        self.assertTrue(any(r.get("id") == 3 and r.get("ok") for r in replies))
        await runner.close()

    async def test_cancelled_http_worker_cannot_restore_credentials_after_logout(self):
        entered, release = threading.Event(), threading.Event()
        class SlowApi(Api):
            def validate_session(self):
                entered.set()
                release.wait(2)
                self.token = "late-rotated-secret"
                self.session = {"userId": "old"}
                return {"session": self.session}
            def logout(self): self.clear(); return {"session": None}
        api = SlowApi()
        api.token, api.session = "initial-secret", {"userId": "old"}
        broker = Broker(api=api)
        events = []
        broker.emit = events.append
        runner = CommandRunner(broker, events.append)
        try:
            await runner.submit({"id": 1, "op": "refresh"})
            while not entered.is_set(): await asyncio.sleep(0.001)
            await runner.submit({"id": 2, "op": "logout"})
            await asyncio.wait_for(runner.control, 0.3)
            self.assertIsNone(api.token)
            self.assertIsNone(api.session)
            self.assertTrue(any(e.get("event") == "session" for e in events))
            release.set()
            await asyncio.sleep(0.05)
            self.assertIsNone(api.token)
            self.assertIsNone(api.session)
            self.assertNotIn("secret", str(events))
        finally:
            release.set()
            await runner.close()


if __name__ == "__main__": unittest.main()

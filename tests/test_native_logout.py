"""Logout revokes only this token, survives local failure and is retryable."""
import asyncio
import os
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import AsyncMock, patch
os.environ["SOVCHAT_NATIVE_DISABLE_KEYRING"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "native-plugin/runtime"))
from api import ApiError
from features import NativeApi
from broker import Broker
from session_lifecycle import revoke


class Transport:
    def __init__(self, *results): self.results, self.calls = list(results), []
    def request(self, url, method="GET", headers=None, body=None):
        self.calls.append((url, method, headers))
        result = self.results.pop(0)
        if isinstance(result, Exception): raise result
        return result


def api(*results):
    value = NativeApi(Transport(*results))
    value.token, value.session = "private-test-token", {"userId": "qa"}
    return value


class RevocationTests(unittest.TestCase):
    def test_logout_is_confirmed_by_rejection_of_same_token(self):
        value = api((200, {"ok": True}), (401, {}))
        revoke(value)
        self.assertEqual([x[1] for x in value.transport.calls], ["POST", "GET"])
        self.assertTrue(all(x[2]["Authorization"] == "Bearer private-test-token" for x in value.transport.calls))
        self.assertIsNotNone(value.token)  # Caller controls local clearing.

    def test_livekit_pending_after_database_delete_still_verifies_revocation(self):
        value = api((503, {"code": "VOICE_REVOCATION_PENDING"}), (401, {}))
        revoke(value)
        self.assertEqual(len(value.transport.calls), 2)

    def test_success_response_alone_does_not_prove_logout(self):
        value = api((200, {"ok": True}), (200, {"session": {"userId": "qa"}}))
        with self.assertRaisesRegex(ApiError, "LOGOUT_PENDING"): revoke(value)


class LogoutTests(unittest.IsolatedAsyncioTestCase):
    async def test_media_shutdown_failure_cannot_skip_server_revocation(self):
        value = api((200, {}), (401, {}))
        broker = Broker(api=value)
        broker.media.shutdown = AsyncMock(side_effect=RuntimeError("media failure"))
        await broker.shutdown()
        self.assertEqual(len(value.transport.calls), 2)
        self.assertIsNone(value.token)

    async def test_media_logout_failure_cannot_hide_auth_result(self):
        value = api((200, {}), (401, {}))
        broker = Broker(api=value)
        broker.media.leave = AsyncMock(side_effect=RuntimeError("media failure"))
        response = await broker.reply({"id": 1, "op": "logout"})
        self.assertIsInstance(response, dict)
        self.assertIsNone(value.token)
        self.assertIsNone(broker.logout_pending)
        self.assertEqual(len(value.transport.calls), 2)

    async def test_room_cleanup_failure_does_not_lock_ui(self):
        broker = Broker()
        broker.room_id = "old"
        broker.media.room = object()
        broker.media.leave = AsyncMock(side_effect=RuntimeError("media failure"))
        with self.assertRaises(RuntimeError):
            await broker.observe({"currentRoom": {"id": "new"}})
        self.assertFalse(broker.room_transition)
        self.assertEqual(broker.room_id, "old")

    async def test_room_cleanup_cannot_resurrect_snapshot_after_logout(self):
        broker = Broker()
        broker.room_id = "old"
        broker.media.room = object()
        entered, release = asyncio.Event(), asyncio.Event()
        async def leaving(): entered.set(); await release.wait()
        broker.media.leave = leaving
        events = []
        broker.emit = events.append
        task = asyncio.create_task(broker.observe({"currentRoom": {"id": "new"}}))
        await entered.wait()
        broker.generation += 1
        broker.room_transition = False
        broker.room_id = None
        release.set()
        with self.assertRaisesRegex(ApiError, "CANCELLED"): await task
        self.assertIsNone(broker.room_id)
        self.assertNotIn("currentRoom", str(events))

    async def test_cancelled_login_revokes_late_created_session(self):
        entered, release, revoked = threading.Event(), threading.Event(), threading.Event()
        class SlowLogin(NativeApi):
            def login(self, data):
                entered.set()
                release.wait(2)
                self.token, self.session = "late-own-session", {"userId": "qa"}
                return {"session": self.session}
        value = SlowLogin()
        broker = Broker(api=value)
        def capture(target):
            self.assertEqual(target.token, "late-own-session")
            revoked.set()
        with patch("broker.revoke", side_effect=capture):
            task = asyncio.create_task(broker.api_work("login", {}))
            while not entered.is_set(): await asyncio.sleep(0.001)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            release.set()
            self.assertTrue(await asyncio.to_thread(revoked.wait, 2))
        self.assertIsNone(value.token)
        self.assertIsNone(value.session)

    async def test_failed_remember_save_revokes_new_session(self):
        class Login(NativeApi):
            def login(self, data):
                self.token, self.session = "new-session", {"userId": "qa"}
                return {"session": self.session}
        value = Login(Transport((200, {}), (401, {})))
        broker = Broker(api=value)
        broker.vault.program = "test-only"
        broker.vault.clear = AsyncMock()
        broker.vault.save = AsyncMock(side_effect=ApiError("KEYRING_UNAVAILABLE"))
        response = await broker.reply({"id": 1, "op": "login", "data": {"rememberMe": True}})
        self.assertEqual(response["code"], "KEYRING_UNAVAILABLE")
        self.assertIsNone(value.token)
        self.assertEqual(len(value.transport.calls), 2)

    async def test_keyring_failure_cannot_skip_server_logout(self):
        value = api((200, {}), (401, {}))
        broker = Broker(api=value)
        broker.vault.clear = AsyncMock(side_effect=ApiError("KEYRING_UNAVAILABLE"))
        response = await broker.reply({"id": 1, "op": "logout"})
        self.assertEqual(response["code"], "KEYRING_UNAVAILABLE")
        self.assertEqual(len(value.transport.calls), 2)
        self.assertIsNone(value.token)
        self.assertIsNone(broker.logout_pending)

    async def test_network_failure_keeps_only_revocation_handle_and_retry_works(self):
        value = api(ApiError("NETWORK"), (200, {}), (401, {}))
        broker = Broker(api=value)
        first = await broker.reply({"id": 1, "op": "logout"})
        self.assertEqual(first["code"], "LOGOUT_PENDING")
        self.assertTrue(first["signedOut"])
        self.assertIsNone(value.token)
        self.assertIsNotNone(broker.logout_pending)
        blocked = await broker.reply({"id": 2, "op": "login", "data": {}})
        self.assertEqual(blocked["code"], "LOGOUT_PENDING")
        second = await broker.reply({"id": 3, "op": "logout"})
        self.assertTrue(second["ok"])
        self.assertIsNone(broker.logout_pending)
        self.assertNotIn("private-test-token", str([first, second]))

    async def test_graceful_shutdown_revokes_nonremembered_session(self):
        value = api((200, {}), (401, {}))
        broker = Broker(api=value)
        await broker.shutdown()
        self.assertEqual(len(value.transport.calls), 2)
        self.assertIsNone(value.token)

    async def test_graceful_shutdown_preserves_opted_in_remembered_session(self):
        value = api()
        broker = Broker(api=value); broker.remember = True
        await broker.shutdown()
        self.assertEqual(value.transport.calls, [])
        self.assertIsNone(value.token)


if __name__ == "__main__": unittest.main()

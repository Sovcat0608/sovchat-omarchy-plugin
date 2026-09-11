"""Shared feature contracts and native safety boundaries. No production requests."""
import asyncio
import json
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "native-plugin/runtime"))
from api import ApiError
from features import NativeApi, local_path, message_details
from broker import Broker
from commands import CommandRunner


class Transport:
    def __init__(self, payload=None, status=200): self.payload, self.status, self.calls = payload or {}, status, []
    def request(self, *args): self.calls.append(args); return self.status, self.payload


class FeaturesTests(unittest.TestCase):
    def test_switcher_includes_current_and_owned_room_codes_without_leaking_extra_fields(self):
        result = self.api().room_snapshot({
            "currentRoom": {"id": "current", "name": "Current", "code": "CURRENT", "secret": "NEVER"},
            "ownedRoom": {"id": "owned", "name": "Owned", "code": "OWNED", "isOwned": True},
            "joinedRooms": [{"id": "joined", "name": "Joined", "code": "JOINED"}]})
        self.assertEqual(result["roomCodes"], {"current": "CURRENT", "owned": "OWNED", "joined": "JOINED"})
        self.assertNotIn("code", result["currentRoom"])
        self.assertNotIn("NEVER", str(result))

    def api(self, payload=None, status=200):
        api = NativeApi(Transport(payload, status)); api.token = "test-token"
        return api

    def test_private_reply_and_attachments_use_shared_multipart_contract(self):
        api = self.api()
        with patch("features.upload_files", return_value=[("example.txt", "text/plain", b"QA only")]):
            result = api.send({"body": "hello", "replyToMessageId": "message-1", "whisperRecipientIds": ["user-2"], "files": ["file:///tmp/test.txt"]})
        self.assertTrue(result["sent"])
        url, method, headers, body = api.transport.calls[0]
        self.assertEqual(method, "POST")
        self.assertIn(b'"replyToMessageId": "message-1"', body)
        self.assertIn(b'"whisperRecipientIds": ["user-2"]', body)
        self.assertIn(b'name="files"; filename="example.txt"', body)
        self.assertIn(b"QA only", body)
        self.assertNotIn(b"test-token", body)

    def test_empty_or_oversized_recipient_message_rejected_before_network(self):
        api = self.api()
        for data in ({"body": " "}, {"body": "hi", "whisperRecipientIds": ["a"] * 33}, {"body": "hi", "replyToMessageId": "../other"}):
            with self.assertRaises(ApiError): api.send(data)
        self.assertEqual(api.transport.calls, [])

    def test_message_projection_keeps_context_but_drops_urls_and_unknown_fields(self):
        result = message_details({"id": "m", "userId": "u", "body": "<b>plain</b>",
            "whisper": {"recipientIds": ["u", "v"]}, "replyTo": {"id": "r", "body": "quote", "nickname": "Other", "sessionToken": "SECRET"},
            "attachments": [{"id": "a", "fileName": "file.txt", "url": "https://evil.invalid/"}],
            "reactions": [{"emoji": "👍", "count": 2, "reactedByMe": True, "secret": "SECRET"}], "sessionToken": "SECRET"})
        self.assertTrue(result["private"])
        self.assertEqual(result["recipientIds"], ["u", "v"])
        self.assertEqual(result["replyTo"]["id"], "r")
        self.assertNotIn("SECRET", str(result))
        self.assertNotIn("evil.invalid", str(result))

    def test_room_actions_are_allowlisted_and_confirmed_on_ui_not_server_bypassed(self):
        api = self.api({"joinedRooms": []})
        api.room_action({"action": "ban-owned-member", "userId": "user-2"})
        self.assertEqual(json.loads(api.transport.calls[-1][3]), {"action": "ban-owned-member", "userId": "user-2"})
        for data in ({"action": "admin"}, {"action": "remove-room", "roomId": "x?admin=true"},
                     {"action": "update-owned", "name": "QA", "fillerMode": False, "dailyStreamLimitMinutes": -1}):
            with self.assertRaises(ApiError): api.room_action(data)

    def test_applied_room_change_error_is_distinct_and_not_retried(self):
        api = self.api({"code": "VOICE_REVOCATION_PENDING", "databaseChangeApplied": True}, 503)
        with self.assertRaises(ApiError) as caught: api.room_action({"action": "reset-owned-code"})
        self.assertEqual(caught.exception.code, "VOICE_REVOCATION_PENDING")
        self.assertEqual(len(api.transport.calls), 1)

    def test_file_selection_only_accepts_local_file_urls(self):
        self.assertEqual(local_path("file:///tmp/QA%20file.txt"), "/tmp/QA file.txt")
        for value in ("https://example.test/x", "file://remote/share", "/tmp/a", "file:///tmp/a?token=x", "file:///tmp/%00"):
            with self.assertRaises(ApiError): local_path(value)

    def test_stream_allowance_requires_explicit_valid_remaining_value(self):
        self.assertIsNone(self.api({"remainingSeconds": None}).stream_usage()["streamUsage"]["remainingSeconds"])
        self.assertEqual(self.api({"remainingSeconds": 0}).stream_usage()["streamUsage"]["remainingSeconds"], 0)
        for value in ({}, {"remainingSeconds": -1}, {"remainingSeconds": False}, {"remainingSeconds": "100"}):
            with self.assertRaises(ApiError): self.api(value).stream_usage()

    def test_profile_patch_does_not_forward_arbitrary_properties(self):
        api = self.api({"nickname": "QA", "avatarId": "avatar-1"})
        api.profile({"nickname": "QA", "sessionToken": "SECRET"})
        self.assertEqual(json.loads(api.transport.calls[-1][3]), {"nickname": "QA"})


class SafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_logout_preempts_slow_screen_stop(self):
        started = asyncio.Event()
        class Fake:
            async def reply(self, request):
                if request["op"] == "screen-stop": started.set(); await asyncio.Future()
                return {"id": request["id"], "ok": True}
        replies = []
        runner = CommandRunner(Fake(), replies.append)
        await runner.submit({"id": 1, "op": "screen-stop"})
        await started.wait()
        await runner.submit({"id": 2, "op": "logout"})
        await asyncio.wait_for(runner.control, 0.2)
        self.assertEqual(replies, [{"id": 2, "ok": True}])
        await runner.close()

    async def test_stream_clock_stops_local_capture_without_http(self):
        import time
        broker = Broker()
        video = Mock(publication=object(), stop=AsyncMock())
        broker.media.video = video
        broker.stream_deadline = time.monotonic() - 1
        task = asyncio.create_task(broker.media_clock())
        try:
            await asyncio.sleep(0.15)
            video.stop_share_local.assert_called_once()
            video.stop.assert_awaited_once()
        finally:
            task.cancel(); await asyncio.gather(task, return_exceptions=True)
            broker.media.video = None
            await broker.media.shutdown()

    async def test_room_change_stops_media_before_new_room_is_emitted(self):
        broker = Broker()
        broker.room_id = "old"
        broker.media.room = object()
        broker.media.leave = AsyncMock()
        await broker.observe({"currentRoom": {"id": "new"}})
        broker.media.leave.assert_awaited_once()
        self.assertEqual(broker.room_id, "new")


if __name__ == "__main__": unittest.main()

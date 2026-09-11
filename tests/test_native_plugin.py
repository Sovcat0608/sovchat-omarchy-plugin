"""Portable contract/security/lifecycle tests. No production accounts or devices."""

import asyncio
import base64
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
os.environ["SOVCHAT_NATIVE_DISABLE_KEYRING"] = "1"  # Tests never read or clear the user's keyring.
sys.path.insert(0, str(ROOT / "native-plugin" / "runtime"))
from api import Api, ApiError, API_ORIGIN, LIVEKIT_ORIGIN, NoRedirect, Transport, MAX_RESPONSE, avatar_image
from broker import Broker, MAX_REQUEST
from media import Media
from updates import Updates, LATEST_URL, version


class FakeTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, url, method="GET", headers=None, body=None):
        self.calls.append((url, method, headers, body))
        if not self.responses:
            raise AssertionError("Unexpected API request")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def authenticated(transport):
    api = Api(transport)
    api.token = "private-session-token"
    api.session = {"userId": "one", "nickname": "Tester"}
    return api


class ApiTests(unittest.TestCase):
    def test_avatars_only_allow_bundled_names_or_bounded_rasters(self):
        for number in range(1, 16):
            name = f"avatar-{number}.png"
            self.assertEqual(avatar_image("/avatars/" + name), name)
        png = "data:image/png;base64," + base64.b64encode((ROOT / "native-plugin/assets/avatar-1.png").read_bytes()).decode()
        self.assertEqual(avatar_image(png), png)
        for value in (None, 42, {}, "https://sovchat.com/avatar.png", "file:///etc/passwd",
                      "/avatars/../secret.png", "/avatars/avatar-0.png", "/avatars/avatar-16.png",
                      "data:image/svg+xml;base64,PHN2Zz4=", "data:image/png;base64,AAAA",
                      "data:image/png;base64,=", "data:image/png;base64," + "A" * 350000):
            self.assertEqual(avatar_image(value), "")

    def test_avatar_projection_does_not_forward_unknown_fields_or_fetch_urls(self):
        transport = FakeTransport((200, {"session": {"userId": "one", "avatarId": "avatar-2"}}),
                                  (200, {"avatars": {"one": "/avatars/avatar-2.png", "two": "https://other.test/a.png"},
                                         "messages": [{"userId": "one"}, {"userId": "two"}]}))
        api = authenticated(transport)
        self.assertEqual(api.validate_session()["session"]["avatarImage"], "avatar-2.png")
        result = api.messages()
        self.assertEqual(result["avatars"], {"one": "avatar-2.png", "two": ""})
        self.assertEqual(len(transport.calls), 2)

    def test_repeated_author_avatar_is_not_duplicated_on_each_message(self):
        png = "data:image/png;base64," + base64.b64encode((ROOT / "native-plugin/assets/avatar-1.png").read_bytes()).decode()
        result = authenticated(FakeTransport((200, {"avatars": {"one": png},
                                                   "messages": [{"userId": "one"}] * 100}))).messages()
        self.assertEqual(len(result["messages"]), 100)
        self.assertEqual(result["avatars"], {"one": png})
        self.assertEqual(json.dumps(result).count(png), 1)

    def test_login_reuses_shared_variant_and_never_exposes_token(self):
        transport = FakeTransport((200, {"sessionToken": "secret"}), (200, {
            "session": {"userId": "one", "nickname": "Tester", "sessionToken": "nested-secret"},
            "sessionToken": "rotated-secret",
        }))
        api = Api(transport)
        result = api.login({"email": " TEST@EXAMPLE.COM ", "password": "password"})
        self.assertEqual(api.token, "rotated-secret")
        self.assertNotIn("secret", json.dumps(result))
        url, method, headers, body = transport.calls[0]
        self.assertEqual(url, API_ORIGIN + "/api/auth/login")
        self.assertEqual(method, "POST")
        self.assertNotIn("Authorization", headers)
        self.assertEqual(headers["X-SovChat-App-Variant"], "omarchy")
        self.assertEqual(headers["X-SovChat-Client"], "desktop")
        self.assertFalse(json.loads(body)["disconnectOtherSessions"])
        self.assertFalse(json.loads(body)["rememberMe"])
        self.assertEqual(transport.calls[1][2]["Authorization"], "Bearer secret")

    def test_conflict_does_not_retry_or_disconnect_another_device(self):
        transport = FakeTransport((409, {"code": "SESSION_CONFLICT"}))
        api = Api(transport)
        with self.assertRaisesRegex(ApiError, "SESSION_CONFLICT"):
            api.login({"email": "a@b.test", "password": "password"})
        self.assertEqual(len(transport.calls), 1)
        self.assertIsNone(api.token)

    def test_signup_capacity_stays_on_server_no_beta_code(self):
        transport = FakeTransport((403, {"error": "server details and secret"}))
        api = Api(transport)
        with self.assertRaisesRegex(ApiError, "SERVER_REJECTED"):
            api.signup({"email": "a@b.test", "nickname": "Tester", "password": "password"})
        payload = json.loads(transport.calls[0][3])
        self.assertEqual(set(payload), {"email", "nickname", "password"})
        self.assertIsNone(api.token)

    def test_signup_success_does_not_store_premature_session(self):
        api = Api(FakeTransport((200, {"sessionToken": "unverified"})))
        result = api.signup({"email": "a@b.test", "nickname": "Tester", "password": "password"})
        self.assertIn("verification", result["notice"])
        self.assertIsNone(api.token)

    def test_failed_session_validation_discards_login(self):
        api = Api(FakeTransport((200, {"sessionToken": "secret"}), (403, {})))
        with self.assertRaises(ApiError):
            api.login({"email": "a@b.test", "password": "password"})
        self.assertIsNone(api.token)
        self.assertIsNone(api.session)

    def test_expired_session_clears_state(self):
        api = authenticated(FakeTransport((401, {})))
        with self.assertRaisesRegex(ApiError, "AUTH_REQUIRED"):
            api.messages()
        self.assertIsNone(api.token)

    def test_permission_failure_does_not_clear_valid_account(self):
        api = authenticated(FakeTransport((403, {})))
        with self.assertRaises(ApiError):
            api.rooms()
        self.assertIsNotNone(api.token)

    def test_logout_is_local_even_if_network_fails(self):
        api = authenticated(FakeTransport(ApiError("NETWORK")))
        with self.assertRaises(ApiError):
            api.logout()
        self.assertIsNone(api.token)
        self.assertIsNone(api.session)

    def test_session_rotation_rejects_header_injection(self):
        api = authenticated(FakeTransport((200, {"session": {"userId": "one"}, "sessionToken": "a\r\nb"})))
        with self.assertRaises(ApiError):
            api.validate_session()
        self.assertIsNone(api.token)

    def test_malformed_session_revokes_stale_local_state(self):
        api = authenticated(FakeTransport((200, {"session": None})))
        with self.assertRaises(ApiError):
            api.validate_session()
        self.assertIsNone(api.token)
        self.assertIsNone(api.session)

    def test_api_paths_are_fixed_and_not_caller_supplied(self):
        transport = FakeTransport()
        api = authenticated(transport)
        for path in ("https://evil.test", "//evil.test", "/api/admin", "/api/messages?sessionToken=secret"):
            with self.assertRaises(ApiError):
                api.request(path)
        self.assertEqual(transport.calls, [])

    def test_send_uses_existing_multipart_contract_and_never_replays(self):
        transport = FakeTransport((200, {"message": {"id": "sent"}}))
        result = authenticated(transport).send({"body": "hello\r\nworld"})
        self.assertEqual(result, {"sent": True})
        url, method, headers, body = transport.calls[0]
        self.assertTrue(headers["Content-Type"].startswith("multipart/form-data; boundary="))
        self.assertIn(b'name="payload"', body)
        self.assertIn(b'"whisperRecipientIds": []', body)
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(method, "POST")

    def test_messages_keep_private_context_without_secrets_or_urls(self):
        message = {"id": "one", "nickname": "<b>Bob</b>", "body": "hi", "sessionToken": "secret",
                   "whisper": {"recipientIds": ["other"]}, "attachments": [{"url": "secret-url"}]}
        result = authenticated(FakeTransport((200, {"messages": [message]}))).messages()
        self.assertTrue(result["messages"][0]["private"])
        self.assertTrue(result["messages"][0]["hasAttachments"])
        self.assertNotIn("secret", json.dumps(result))
        self.assertEqual(result["messages"][0]["nickname"], "<b>Bob</b>")

    def test_room_projection_excludes_join_code_and_unknown_fields(self):
        room = {"id": "a", "name": "Test", "code": "private-code", "sessionToken": "secret"}
        result = authenticated(FakeTransport((200, {"currentRoom": room, "joinedRooms": [room]}))).rooms()
        self.assertEqual(result["currentRoom"], {"id": "a", "name": "Test"})

    def test_input_bounds_before_network(self):
        api = authenticated(FakeTransport())
        for body in ("", " " * 3, "x" * 4001, 42, None):
            with self.assertRaises(ApiError):
                api.send({"body": body})

    def test_livekit_only_shared_endpoint(self):
        for endpoint in ("wss://evil.test", "ws://livekit.sovchat.com", "wss://livekit.sovchat.com@evil.test"):
            api = authenticated(FakeTransport((200, {"session": {"userId": "one"}}),
                                             (200, {"token": "secret", "serverUrl": endpoint})))
            with self.assertRaises(ApiError):
                api.voice_credentials()

    def test_livekit_credentials_never_require_server_keys(self):
        transport = FakeTransport((200, {"session": {"userId": "one"}}), (200, {"token": "room-token"}))
        self.assertEqual(authenticated(transport).voice_credentials(), (LIVEKIT_ORIGIN, "room-token"))
        self.assertEqual(transport.calls[1][0:2], (API_ORIGIN + "/api/livekit/token", "POST"))

    def test_transport_refuses_redirects(self):
        with self.assertRaises(ApiError):
            NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.test")

    def test_transport_bounds_json_and_rejects_other_shapes(self):
        class Response(io.BytesIO):
            code = 200
        for payload in (b"x" * (MAX_RESPONSE + 1), b"not json", b"[]", b"null"):
            transport = Transport()
            transport.opener = SimpleNamespace(open=lambda *args, **kwargs: Response(payload))
            with self.assertRaises(ApiError):
                transport.request(API_ORIGIN)


class UpdateTests(unittest.TestCase):
    def release(self, tag="v0.2.1", **extra):
        return (200, {"tag_name": tag, "draft": False, "prerelease": False, **extra})

    def test_versions_numeric_not_lexical(self):
        self.assertGreater(version("0.10.0"), version("0.9.0"))
        for bad in ("1.2", "1.2.3; sh", "01.2.3", "1.2.3-beta", None, "1.2.999999999"):
            with self.assertRaises(ApiError):
                version(bad)

    def test_stable_release_supersedes_preview(self):
        updates = Updates("0.2.0-dev.1", FakeTransport(self.release("v0.2.0")), notify=lambda _: True)
        self.assertTrue(updates.check()["available"])

    def test_update_ping_once_per_version_and_no_account_token(self):
        calls = []
        transport = FakeTransport(self.release(), self.release())
        def notify(tag):
            calls.append(tag)
            return True
        updates = Updates("0.2.0-dev.1", transport, notify=notify)
        self.assertTrue(updates.check()["available"])
        updates.check()
        self.assertEqual(calls, ["0.2.1"])
        self.assertEqual(transport.calls[0][0], LATEST_URL)
        self.assertNotIn("Authorization", transport.calls[0][2])

    def test_unavailable_notification_retains_visible_update(self):
        updates = Updates("0.2.0", FakeTransport(self.release()), notify=lambda _: False)
        self.assertTrue(updates.check()["available"])
        self.assertFalse(updates.notified)

    def test_no_downgrade_or_draft_notifications(self):
        for release in (self.release("v0.1.6"), self.release(draft=True), self.release(prerelease=True)):
            updates = Updates("0.2.0-dev.1", FakeTransport(release), notify=lambda _: self.fail("notified"))
            if release[1]["tag_name"] == "v0.1.6":
                self.assertFalse(updates.check()["available"])
            else:
                with self.assertRaises(ApiError):
                    updates.check()

    def test_notification_never_uses_shell_or_remote_text(self):
        with patch("updates.shutil.which", return_value="/usr/bin/notify-send"), patch("updates.subprocess.run") as run:
            Updates.desktop_notice("0.2.1")
        args, kwargs = run.call_args
        self.assertIsInstance(args[0], list)
        self.assertNotIn("shell", kwargs)
        self.assertIn("--", args[0])
        self.assertEqual(kwargs["timeout"], 5)


class MediaTests(unittest.IsolatedAsyncioTestCase):
    def fake_rtc(self, fail=None):
        calls = []
        class Audio:
            def __init__(self): calls.append("audio-open")
            def create_audio_source(self):
                calls.append("source-open")
                return SimpleNamespace(close=lambda: calls.append("source-close"))
            def close(self): calls.append("audio-close")
        class Track:
            def mute(self): calls.append("mute")
            def unmute(self): calls.append("unmute")
        async def publish(*args):
            calls.append("publish")
            if fail == "publish": raise RuntimeError("token-secret")
        class Room:
            def __init__(self):
                self.remote_participants = {}
                self.local_participant = SimpleNamespace(publish_track=publish)
                self.handlers = {}
            def on(self, name):
                def register(callback):
                    self.handlers[name] = callback
                    return callback
                return register
            async def connect(self, *args):
                calls.append("connect")
                if fail == "connect": raise RuntimeError("token-secret")
            async def disconnect(self): calls.append("disconnect")
        rtc = SimpleNamespace(PlatformAudio=Audio, Room=Room, RoomOptions=lambda **kw: kw,
                              TrackKind=SimpleNamespace(KIND_AUDIO=1),
                              TrackSource=SimpleNamespace(SOURCE_MICROPHONE=1),
                              TrackPublishOptions=lambda **kw: kw,
                              LocalAudioTrack=SimpleNamespace(create_audio_track=lambda *args: Track()))
        return rtc, calls

    async def test_disabled_by_default_no_capture(self):
        media = Media()
        self.assertFalse(media.available())
        with self.assertRaisesRegex(ApiError, "MEDIA_UNAVAILABLE"):
            await media.join("url", "token")

    async def test_join_is_muted_and_leave_releases_every_handle(self):
        rtc, calls = self.fake_rtc()
        media = Media(enabled=True, rtc=rtc)
        result = await media.join(LIVEKIT_ORIGIN, "token")
        self.assertTrue(result["connected"])
        self.assertTrue(result["muted"])
        self.assertLess(calls.index("mute"), calls.index("publish"))
        media.set_muted(False)
        await media.leave()
        await media.leave()
        self.assertEqual(calls.count("audio-close"), 1)
        self.assertEqual(calls.count("source-close"), 1)
        self.assertIsNone(media.room)
        self.assertFalse(media.state()["connected"])

    async def test_failed_connect_and_publish_leave_clean_retry(self):
        for fail in ("connect", "publish"):
            rtc, calls = self.fake_rtc(fail)
            media = Media(enabled=True, rtc=rtc)
            with self.assertRaises(RuntimeError):
                await media.join(LIVEKIT_ORIGIN, "token")
            self.assertIsNone(media.room)
            self.assertIsNone(media.source)
            self.assertEqual(calls.count("audio-close"), 1)
            self.assertIn("disconnect", calls)
            rtc2, _ = self.fake_rtc()
            media.rtc = rtc2
            self.assertTrue((await media.join(LIVEKIT_ORIGIN, "token"))["connected"])
            await media.leave()

    async def test_disconnect_releases_capture_and_room_switch_guard(self):
        rtc, calls = self.fake_rtc()
        media = Media(enabled=True, rtc=rtc)
        await media.join(LIVEKIT_ORIGIN, "token")
        room = media.room
        room.handlers["disconnected"]()
        self.assertIsNone(media.room)
        self.assertFalse(media.state()["connected"])
        self.assertEqual(calls.count("audio-close"), 1)
        room.handlers["disconnected"]()
        self.assertEqual(calls.count("audio-close"), 1)

    async def test_late_old_room_disconnect_does_not_stop_new_call(self):
        rtc, calls = self.fake_rtc()
        media = Media(enabled=True, rtc=rtc)
        await media.join(LIVEKIT_ORIGIN, "first-token")
        old_room = media.room
        await media.leave()
        await media.join(LIVEKIT_ORIGIN, "second-token")
        new_room = media.room
        new_audio = media.audio
        old_room.handlers["disconnected"]()
        self.assertIs(media.room, new_room)
        self.assertIs(media.audio, new_audio)
        self.assertTrue(media.state()["connected"])
        self.assertEqual(calls.count("audio-close"), 1)
        await media.leave()
        self.assertEqual(calls.count("audio-close"), 2)

    async def test_cancelled_join_releases_resources(self):
        rtc, calls = self.fake_rtc()
        ready = asyncio.Event()
        async def connect(*args):
            ready.set()
            await asyncio.Future()
        original = rtc.Room
        def room():
            result = original()
            result.connect = connect
            return result
        rtc.Room = room
        media = Media(enabled=True, rtc=rtc)
        task = asyncio.create_task(media.join(LIVEKIT_ORIGIN, "secret"))
        await ready.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertIn("audio-close", calls)
        self.assertIsNone(media.room)

    async def test_both_handles_and_room_cleaned_if_source_close_raises(self):
        rtc, calls = self.fake_rtc()
        media = Media(enabled=True, rtc=rtc)
        await media.join(LIVEKIT_ORIGIN, "token")
        def fail(): raise RuntimeError("source failure")
        media.source.close = fail
        with self.assertRaises(RuntimeError): await media.leave()
        self.assertIn("audio-close", calls)
        self.assertIn("disconnect", calls)
        self.assertIsNone(media.source)
        self.assertIsNone(media.audio)
        self.assertIsNone(media.room)

    async def test_video_stop_failure_cannot_skip_microphone_cleanup(self):
        rtc, calls = self.fake_rtc()
        media = Media(enabled=True, rtc=rtc)
        await media.join(LIVEKIT_ORIGIN, "token")
        class BrokenVideo:
            def stop_local(self): raise RuntimeError("video failure")
            async def close(self): calls.append("video-close")
        media.video = BrokenVideo()
        with self.assertRaises(RuntimeError): await media.shutdown()
        self.assertIn("audio-close", calls)
        self.assertIn("video-close", calls)
        self.assertIn("disconnect", calls)
        self.assertIsNone(media.source)
        self.assertIsNone(media.audio)


class BrokerTests(unittest.IsolatedAsyncioTestCase):
    async def test_errors_do_not_serialize_server_details_or_credentials(self):
        api = Api(FakeTransport((500, {"error": "password secret", "code": "token-secret"})))
        broker = Broker(api=api)
        response = await broker.reply({"id": 1, "op": "login", "data": {"email": "a@b", "password": "password"}})
        self.assertFalse(response["ok"])
        self.assertNotIn("secret", json.dumps(response))
        self.assertNotIn("password", json.dumps(response))

    async def test_bad_input_and_unknown_commands_are_bounded(self):
        broker = Broker()
        for request in (None, [], {"op": "login"}, {"id": True}, {"id": "secret"},
                        {"id": 1, "op": "shell", "data": {}}, {"id": 1, "data": []}):
            result = await broker.reply(request)
            self.assertFalse(result["ok"])

    async def test_room_switch_cannot_leave_old_room_messages(self):
        api = authenticated(FakeTransport((200, {"currentRoom": {"id": "new"}, "joinedRooms": []})))
        result = await Broker(api=api).dispatch({"op": "switch", "data": {"roomId": "new"}})
        self.assertEqual(result["messages"], [])

    async def test_room_switch_refuses_while_voice_connected(self):
        media = Media()
        media.room = object()
        with self.assertRaisesRegex(ApiError, "MEDIA_BUSY"):
            await Broker(media=media).dispatch({"op": "switch", "data": {"roomId": "new"}})


class ProcessTests(unittest.TestCase):
    def test_service_disables_bytecode_in_watched_plugin_directory(self):
        service = (ROOT / "native-plugin/Service.qml").read_text()
        self.assertIn('"-B", "-u"', service)

    def test_actual_pipe_protocol_and_clean_eof(self):
        result = subprocess.run([sys.executable, "-B", "-u", str(ROOT / "native-plugin/runtime/broker.py")],
                                input='{"id":1,"op":"hello"}\n{bad json}\n', text=True,
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertTrue(lines[0]["ok"])
        self.assertFalse(lines[0]["result"]["media"]["available"])
        self.assertFalse(lines[1]["ok"])
        self.assertEqual(result.stderr, "")

    def test_oversized_request_terminates_without_echo(self):
        result = subprocess.run([sys.executable, "-B", str(ROOT / "native-plugin/runtime/broker.py")],
                                input="secret" * MAX_REQUEST, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()

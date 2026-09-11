"""One helper per Omarchy plugin service, controlled through inherited pipes.

Passwords enter only on stdin. Session/LiveKit tokens stay in this process.
No permanent HTTP listener, plaintext token file or QML token property.
Opt-in Google sign-in temporarily binds its nonce-checked loopback callback.
"""

import asyncio
import copy
import json
import logging
import os
from pathlib import Path
import signal
import sys
import threading
import time

from api import Api, ApiError, ERROR_MESSAGES, field, Transport
from media import Media
from updates import Updates
from commands import CommandRunner
from features import NativeApi
from auth_native import Vault, google_sign_in
from events import Events
from preferences import Preferences, validated
from session_lifecycle import revoke
from app_audio import applications

MAX_REQUEST = 131072


class Broker:
    def __init__(self, api=None, media=None, updates=None):
        self.api = api or NativeApi()
        self.media = media or Media(enabled=os.environ.get("SOVCHAT_NATIVE_VOICE_PREVIEW") == "1")
        installed = json.loads((Path(__file__).resolve().parent.parent / "manifest.json").read_text())["version"]
        self.updates = updates or Updates(installed)
        self.generation = 0
        self.emit = lambda event: None
        self.vault = Vault()
        self.remember = False
        self.api_lock = asyncio.Lock()
        self.room_id = None
        self.room_transition = False
        self.changed = asyncio.Event()
        self.stream_deadline = None
        self.voice_seconds = self.share_seconds = 0.0
        self.usage_lock = asyncio.Lock()
        self.logout_pending = None
        self.preferences = Preferences()
        if media is None:
            self.media.options = self.preferences.load()

    async def api_work(self, method, *args, **kwargs):
        async with self.api_lock:
            return await self._api_work(method, *args, **kwargs)

    async def _api_work(self, method, *args, **kwargs):
        # urllib workers cannot be cancelled once executing. Isolate mutable
        # credentials so a late session rotation/401 cannot resurrect a logout
        # or clear a newer login. Only the current generation can commit state.
        generation = self.generation
        api = copy.copy(self.api)
        original_token = api.token
        if isinstance(getattr(api, "transport", None), Transport):
            api.transport = copy.copy(api.transport)
            api.transport.deadline = time.monotonic() + 35
        abandoned = threading.Event()
        def discard_login():
            if method == "login" and isinstance(api, NativeApi) and api.token:
                try: revoke(api)
                except Exception: pass
        def work():
            try: return getattr(api, method)(*args, **kwargs)
            finally:
                # A timed-out/cancelled login can still create a server session.
                # Revoke that exact late result rather than abandoning its token.
                if abandoned.is_set(): discard_login()
        try:
            result = await asyncio.to_thread(work)
            if generation != self.generation:
                abandoned.set()
                await asyncio.to_thread(discard_login)
                raise ApiError("CANCELLED")
            return result
        except asyncio.CancelledError:
            abandoned.set()
            # Cover a worker that finished just before cancellation was delivered.
            if method == "login" and api.token:
                await asyncio.to_thread(discard_login)
            raise
        finally:
            if generation == self.generation and not asyncio.current_task().cancelling():
                self.api.token, self.api.session = api.token, api.session
                if self.remember and self.api.token and self.api.token != original_token:
                    await self.vault.save(self.api.token)

    async def dispatch(self, command):
        if not isinstance(command, dict):
            raise ApiError("BAD_INPUT")
        op = command.get("op")
        data = command.get("data", {})
        if not isinstance(data, dict):
            raise ApiError("BAD_INPUT")
        if self.room_transition and op not in {"logout", "voice-mute", "voice-deafen", "voice-leave", "voice-idle", "screen-stop", "screen-unwatch"}:
            raise ApiError("BUSY")
        if op == "hello":
            token = await self.vault.load()
            if token and len(token) <= 8192 and not any(c.isspace() for c in token):
                self.api.token = token
                self.remember = True
                try:
                    result = await self.api_work("validate_session")
                    result.update(media=self.media.state(), secureStorage=bool(self.vault.program))
                    return result
                except ApiError:
                    self.api.clear()
                    self.remember = False
            return {"session": None, "media": self.media.state(), "secureStorage": bool(self.vault.program)}
        if op == "updates":
            return {"update": await asyncio.to_thread(self.updates.check)}
        if op == "logout":
            revoker = copy.copy(self.api) if self.api.token else self.logout_pending
            self.generation += 1
            self.remember = False
            self.api.clear()
            self.room_transition = False
            self.room_id = None
            self.logout_pending = revoker
            self.emit({"event": "session", "session": None})
            # Keyring/media failures must never prevent the server request.
            results = await asyncio.gather(self.media.leave(), self.vault.clear(),
                asyncio.to_thread(revoke, revoker) if revoker and isinstance(revoker, NativeApi)
                else asyncio.to_thread(revoker.logout) if revoker else asyncio.sleep(0),
                return_exceptions=True)
            if isinstance(results[2], BaseException):
                raise ApiError("LOGOUT_PENDING")
            self.logout_pending = None
            if isinstance(results[1], BaseException): raise ApiError("KEYRING_UNAVAILABLE")
            return {"session": None, "notice": "Signed out. Server session revoked."}
        if op in {"login", "signup", "google-login"}:
            if self.logout_pending is not None: raise ApiError("LOGOUT_PENDING")
            self.generation += 1
            self.remember = False
            await self.media.leave()
            if op == "signup": return await self.api_work(op, data)
            remember = data.get("rememberMe") is True
            if remember and not self.vault.program: raise ApiError("KEYRING_UNAVAILABLE")
            await self.vault.clear()
            if op == "google-login":
                self.api.clear()
                self.api.token = await google_sign_in(remember)
                result = await self.api_work("validate_session")
            else:
                result = await self.api_work(op, data)
            if remember:
                try: await self.vault.save(self.api.token)
                except BaseException:
                    failed_login = copy.copy(self.api)
                    self.api.clear()
                    try: await asyncio.to_thread(revoke, failed_login)
                    except Exception: self.logout_pending = failed_login
                    raise
            self.remember = remember
            return result
        if op == "resend":
            await self.api_work("request", "/api/auth/resend-verification", "POST",
                                   {"email": field(data, "email", 254).strip()}, authenticated=False)
            return {"notice": "Verification requested. Check your inbox."}
        if op == "refresh":
            if isinstance(self.api, NativeApi):
                result = await self.api_work("snapshot")
                await self.observe(result)
                result["media"] = self.media.state()
                return result
            result = await self.api_work("validate_session")
            result.update(await self.api_work("rooms"))
            result.update(await self.api_work("messages") if result["currentRoom"] else {"messages": [], "avatars": {}})
            result["media"] = self.media.state()
            return result
        if op in {"switch", "join-room", "create-room"}:
            if self.media.room is not None:
                raise ApiError("MEDIA_BUSY")
            await self.flush_usage()
            self.generation += 1
            if op == "switch":
                payload = {"action": "switch", "roomId": field(data, "roomId", 191)}
            elif op == "join-room":
                payload = {"action": "join", "code": field(data, "code", 100)}
            else:
                payload = {"action": "create", "code": field(data, "code", 100),
                           "name": field(data, "name", 100)}
            result = await self.api_work("rooms", payload)
            result["messages"] = []  # Never leave the previous room's messages visible.
            result["avatars"] = {}
            return result
        if op == "send":
            return await self.api_work("send", data)
        if op in {"reaction", "delete-message", "save-attachment", "room-action"}:
            if op == "room-action" and self.media.room is not None:
                raise ApiError("MEDIA_BUSY")
            if op == "room-action":
                await self.flush_usage()
                self.generation += 1
            return await self.api_work(op.replace("-", "_"), data)
        if op == "profile":
            return await self.api_work("profile", data or None)
        if op == "usage":
            return await self.api_work("usage", data.get("month"))
        if op in {"presence", "voice-presence", "stream-usage"}:
            return await self.api_work(op.replace("-", "_"))
        if op == "voice-join":
            if not self.media.available():
                raise ApiError("MEDIA_UNAVAILABLE")
            url, token = await self.api_work("voice_credentials")
            try:
                return {"media": await self.media.join(url, token)}
            except ApiError:
                raise
            except Exception:
                raise ApiError("MEDIA_FAILED") from None
        if op == "voice-leave":
            state = await self.media.leave()
            await self.flush_usage()
            return {"media": state}
        if op == "voice-idle":
            if type(data.get("idle")) is not bool: raise ApiError("BAD_INPUT")
            self.media.afk = data["idle"]
            self.media.metadata()
            return {"media": self.media.state()}
        if op == "voice-mute":
            return {"media": self.media.set_muted(data.get("muted"))}
        if op == "voice-deafen":
            return {"media": await self.media.set_deafened(data.get("deafened"))}
        if op == "voice-volume":
            return {"media": self.media.set_volume(data)}
        if op == "audio-devices":
            return {"devices": self.media.devices()}
        if op == "audio-applications":
            return {"audioApplications": [{ "id": app["id"], "name": app["name"] } for app in await applications()]}
        if op == "screen-volume":
            return {"media": self.media.set_volume({"participantId": "$stream", "volume": data.get("volume")})}
        if op == "audio-settings":
            if self.media.room is not None: raise ApiError("MEDIA_BUSY")
            values = validated(dict(self.media.options, **data))
            await asyncio.to_thread(self.preferences.save, values)
            return {"media": self.media.configure(data)}
        if op == "output-volume":
            values = validated(dict(self.media.options, outputVolume=data.get("volume")))
            await asyncio.to_thread(self.preferences.save, values)
            self.media.options = values
            if self.media.playback is not None: self.media.playback.set_master(values["outputVolume"])
            return {"media": self.media.state()}
        if op == "screen-start":
            if self.media.video is None or not self.media.state()["screenSharingAvailable"]:
                raise ApiError("CAPTURE_UNAVAILABLE")
            await self.flush_usage()
            usage = await self.api_work("stream_usage")
            if usage["streamUsage"]["remainingSeconds"] == 0: raise ApiError("STREAM_LIMIT")
            video = self.media.video
            async def authorize():
                nonlocal usage
                # Recheck after the user spends time in the source picker, but
                # before publishing any frames. Cancellation still closes it.
                usage = await self.api_work("stream_usage")
                remaining = usage["streamUsage"]["remainingSeconds"]
                if remaining == 0: raise ApiError("STREAM_LIMIT")
                self.stream_deadline = time.monotonic() + remaining if remaining is not None else None
            try:
                await video.start(field(data, "source", 10), authorize=authorize, quality=data.get("quality", "720p"),
                                  audio_node=field(data, "audioNode", 20, required=False), fps=data.get("fps", 30))
            except BaseException:
                # A cancelled SDK publication may complete remotely after its
                # waiter exits. Muted/closed local tracks plus room disconnect
                # prevent an orphan publication. Picker cancellation is exempt.
                if video.publication_uncertain and self.media.video is video: await self.media.leave()
                raise
            return {"media": self.media.state(), **usage}
        if op == "screen-stop":
            if self.media.video is not None: await self.media.video.stop()
            self.stream_deadline = None
            await self.flush_usage()
            return {"media": self.media.state()}
        if op == "screen-watch":
            if self.media.video is None: raise ApiError("MEDIA_UNAVAILABLE")
            await self.media.video.watch(field(data, "id", 191, required=False))
            return {"media": self.media.state()}
        if op == "screen-unwatch":
            if self.media.video is not None: await self.media.video.unwatch()
            return {"media": self.media.state()}
        raise ApiError("UNSUPPORTED")

    async def observe(self, result):
        if "currentRoom" in result:
            current = result["currentRoom"]
            room_id = current.get("id") if current else None
            generation = self.generation
            if room_id != self.room_id:
                self.generation += 1
                generation = self.generation
                self.room_transition = True
                self.emit({"event": "snapshot", "result": {"roomTransition": True, "messages": [], "avatars": {}, "presence": [], "participants": []}})
            if room_id != self.room_id and "messages" not in result:
                result.update(messages=[], avatars={}, presence=[], participants=[])
            if room_id != self.room_id and self.media.room is not None:
                try:
                    await self.media.leave()
                except Exception:
                    if generation == self.generation:
                        self.room_transition = False
                        self.emit({"event": "snapshot", "result": {"roomTransition": False}})
                    raise
            if generation != self.generation: raise ApiError("CANCELLED")
            if room_id != self.room_id:
                # The shared API bills the server's current room, not a supplied
                # room ID. Never transfer an old room's counters to a new one.
                self.voice_seconds = self.share_seconds = 0
                self.stream_deadline = None
            self.room_id = room_id
            self.room_transition = False
            result["roomTransition"] = False

    async def flush_usage(self):
        async with self.usage_lock:
            if not isinstance(self.api, NativeApi) or not self.api.session: return
            video = self.media.video
            publication = video.publication if video is not None else None
            generation = self.generation
            voice, share = min(60, int(self.voice_seconds)), min(60, int(self.share_seconds))
            self.voice_seconds -= voice; self.share_seconds -= share
            if not voice and not share: return
            try:
                if share:
                    usage = await self.api_work("stream_usage", share)
                    self.emit({"event": "snapshot", "result": usage})
                    remaining = usage["streamUsage"]["remainingSeconds"]
                    if generation == self.generation and video is self.media.video and video is not None and publication is video.publication:
                        self.stream_deadline = time.monotonic() + max(0, remaining - self.share_seconds) if remaining is not None else None
                stream_bytes = await video.usage_bytes() if video is not None else 0
                await self.api_work("request", "/api/livekit-usage", "PATCH", {"webRtcSeconds": voice, "streamSeconds": share, "streamBytes": stream_bytes})
            except ApiError:
                # Ambiguous PATCHes are never replayed. Fail closed for capture.
                if video is not None and video is self.media.video and video.publication is not None:
                    video.stop_share_local()
                    self.media.schedule_cleanup(video.stop())
                    self.emit({"event": "notice", "error": "Sharing stopped because usage could not be confirmed. Check your connection before retrying."})

    async def maintenance(self):
        watcher = None
        watcher_key = None
        last_refresh = 0.0
        try:
            while True:
                await asyncio.sleep(0.25)
                now = time.monotonic()
                video = self.media.video
                sharing = video is not None and video.publication is not None
                key = (self.generation, self.room_id, self.api.token)
                if key != watcher_key:
                    if watcher: watcher.close()
                    watcher = Events(self.api.token, asyncio.get_running_loop(), self.changed) if self.api.token and self.room_id else None
                    watcher_key = key
                if not self.api.session or not isinstance(self.api, NativeApi):
                    self.voice_seconds = self.share_seconds = 0
                    continue
                if self.changed.is_set() or now - last_refresh >= 10:
                    self.changed.clear()
                    last_refresh = now
                    generation = self.generation
                    try:
                        result = await self.api_work("snapshot")
                        if generation == self.generation:
                            await self.observe(result)
                            self.emit({"event": "snapshot", "result": result})
                    except ApiError:
                        if not self.api.session:
                            await self.media.leave()
                            self.emit({"event": "session", "session": None})
                        elif sharing:
                            video.stop_share_local()
                            self.media.schedule_cleanup(video.stop())
                if self.voice_seconds >= 15 or self.share_seconds >= 15 or (not sharing and self.share_seconds >= 1):
                    await self.flush_usage()
        finally:
            if watcher: watcher.close()

    async def media_clock(self):
        # Runs independently of HTTP; a blocked request cannot extend a grant.
        previous = time.monotonic()
        while True:
            await asyncio.sleep(0.1)
            now = time.monotonic()
            elapsed, previous = min(now - previous, 60), now
            if self.media.track is not None: self.voice_seconds += elapsed
            video = self.media.video
            if video is not None and (video.publication is not None or getattr(video, "publication_uncertain", False) is True):
                if getattr(video, "pending", False) is not True: self.share_seconds += elapsed
                if self.stream_deadline is not None and now >= self.stream_deadline:
                    self.stream_deadline = None
                    video.stop_share_local()
                    self.media.schedule_cleanup(self.media.leave() if getattr(video, "publication_uncertain", False) is True else video.stop())
                    self.emit({"event": "notice", "error": ERROR_MESSAGES["STREAM_LIMIT"]})

    async def reply(self, request):
        request_id = request.get("id") if isinstance(request, dict) else None
        if type(request_id) is not int or not 0 <= request_id <= 2147483647:
            request_id = None
        try:
            if request_id is None:
                raise ApiError("BAD_INPUT")
            result = await self.dispatch(request)
            await self.observe(result)
            if result.get("sent") or result.get("changed"): self.changed.set()
            return {"id": request_id, "ok": True, "result": result}
        except Exception as error:
            # Deliberately do not serialize exception strings, HTTP bodies, or SDK logs.
            code = error.code if isinstance(error, ApiError) else "INVALID_RESPONSE"
            if self.api.session is None:
                try: await self.media.leave()
                except Exception: pass  # Cleanup must not hide the retryable auth error.
            return {"id": request_id, "ok": False, "code": code,
                    "error": ERROR_MESSAGES.get(code, ERROR_MESSAGES["SERVER_REJECTED"]),
                    "signedOut": self.api.session is None, "media": self.media.state()}

    async def shutdown(self):
        # A non-remembered session must not become an orphan when Omarchy reloads.
        # Remembered sessions intentionally survive normal helper restarts.
        target = self.logout_pending or (copy.copy(self.api) if not self.remember and self.api.token else None)
        self.api.clear()
        operations = [self.media.shutdown()]
        if target is not None:
            operations.append(asyncio.wait_for(asyncio.to_thread(revoke, target), 8))
        # Neither local media failure nor remote failure can skip the other cleanup.
        # Forced/offline shutdown still cannot guarantee remote revocation.
        await asyncio.gather(*operations, return_exceptions=True)


async def serve():
    logging.disable(logging.CRITICAL)
    broker = Broker()
    loop = asyncio.get_running_loop()
    stopped = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stopped.set)
        except (NotImplementedError, RuntimeError):
            pass
    # A daemon input reader lets EOF/signals stop without waiting forever for
    # asyncio's executor to finish a blocked stdin read.
    import threading
    queue = asyncio.Queue(maxsize=8)

    def reader():
        while True:
            raw = sys.stdin.buffer.readline(MAX_REQUEST + 1)
            future = asyncio.run_coroutine_threadsafe(queue.put(raw), loop)
            try:
                future.result()
            except Exception:
                return
            if not raw or len(raw) > MAX_REQUEST:
                return

    threading.Thread(target=reader, daemon=True).start()
    emit = lambda value: print(json.dumps(value, ensure_ascii=True), flush=True)
    broker.emit = emit
    runner = CommandRunner(broker, emit)
    stop_task = asyncio.create_task(stopped.wait())

    async def media_events():
        previous = None
        while True:
            state = broker.media.state()
            encoded = json.dumps(state, sort_keys=True)
            if previous is not None and encoded != previous:
                emit({"event": "media", "media": state})
            previous = encoded
            await asyncio.sleep(0.2)

    event_task = asyncio.create_task(media_events())
    maintenance_task = asyncio.create_task(broker.maintenance())
    clock_task = asyncio.create_task(broker.media_clock())
    read_task = None
    try:
        while not stopped.is_set():
            read_task = asyncio.create_task(queue.get())
            done, _ = await asyncio.wait({read_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
            if stop_task in done:
                read_task.cancel()
                break
            raw = read_task.result()
            if not raw or len(raw) > MAX_REQUEST:
                break
            try:
                request = json.loads(raw)
            except (ValueError, UnicodeError):
                request = None
            try:
                await runner.submit(request)
            except ValueError:
                break
            # Give already-ready commands a chance to complete before EOF.
            await asyncio.sleep(0)
    finally:
        if read_task:
            read_task.cancel()
        event_task.cancel()
        maintenance_task.cancel()
        clock_task.cancel()
        await asyncio.gather(clock_task, return_exceptions=True)
        await asyncio.gather(maintenance_task, return_exceptions=True)
        await asyncio.gather(event_task, return_exceptions=True)
        await runner.close()
        stop_task.cancel()
        await broker.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(serve())
    except (BrokenPipeError, KeyboardInterrupt):
        pass

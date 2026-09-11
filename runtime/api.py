"""SovChat wire protocol. No backend, listening socket, or persistent credentials."""

import base64
import binascii
import json
import re
import secrets
import urllib.error
import urllib.request
import time

API_ORIGIN = "https://sovchat.com"
LIVEKIT_ORIGIN = "wss://livekit.sovchat.com"
# Existing server middleware calls all non-web bearer clients 'desktop'. This is
# the compatible API family, NOT the native plugin's package version.
API_COMPAT_VERSION = "0.4.9"
MAX_RESPONSE = 2 * 1024 * 1024


class ApiError(Exception):
    def __init__(self, code, status=0):
        super().__init__(code)
        self.code = code
        self.status = status


ERROR_MESSAGES = {
    "LOGOUT_PENDING": "Signed out locally, but server sign-out is not confirmed. Retry sign-out before signing in again.",
    "VOICE_REVOCATION_PENDING": "The room change was saved, but voice permissions are still updating. Refresh before retrying.",
    "STREAM_LIMIT": "This room's daily screen-sharing allowance has been used.",
    "KEYRING_UNAVAILABLE": "Secure storage is unavailable or locked. Unlock your keyring, or sign in without Remember me.",
    "GOOGLE_FAILED": "Google sign-in did not complete. Close the browser sign-in tab and retry, or use email.",
    "CANCELLED": "The action was interrupted. Check its result before retrying.",
    "BUSY": "Another action is still completing.",
    "CAPTURE_FAILED": "Screen sharing stopped. Choose a source again to retry.",
    "CAPTURE_CANCELLED": "Screen selection cancelled. Nothing is being shared.",
    "CAPTURE_UNAVAILABLE": "The screen portal or PipeWire capture dependency is unavailable.",
    "SESSION_CONFLICT": "Another device is signed in. Sign out there, then retry here.",
    "EMAIL_NOT_VERIFIED": "Verify your email before signing in.",
    "AUTH_REQUIRED": "Sign in to SovChat again.",
    "NETWORK": "Cannot reach SovChat. Check your connection and retry.",
    "INVALID_RESPONSE": "SovChat returned an unexpected response.",
    "BAD_INPUT": "Check the entered values and retry.",
    "SERVER_REJECTED": "SovChat rejected this request. Check your details, account capacity, or permissions.",
    "MEDIA_UNAVAILABLE": "Native voice is not available in this development environment.",
    "MEDIA_FAILED": "Voice could not start. Audio resources have been released; you can retry.",
    "MEDIA_BUSY": "Leave voice before changing rooms.",
    "UNSUPPORTED": "This feature has not passed the native migration release gate.",
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ApiError("NETWORK")


class Transport:
    def __init__(self):
        self.opener = urllib.request.build_opener(NoRedirect())
        self.deadline = None

    def request(self, url, method="GET", headers=None, body=None):
        request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
        try:
            timeout = min(15, self.deadline - time.monotonic()) if self.deadline is not None else 15
            if timeout <= 0: raise ApiError("NETWORK")
            try:
                response = self.opener.open(request, timeout=timeout)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                raw = response.read(MAX_RESPONSE + 1)
                if len(raw) > MAX_RESPONSE:
                    raise ApiError("INVALID_RESPONSE")
                try:
                    payload = json.loads(raw) if raw else {}
                except (ValueError, UnicodeError):
                    raise ApiError("INVALID_RESPONSE") from None
                if not isinstance(payload, dict):
                    raise ApiError("INVALID_RESPONSE")
                return response.code, payload
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ApiError("NETWORK") from None


def field(data, name, limit, required=True):
    value = data.get(name, "")
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ApiError("BAD_INPUT")
    return value


def project(value, keys):
    """Do not forward tokens, unknown server fields, or nested metadata to QML."""
    if not isinstance(value, dict):
        raise ApiError("INVALID_RESPONSE")
    return {key: value[key] for key in keys if isinstance(value.get(key), (str, bool, int))}


def avatar_image(value, max_length=350000):
    """Permit only bundled avatars or bounded inline raster data, never URLs/SVG."""
    if not isinstance(value, str) or len(value) > max_length:
        return ""
    match = re.fullmatch(r"/avatars/(avatar-(?:[1-9]|1[0-5])\.png)", value)
    if match:
        return match[1]
    match = re.fullmatch(r"data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)", value)
    if not match:
        return ""
    try:
        raw = base64.b64decode(match[2], validate=True)
    except (ValueError, binascii.Error):
        return ""
    valid = (match[1] == "png" and raw.startswith(b"\x89PNG\r\n\x1a\n")
             or match[1] == "jpeg" and raw.startswith(b"\xff\xd8\xff")
             or match[1] == "webp" and raw.startswith(b"RIFF") and raw[8:12] == b"WEBP")
    return value if valid else ""


class Api:
    def __init__(self, transport=None):
        self.transport = transport or Transport()
        self.token = None
        self.session = None

    def clear(self):
        self.token = None
        self.session = None

    def request(self, path, method="GET", data=None, *, authenticated=True, multipart=False, files=()):
        if authenticated and not self.token:
            raise ApiError("AUTH_REQUIRED")
        # All callers use fixed paths; neither QML nor IPC supplies a URL.
        if path not in {"/api/auth/login", "/api/auth/signup", "/api/auth/logout",
                        "/api/auth/session", "/api/auth/resend-verification", "/api/rooms",
                        "/api/messages", "/api/livekit/token", "/api/profile", "/api/presence",
                        "/api/voice/participants", "/api/messages/reactions", "/api/stream-usage", "/api/livekit-usage"} and not (
                            method == "DELETE" and re.fullmatch(r"/api/rooms\?roomId=[A-Za-z0-9_-]{1,191}", path)) and not (
                            method == "GET" and re.fullmatch(r"/api/livekit-usage\?month=\d{4}-(?:0[1-9]|1[0-2])", path)):
            raise ApiError("BAD_INPUT")
        headers = {
            "Accept": "application/json", "X-SovChat-Client": "desktop",
            "X-SovChat-Version": API_COMPAT_VERSION, "X-SovChat-App-Variant": "omarchy",
            "User-Agent": "SovChat-Omarchy-Native-Preview",
        }
        if authenticated:
            headers["Authorization"] = "Bearer " + self.token
        body = None
        if data is not None:
            encoded = json.dumps(data, ensure_ascii=True).encode("utf-8")
            if multipart:
                boundary = "sovchat-" + secrets.token_hex(24)
                headers["Content-Type"] = "multipart/form-data; boundary=" + boundary
                parts = [("--" + boundary + '\r\nContent-Disposition: form-data; name="payload"'
                         + "\r\nContent-Type: application/json\r\n\r\n").encode() + encoded + b"\r\n"]
                for name, mime, content in files:
                    parts.append(("--" + boundary + '\r\nContent-Disposition: form-data; name="files"; filename="'
                                  + name + '"\r\nContent-Type: ' + mime + "\r\n\r\n").encode() + content + b"\r\n")
                body = b"".join(parts) + ("--" + boundary + "--\r\n").encode()
            else:
                headers["Content-Type"] = "application/json"
                body = encoded
        status, payload = self.transport.request(API_ORIGIN + path, method, headers, body)
        if not 200 <= status < 300:
            if status == 401 and authenticated:
                self.clear()
                raise ApiError("AUTH_REQUIRED", status)
            code = payload.get("code")
            raise ApiError(code if code in {"SESSION_CONFLICT", "EMAIL_NOT_VERIFIED", "VOICE_REVOCATION_PENDING"}
                           else "SERVER_REJECTED", status)
        return payload

    def login(self, data):
        # Never automatically disconnect a session on another device.
        self.clear()
        payload = self.request("/api/auth/login", "POST", {
            "email": field(data, "email", 254).strip().lower(),
            "password": field(data, "password", 72),
            "rememberMe": data.get("rememberMe") is True,
            "disconnectOtherSessions": data.get("disconnectOtherSessions") is True,
        }, authenticated=False)
        token = payload.get("sessionToken")
        if not isinstance(token, str) or not token or len(token) > 8192 or any(c.isspace() for c in token):
            raise ApiError("INVALID_RESPONSE")
        self.token = token
        try:
            return self.validate_session()
        except Exception:
            # The login POST may have created a session even when validation
            # fails. Best-effort cleanup uses only that newly issued token.
            self.token = token
            try: self.request("/api/auth/logout", "POST")
            except Exception: pass
            finally: self.clear()
            raise

    def signup(self, data):
        self.request("/api/auth/signup", "POST", {
            "email": field(data, "email", 254).strip().lower(),
            "password": field(data, "password", 72),
            "nickname": field(data, "nickname", 20).strip(),
        }, authenticated=False)
        return {"notice": "Check your email for verification, then sign in. Account capacity is enforced by SovChat."}

    def validate_session(self):
        try:
            payload = self.request("/api/auth/session")
        except ApiError as error:
            if error.status in (401, 403):
                self.clear()
            raise
        try:
            self.session = project(payload.get("session"), ("userId", "nickname", "email", "expiresAt"))
        except ApiError:
            self.clear()
            raise
        if not self.session.get("userId"):
            self.clear()
            raise ApiError("INVALID_RESPONSE")
        user = payload["session"]
        self.session["avatarImage"] = avatar_image(user.get("avatarDataUrl")) or avatar_image(
            "/avatars/" + str(user.get("avatarId", "")) + ".png")
        # Session endpoint can rotate the bearer token.
        token = payload.get("sessionToken")
        if token is not None:
            if not isinstance(token, str) or not token or len(token) > 8192 or any(c.isspace() for c in token):
                self.clear()
                raise ApiError("INVALID_RESPONSE")
            self.token = token
        return {"session": self.session}

    def logout(self):
        try:
            if self.token:
                self.request("/api/auth/logout", "POST")
        finally:
            self.clear()
        return {"session": None}

    def rooms(self, data=None):
        payload = self.request("/api/rooms", "POST" if data else "GET", data)
        keys = ("id", "name", "isOwned")
        joined = payload.get("joinedRooms", [])
        if not isinstance(joined, list):
            raise ApiError("INVALID_RESPONSE")
        return {
            "currentRoom": project(payload["currentRoom"], keys) if payload.get("currentRoom") else None,
            "joinedRooms": [project(room, keys) for room in joined[:100]],
        }

    def messages(self):
        payload = self.request("/api/messages")
        messages = payload.get("messages")
        if not isinstance(messages, list):
            raise ApiError("INVALID_RESPONSE")
        result = []
        images = {}
        avatars = payload.get("avatars", {})
        if not isinstance(avatars, dict):
            avatars = {}
        for message in messages[-100:]:
            item = project(message, ("id", "userId", "nickname", "body", "createdAt"))
            # Preserve privacy context without exposing recipients or attachment URLs.
            item["private"] = bool(message.get("whisper"))
            item["hasAttachments"] = bool(message.get("attachments"))
            author = item.get("userId")
            if isinstance(author, str) and author not in images:
                images[author] = avatar_image(avatars.get(author))
            result.append(item)
        # One image per author, not one base64 copy per message on every poll.
        return {"messages": result, "avatars": images}

    def send(self, data):
        self.request("/api/messages", "POST", {
            "body": field(data, "body", 4000), "replyToMessageId": None,
            "whisperRecipientIds": [],
        }, multipart=True)
        # Sending succeeded even if a subsequent refresh would fail. Never replay
        # this POST automatically or tell the UI to retry a delivered message.
        return {"sent": True}

    def voice_credentials(self):
        self.validate_session()
        payload = self.request("/api/livekit/token", "POST")
        token = field(payload, "token", 16384)
        server = payload.get("serverUrl") or LIVEKIT_ORIGIN
        if server.rstrip("/") != LIVEKIT_ORIGIN:
            raise ApiError("INVALID_RESPONSE")
        return server, token

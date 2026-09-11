"""Native feature contracts for the shared SovChat service; no web UI runtime."""
import mimetypes
import os
import re
import stat
from urllib.parse import quote, unquote, urlsplit

from api import Api, ApiError, API_ORIGIN, API_COMPAT_VERSION, avatar_image, field, project
from images_native import avatar as resize_avatar


def bounded_list(value, limit=500):
    if not isinstance(value, list): raise ApiError("INVALID_RESPONSE")
    return value[:limit]


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,191}", value):
        raise ApiError("BAD_INPUT")
    return value


def local_path(value):
    if not isinstance(value, str) or len(value) > 4096: raise ApiError("BAD_INPUT")
    url = urlsplit(value)
    if url.scheme != "file" or url.netloc not in ("", "localhost") or url.query or url.fragment:
        raise ApiError("BAD_INPUT")
    path = unquote(url.path)
    if not path.startswith("/") or "\x00" in path: raise ApiError("BAD_INPUT")
    return path


def upload_files(values):
    if not isinstance(values, list) or len(values) > 6: raise ApiError("BAD_INPUT")
    result, total = [], 0
    for value in values:
        path = local_path(value)
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(fd, "rb") as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 8 * 1024 * 1024:
                raise ApiError("BAD_INPUT")
            content = source.read(8 * 1024 * 1024 + 1)
        total += len(content)
        if not content or len(content) > 8 * 1024 * 1024 or total > 20 * 1024 * 1024:
            raise ApiError("BAD_INPUT")
        name = os.path.basename(path)
        name = re.sub(r'[\x00-\x1f\x7f"\\]', "_", name)[:180]
        result.append((name, mimetypes.guess_type(name)[0] or "application/octet-stream", content))
    return result


def message_details(message):
    item = project(message, ("id", "userId", "nickname", "body", "createdAt"))
    whisper = message.get("whisper")
    item["private"] = bool(whisper)
    item["recipientIds"] = [identifier(x) for x in bounded_list(whisper.get("recipientIds", []), 32)] if isinstance(whisper, dict) else []
    item["replyTo"] = project(message["replyTo"], ("id", "nickname", "body")) if message.get("replyTo") else None
    item["attachments"] = [project(x, ("id", "fileName", "mimeType", "sizeBytes", "kind"))
                           for x in bounded_list(message.get("attachments", []), 6)]
    item["hasAttachments"] = bool(item["attachments"])
    item["reactions"] = [project(x, ("emoji", "count", "reactedByMe"))
                         for x in bounded_list(message.get("reactions", []), 100)]
    return item


class NativeApi(Api):
    def snapshot(self):
        result = self.validate_session()
        result.update(self.rooms())
        if result["currentRoom"]:
            room_id = result["currentRoom"]["id"]
            result.update(self.messages())
            result.update(self.presence())
            result.update(self.voice_presence())
            checked = self.rooms()
            if not checked["currentRoom"] or checked["currentRoom"]["id"] != room_id:
                result.update(messages=[], avatars={}, presence=[], participants=[])
            result.update(checked)
        else:
            result.update(messages=[], avatars={}, presence=[], participants=[])
        return result

    def rooms(self, data=None):
        return self.room_snapshot(self.request("/api/rooms", "POST" if data else "GET", data))

    def room_snapshot(self, payload):
        keys = ("id", "name", "isOwned", "fillerMode", "dailyStreamLimitMinutes")
        def room(value):
            if not value: return None
            item = project(value, keys)
            item["avatarImage"] = avatar_image(value.get("avatarDataUrl"), max_length=900000)
            return item
        result = {"currentRoom": room(payload.get("currentRoom")),
                  "ownedRoom": room(payload.get("ownedRoom")),
                  "joinedRooms": [room(x) for x in bounded_list(payload.get("joinedRooms", []), 100)]}
        # Codes appear only in explicitly opened room UI, never chat/notifications.
        result["roomCodes"] = {str(x.get("id")): str(x.get("code", ""))[:12]
                               for x in bounded_list(payload.get("joinedRooms", []), 100) + [payload.get("ownedRoom"), payload.get("currentRoom")] if isinstance(x, dict)}
        for key in ("currentRoomMembers", "ownedRoomMembers", "ownedRoomBans"):
            result[key] = []
            for value in bounded_list(payload.get(key, [])):
                item = project(value, ("userId", "nickname", "isOwner"))
                item["avatarImage"] = avatar_image(value.get("avatarDataUrl")) or avatar_image("/avatars/" + str(value.get("avatarId", "")) + ".png")
                result[key].append(item)
        return result

    def room_action(self, data):
        action = field(data, "action", 40)
        payload = {"action": action}
        if action in ("remove-owned-member", "ban-owned-member", "unban-owned-member"):
            payload["userId"] = identifier(data.get("userId"))
        elif action == "update-owned":
            name = field(data, "name", 32).strip()
            limit = data.get("dailyStreamLimitMinutes", 0)
            if len(name) < 2 or type(limit) is not int or not 0 <= limit <= 1440 or type(data.get("fillerMode")) is not bool:
                raise ApiError("BAD_INPUT")
            payload.update(name=name, fillerMode=data["fillerMode"], dailyStreamLimitMinutes=limit)
            if "avatarFile" in data: payload["avatarDataUrl"] = self.avatar_upload(data["avatarFile"])
        elif action == "remove-room":
            return self.room_snapshot(self.request("/api/rooms?roomId=" + quote(identifier(data.get("roomId")), safe=""), "DELETE"))
        elif action not in ("reset-owned-code", "reset-owned-stream-usage"):
            raise ApiError("BAD_INPUT")
        return self.rooms(payload)

    def messages(self):
        payload = self.request("/api/messages")
        result = [message_details(x) for x in bounded_list(payload.get("messages"), 100)]
        images = payload.get("avatars", {})
        if not isinstance(images, dict): images = {}
        return {"messages": result, "avatars": {x["userId"]: avatar_image(images.get(x["userId"])) for x in result if "userId" in x}}

    def send(self, data):
        body = field(data, "body", 4000, required=False)
        recipients = data.get("whisperRecipientIds", [])
        if not isinstance(recipients, list) or len(recipients) > 32: raise ApiError("BAD_INPUT")
        recipients = list(dict.fromkeys(identifier(x) for x in recipients))
        reply = data.get("replyToMessageId")
        if reply is not None: reply = identifier(reply)
        files = upload_files(data.get("files", []))
        if not body.strip() and not files: raise ApiError("BAD_INPUT")
        self.request("/api/messages", "POST", {"body": body, "replyToMessageId": reply,
                     "whisperRecipientIds": recipients}, multipart=True, files=files)
        return {"sent": True}

    def reaction(self, data):
        self.request("/api/messages/reactions", "POST", {"messageId": identifier(data.get("messageId")), "emoji": field(data, "emoji", 16)})
        return {"changed": True}

    def delete_message(self, data):
        self.request("/api/messages", "DELETE", {"messageId": identifier(data.get("messageId"))})
        return {"changed": True}

    def avatar_upload(self, value):
        if value is None: return None
        files = upload_files([value])
        _, mime, raw = files[0]
        encoded = resize_avatar(raw, mime)
        if not avatar_image(encoded): raise ApiError("BAD_INPUT")
        return encoded

    def profile(self, data=None):
        payload = None
        if data is not None:
            payload = {}
            if "nickname" in data:
                nickname = field(data, "nickname", 20).strip()
                if not re.fullmatch(r"[A-Za-z0-9_ ]{2,20}", nickname): raise ApiError("BAD_INPUT")
                payload["nickname"] = nickname
            if "avatarId" in data:
                value = field(data, "avatarId", 20)
                if not re.fullmatch(r"avatar-(?:[1-9]|1[0-5])", value): raise ApiError("BAD_INPUT")
                payload.update(avatarId=value, avatarDataUrl=None)
            if "avatarFile" in data: payload["avatarDataUrl"] = self.avatar_upload(data["avatarFile"])
            if not payload: raise ApiError("BAD_INPUT")
        value = self.request("/api/profile", "PATCH" if payload else "GET", payload)
        result = project(value, ("nickname", "avatarId"))
        result["avatarImage"] = avatar_image(value.get("avatarDataUrl")) or avatar_image("/avatars/" + str(value.get("avatarId", "")) + ".png")
        return {"profile": result, "changed": payload is not None}

    def presence(self):
        result = []
        for value in bounded_list(self.request("/api/presence").get("profiles", [])):
            item = project(value, ("userId", "nickname"))
            item["avatarImage"] = avatar_image(value.get("avatarSrc"))
            result.append(item)
        return {"presence": result}

    def voice_presence(self):
        result = []
        for value in bounded_list(self.request("/api/voice/participants").get("participants", [])):
            item = project(value, ("participantId", "userId", "displayName", "isStreaming", "isSelfMuted", "isSelfDeafened", "isAfk"))
            item["avatarImage"] = avatar_image(value.get("avatarSrc"))
            result.append(item)
        return {"participants": result}

    def stream_usage(self, seconds=None):
        value = self.request("/api/stream-usage", "PATCH" if seconds is not None else "GET",
                             {"seconds": max(0, min(60, int(seconds)))} if seconds is not None else None)
        result = project(value, ("usedSeconds", "limitSeconds", "dateKey"))
        remaining = value.get("remainingSeconds")
        if remaining is not None and (type(remaining) is not int or remaining < 0): raise ApiError("INVALID_RESPONSE")
        if "remainingSeconds" not in value: raise ApiError("INVALID_RESPONSE")
        result["remainingSeconds"] = remaining
        return {"streamUsage": result}

    def usage(self, month=None):
        if month is not None and (not isinstance(month, str) or not re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])", month)): raise ApiError("BAD_INPUT")
        value = self.request("/api/livekit-usage" + ("?month=" + month if month else ""))
        result = project(value, ("month", "roomName", "hasOwnedRoom", "daysInMonth"))
        for key in ("totalWebRtcMinutes", "totalStreamMinutes", "totalStreamGb", "averageWebRtcMinutesPerDay", "averageStreamMinutesPerDay", "averageStreamGbPerDay"):
            if type(value.get(key)) in (int, float): result[key] = value[key]
        result["days"] = []
        for day in bounded_list(value.get("days", []), 31):
            item = project(day, ("dateKey",))
            for key in ("webRtcMinutes", "streamMinutes", "streamGb"):
                item[key] = day[key] if type(day.get(key)) in (int, float) else 0
            result["days"].append(item)
        return {"usage": result}

    def save_attachment(self, data):
        attachment = identifier(data.get("attachmentId"))
        path = local_path(data.get("destination"))
        if not self.token: raise ApiError("AUTH_REQUIRED")
        import urllib.request
        import urllib.error
        request = urllib.request.Request(API_ORIGIN + "/api/messages/attachments/" + quote(attachment, safe=""),
                                         headers={"Authorization": "Bearer " + self.token, "X-SovChat-App-Variant": "omarchy",
                                                  "X-SovChat-Client": "desktop", "X-SovChat-Version": API_COMPAT_VERSION})
        # The same no-redirect opener prevents leaking bearer credentials.
        try:
            with self.transport.opener.open(request, timeout=15) as response:
                content = response.read(8 * 1024 * 1024 + 1)
                if len(content) > 8 * 1024 * 1024: raise ApiError("INVALID_RESPONSE")
        except urllib.error.HTTPError as error:
            if error.code == 401:
                self.clear()
                raise ApiError("AUTH_REQUIRED", 401) from None
            raise ApiError("SERVER_REJECTED", error.code) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ApiError("NETWORK") from None
        # No overwrite and no automatic execution, including downloaded scripts.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as output: output.write(content)
        return {"notice": "Attachment saved. Existing files are never overwritten."}

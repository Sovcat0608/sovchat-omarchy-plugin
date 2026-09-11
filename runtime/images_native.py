"""Bounded native raster resizing before avatars enter the shared API."""
import base64
import struct
from api import ApiError


def dimensions(raw, mime):
    size = None
    if mime == "image/png" and raw.startswith(b"\x89PNG\r\n\x1a\n") and len(raw) >= 24:
        size = struct.unpack(">II", raw[16:24])
    elif mime == "image/jpeg" and raw.startswith(b"\xff\xd8"):
        pos = 2
        while pos + 4 <= len(raw):
            if raw[pos] != 255: break
            while pos < len(raw) and raw[pos] == 255: pos += 1
            if pos >= len(raw): break
            marker = raw[pos]; pos += 1
            if marker in (0xD9, 0xDA): break
            length = int.from_bytes(raw[pos:pos + 2], "big")
            if length < 2 or pos + length > len(raw): break
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF) and length >= 7:
                height, width = struct.unpack(">HH", raw[pos + 3:pos + 7])
                size = width, height
                break
            pos += length
    elif mime == "image/webp" and raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        if raw[12:16] == b"VP8X" and len(raw) >= 30:
            size = int.from_bytes(raw[24:27], "little") + 1, int.from_bytes(raw[27:30], "little") + 1
        elif raw[12:16] == b"VP8L" and len(raw) >= 25 and raw[20] == 0x2F:
            bits = int.from_bytes(raw[21:25], "little")
            size = (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        elif raw[12:16] == b"VP8 " and len(raw) >= 30 and raw[23:26] == b"\x9d\x01\x2a":
            width, height = struct.unpack("<HH", raw[26:30])
            size = width & 0x3FFF, height & 0x3FFF
    if not size or not all(0 < x <= 16384 for x in size) or size[0] * size[1] > 40_000_000:
        raise ApiError("BAD_INPUT")
    return size


def avatar(raw, mime):
    width, height = dimensions(raw, mime)
    import gi
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf
    loader = GdkPixbuf.PixbufLoader.new_with_type({"image/png": "png", "image/jpeg": "jpeg", "image/webp": "webp"}[mime])
    scale = min(1, 256 / max(width, height))
    loader.set_size(max(1, round(width * scale)), max(1, round(height * scale)))
    closed = False
    try:
        loader.write(raw)
        loader.close(); closed = True
        pixbuf = loader.get_pixbuf()
        if pixbuf is None or max(pixbuf.get_width(), pixbuf.get_height()) > 256: raise ApiError("BAD_INPUT")
        success, data = pixbuf.save_to_bufferv("png", [], [])
        if not success: raise ApiError("BAD_INPUT")
        return "data:image/png;base64," + base64.b64encode(data).decode("ascii")
    except Exception:
        raise ApiError("BAD_INPUT") from None
    finally:
        if not closed:
            try: loader.close()
            except Exception: pass

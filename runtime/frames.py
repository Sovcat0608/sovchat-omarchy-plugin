"""Bounded owner-only shared RAM for the native QML video surface (Linux)."""

import mmap
import os
import secrets
import stat
import struct

MAX_WIDTH, MAX_HEIGHT = 2560, 1440
HEADER = struct.Struct("<8sIIIIQ")
CAPACITY = HEADER.size + MAX_WIDTH * MAX_HEIGHT * 4
MAGIC = b"SOVRGBA2"


class FrameBuffer:
    def __init__(self, runtime_dir=None):
        import fcntl
        self.fcntl = fcntl
        self.name = "sovchat-frame-" + secrets.token_hex(16)
        self.fd = None
        self.memory = None
        self.sequence = 0
        self.owns_path = False
        runtime = str(runtime_dir) if runtime_dir is not None else "/run/user/" + str(os.getuid())
        info = os.stat(runtime, follow_symlinks=False)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise PermissionError("Unsafe runtime directory")
        self.path = runtime + "/" + self.name
        try:
            self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_RDWR, 0o600)
            self.owns_path = True
            os.ftruncate(self.fd, CAPACITY)
            self.memory = mmap.mmap(self.fd, CAPACITY)
        except BaseException:
            self.close()
            raise

    def write(self, width, height, data):
        if type(width) is not int or type(height) is not int or not 0 < width <= MAX_WIDTH or not 0 < height <= MAX_HEIGHT:
            raise ValueError("Invalid frame dimensions")
        size = width * height * 4
        if len(data) != size or self.memory is None:
            raise ValueError("Invalid frame size")
        try:
            self.fcntl.flock(self.fd, self.fcntl.LOCK_EX | self.fcntl.LOCK_NB)
        except BlockingIOError:
            return False  # Drop, never queue frames behind a slow renderer.
        try:
            self.memory[HEADER.size:HEADER.size + size] = data
            self.sequence += 1
            HEADER.pack_into(self.memory, 0, MAGIC, width, height, width * 4, size, self.sequence)
        finally:
            self.fcntl.flock(self.fd, self.fcntl.LOCK_UN)
        return True

    def touch(self):
        if self.memory is None or self.sequence == 0: return False
        try: self.fcntl.flock(self.fd, self.fcntl.LOCK_EX | self.fcntl.LOCK_NB)
        except BlockingIOError: return False
        try:
            self.sequence += 1
            struct.pack_into("<Q", self.memory, 24, self.sequence)
        finally:
            self.fcntl.flock(self.fd, self.fcntl.LOCK_UN)
        return True

    def close(self):
        if self.memory is not None:
            self.memory[:HEADER.size] = bytes(HEADER.size)
            self.memory.close()
            self.memory = None
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        if self.owns_path:
            try: os.unlink(self.path)
            except FileNotFoundError: pass
            self.owns_path = False

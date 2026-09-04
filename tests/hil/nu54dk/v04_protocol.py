"""Bounded, nonce/role/sequence-bound SWD mailbox protocol (no hardware imports)."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct
import tempfile

MAGIC = 0x344C4948
VERSION = 1
WORDS = 32
SIZE = WORDS * 4
MAX_VALUES = 20


class ProtocolError(RuntimeError):
    pass


def checksum(data: bytes) -> int:
    value = 2166136261
    for byte in data:
        value = ((value ^ byte) * 16777619) & 0xFFFFFFFF
    return value


def encode(nonce: bytes, sequence: int, role: int, opcode: int, values=(), status: int = 0) -> bytes:
    if len(nonce) != 16 or nonce == bytes(16) or type(sequence) is not int or not 1 <= sequence <= 0xFFFFFFFF:
        raise ProtocolError("invalid nonce/sequence")
    if role not in (1, 2) or not 1 <= opcode <= 0xFFFF or not 0 <= status <= 0xFFFFFFFF:
        raise ProtocolError("invalid role/opcode/status")
    values = list(values)
    if len(values) > MAX_VALUES or any(type(v) is not int or not 0 <= v <= 0xFFFFFFFF for v in values):
        raise ProtocolError("invalid payload")
    words = [MAGIC, VERSION, sequence, role, opcode, *struct.unpack("<4I", nonce), status, len(values), *values]
    words += [0] * (WORDS - 1 - len(words))
    raw = struct.pack("<31I", *words)
    return raw + struct.pack("<I", checksum(raw))


def decode(raw: bytes, nonce: bytes, sequence: int, role: int, opcode: int) -> tuple[int, list[int]]:
    if len(raw) != SIZE:
        raise ProtocolError("truncated/oversized frame")
    words = struct.unpack("<32I", raw)
    if words[:5] != (MAGIC, VERSION, sequence, role, opcode) or raw[20:36] != nonce:
        raise ProtocolError("stale frame, wrong role/opcode or identity")
    if checksum(raw[:-4]) != words[-1] or words[10] > MAX_VALUES:
        raise ProtocolError("frame checksum/length mismatch")
    count = words[10]
    if any(words[11 + count:31]):
        raise ProtocolError("nonzero frame padding")
    return words[9], list(words[11:11 + count])


def validate_pair(dut: str, peer: str) -> tuple[str, str]:
    values = tuple(v.strip().lower() for v in (dut, peer))
    if any(len(v) != 32 or any(c not in "0123456789abcdef" for c in v) for v in values):
        raise ProtocolError("two exact 32-digit probe UIDs required")
    if values[0] == values[1]:
        raise ProtocolError("DUT and peer must be distinct devices")
    return values


class ProbeLocks:
    """OS-held byte locks, released on process death; lock files need not be deleted."""
    def __init__(self, uids, directory: Path | None = None):
        self.uids = sorted(set(uid.lower() for uid in uids))
        self.directory = directory or Path(tempfile.gettempdir()) / "nu54dk-hil-locks"
        self.streams = []

    def __enter__(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        try:
            for uid in self.uids:
                name = hashlib.sha256(uid.encode("ascii")).hexdigest() + ".lock"
                stream = (self.directory / name).open("a+b")
                try:
                    if stream.seek(0, os.SEEK_END) == 0:
                        stream.write(b"0")
                        stream.flush()
                    stream.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except (OSError, ImportError) as error:
                    stream.close()
                    raise ProtocolError("probe already owned or locking unavailable") from error
                self.streams.append(stream)
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *_):
        for stream in reversed(self.streams):
            try:
                stream.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream, fcntl.LOCK_UN)
            finally:
                stream.close()
        self.streams.clear()

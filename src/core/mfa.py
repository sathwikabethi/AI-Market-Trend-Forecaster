from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
from typing import List


def generate_base32_secret(num_bytes: int = 20) -> str:
    raw = secrets.token_bytes(max(16, int(num_bytes)))
    # RFC 3548 base32, no padding, uppercase.
    return base64.b32encode(raw).decode("utf-8").rstrip("=").upper()


def _b32decode(secret_base32: str) -> bytes:
    secret = (secret_base32 or "").strip().replace(" ", "").upper()
    padding = "=" * (-len(secret) % 8)
    return base64.b32decode(secret + padding, casefold=True)


def totp_code(
    secret_base32: str,
    *,
    for_time: int | None = None,
    step_seconds: int = 30,
    digits: int = 6,
) -> str:
    if for_time is None:
        for_time = int(time.time())
    counter = int(for_time // max(1, int(step_seconds)))
    key = _b32decode(secret_base32)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    dbc = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    code = int(dbc % (10**max(6, int(digits))))
    return str(code).zfill(int(digits))


def verify_totp(
    secret_base32: str,
    code: str,
    *,
    window_steps: int = 1,
    step_seconds: int = 30,
    digits: int = 6,
) -> bool:
    candidate = (code or "").strip()
    if not candidate or not candidate.isdigit():
        return False
    now = int(time.time())
    for offset in range(-int(window_steps), int(window_steps) + 1):
        probe_time = now + (offset * max(1, int(step_seconds)))
        if hmac.compare_digest(
            totp_code(secret_base32, for_time=probe_time, step_seconds=step_seconds, digits=digits),
            candidate,
        ):
            return True
    return False


def generate_backup_codes(count: int = 8) -> List[str]:
    n = max(4, min(int(count or 8), 20))
    # Short, copyable codes; show once.
    return [secrets.token_hex(4).upper() for _ in range(n)]


def hash_backup_code(code: str) -> str:
    value = (code or "").strip().upper()
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def dump_backup_hashes(codes: List[str]) -> str:
    hashes = [hash_backup_code(code) for code in (codes or []) if code]
    return json.dumps(hashes, ensure_ascii=True, separators=(",", ":"))


def load_backup_hashes(raw: str | None) -> List[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [str(item) for item in data if isinstance(item, str) and item]


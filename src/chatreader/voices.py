"""Stable per-viewer voice choice."""
import hashlib


def _digest(platform: str, user: str) -> bytes:
    return hashlib.sha256(f"{platform}:{user.lower()}".encode("utf-8", "replace")).digest()


def voice_for(platform: str, user: str, pool: list[str]) -> str:
    """Pick a voice for a viewer by hash, so it never changes while the pool stays the same."""
    if not pool:
        return ""
    return sorted(pool)[int.from_bytes(_digest(platform, user)[:8], "big") % len(pool)]


def slot_for(platform: str, user: str) -> int:
    """A stable 32-bit number per viewer; themes use it to pick the viewer's hero."""
    return int.from_bytes(_digest(platform, user)[:4], "big")

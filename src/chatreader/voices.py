"""Stable per-viewer voice choice."""
import hashlib


def voice_for(platform: str, user: str, pool: list[str]) -> str:
    """Pick a voice for a viewer by hash, so it never changes while the pool stays the same."""
    if not pool:
        return ""
    digest = hashlib.sha256(f"{platform}:{user.lower()}".encode("utf-8", "replace")).digest()
    return sorted(pool)[int.from_bytes(digest[:8], "big") % len(pool)]

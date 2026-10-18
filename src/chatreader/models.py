from dataclasses import dataclass


@dataclass(frozen=True)
class Msg:
    platform: str
    user: str
    text: str
    ts: float

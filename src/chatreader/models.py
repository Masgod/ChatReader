from dataclasses import dataclass


@dataclass(frozen=True)
class Msg:
    platform: str
    user: str
    text: str
    ts: float
    roles: frozenset[str] = frozenset()  # owner, mod, vip, sub
    kind: str = "chat"  # chat, or an event: bits, subs, gifts, raids, superchat, members
    detail: str = ""  # event size as text: bits, months, gift count, viewers, "R$10.00"; empty when none

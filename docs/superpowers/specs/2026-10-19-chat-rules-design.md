# ChatReader chat rules: roles, duplicates, per-user voices

Date: 2026-10-19
Status: Draft for review

## Goal

Three additions to how chat is turned into speech, inspired by what Lumia Stream
offers: read only chosen roles (set per platform), never read the same text twice
in a short time, and give every viewer a stable voice of their own.

## Decisions (from brainstorming)

| Topic | Decision |
|---|---|
| Roles | One setting per platform (Twitch, YouTube): empty means everyone; otherwise only the listed roles are read. The channel owner is always read. |
| Duplicates | Same text from anyone within a time window is skipped. The existing per-person rule stays. |
| Per-user voice | Picked once by a stable hash of platform and name, from the real voices of the message's language. No override UI now. |
| Control (hotkeys, Stream Deck) | Not here. A separate spec later. |
| Overlay text | Not here. Later. |

## Out of scope

Voice override UI, voice pools or favourites, per-user cooldowns, blocked words,
personal-data masking, alerts (follows, subs, raids), hotkeys, the text overlay.

## Roles

`Msg` gains `roles: frozenset[str] = frozenset()`; existing constructors keep working.
Role names are `owner`, `mod`, `vip`, `sub`.

- Twitch: from the `badges` IRC tag (`broadcaster` is owner, `moderator` is mod, `vip` is vip, `subscriber` and `founder` are sub). The tag is already requested.
- YouTube (`pytchat`): `author.isChatOwner` is owner, `isChatModerator` is mod, `isChatSponsor` (channel member) is sub. YouTube has no vip.
- Config: `twitch_roles: list[str]` and `youtube_roles: list[str]`, each a subset of `sub`, `vip`, `mod`. Empty (the default) reads everyone. A non-empty list reads a message only if its roles intersect the list, or it has `owner`. A role the platform cannot report (vip on YouTube) simply never matches.
- `filters.explain` returns the new reason `role` before the other checks that need history, so no state is touched.
- Validation: unknown role names are rejected with a message (422 on save).

## Duplicates

- Config: `repeat_seconds: int = 30`, 0 turns it off. Range 0 to 600.
- `FilterState` keeps `seen: dict[str, float]` mapping normalized text (casefolded, whitespace collapsed) to the time it was last accepted, using `msg.ts`. Entries older than the window are pruned on each accepted message, and the table is capped at 200 entries (oldest dropped).
- `explain` returns the new reason `duplicate` when the normalized text was accepted from anyone within the window. Only accepted messages are recorded, so a message skipped for another reason never blocks a later one. The per-person `repeat` check stays and runs first.
- Raid effect: the first copy is read, the rest are skipped.

## Per-user voices

- Config: `per_user_voices: bool = True`. Off means everyone uses `voice_pt` / `voice_en` as today.
- `voice_for(platform, user, lang, pool) -> str`: `pool` is the sorted voice ids of that language from `KokoroTTS.voices()`; the pick is `sha256(f"{platform}:{user.lower()}")` taken modulo the pool size. An empty pool returns `""` (use the default voice).
- `QueueItem` gains `voice: str = ""`. `Player.submit(text, lang, user="", voice="")` stores it; the synth callable becomes `synth(text, lang, voice="")`, and prefetch passes it on.
- `KokoroTTS.synth(text, lang, voice="")` uses `voice` when it is a known voice, otherwise the configured default for that language. A bad voice never fails a message.
- The Test voice and preview buttons pass no voice, so they still play the configured default.
- Stable as long as the model's voice list is unchanged; a new model with more voices re-rolls assignments. Portuguese has only three voices, so viewers will share them; English has more.

## UI

- Settings, section Sources: under each platform a "Who is read" chip group: Everyone, Subscribers, VIPs, Mods (Everyone clears the others). YouTube hides VIPs.
- Settings, section Reading: "Skip the same text from anyone for" N seconds (stepper, 0 = off), and a switch "A different voice for each viewer".
- Console: the new skip reasons `role` and `duplicate` appear like the others. The guide's list of skipped messages and reasons is updated.
- Responsive rules, labels and `textContent`-only insertion as in the control center.

## Error handling

| Failure | Behavior |
|---|---|
| Badge tag missing or malformed | No roles; read only if the platform list is empty |
| `isChatSponsor` etc. missing on a YouTube item | Treated as no roles |
| Unknown role in config.toml | The file is treated as unusable like other invalid values (renamed `.bad`, defaults load) |
| Voice picked for a user is not loaded | Falls back to the default voice |
| `tts.voices()` empty (model not loaded) | Default voice path; no per-user pick |

## Testing

Automated, no network or audio:

- Twitch badge parsing for each role, missing tag, malformed tag. YouTube roles from fake items.
- `explain`: `role` for each platform with empty, one and several roles; owner always passes; platform with no vip. `duplicate` inside and outside the window, across users, case and whitespace differences, window 0, prune and cap, and that a skipped message does not enter `seen`. All existing filter tests stay green.
- `voice_for`: stable across calls, platform and case change the key, spreads over the pool, empty pool.
- Player passes the voice to the synth for every sentence including the prefetched one; `KokoroTTS.synth` falls back on an unknown voice.
- Config round trip and validation for the new keys; `/api/config` PUT with bad roles returns 422.
- Pages contain the new controls.

Manual (author): real Twitch and YouTube messages from a mod and a subscriber account, a copy-paste flood from several accounts, and listening to two viewers with different voices.

## Build order

1. `Msg.roles`, Twitch and YouTube role parsing.
2. Config keys and validation; `filters` roles and duplicates; controller passes through.
3. Per-user voice: `voice_for`, `QueueItem.voice`, player and `KokoroTTS.synth`.
4. Settings UI and docs.

Each step keeps the suite green.

## Risks

- The synth signature changes across player, TTS and tests; mitigated by a default `voice=""`.
- Role data from YouTube scraping may be unreliable; a wrong "no roles" only matters when a role filter is set, and the owner exception covers the streamer.
- A strict role filter on a quiet platform can look like "nothing is read"; the Console shows `skipped:role` so it is visible.

# ChatReader Chat Rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read only chosen roles per platform, skip the same text from anyone within a time window, and give every viewer a stable voice of their own.

**Architecture:** `Msg` carries roles parsed by each source. `filters.explain` gains the reasons `role` and `duplicate`. A pure `voice_for` picks a voice by stable hash; the controller attaches it to each queued item and the player hands it to the synth, with `KokoroTTS.synth` falling back to the configured voice. The settings tab gets the new controls.

**Tech Stack:** Python 3.11+, FastAPI, pytest (`uv run pytest -q -m "not slow"`), plain HTML/CSS/JS.

**Spec:** `docs/superpowers/specs/2026-10-19-chat-rules-design.md`

## Global Constraints

- Role names are exactly `owner`, `mod`, `vip`, `sub`. Config lists may hold only `sub`, `vip`, `mod`.
- New config keys and defaults: `twitch_roles: list[str] = []`, `youtube_roles: list[str] = []`, `repeat_seconds: int = 30` (0 to 600), `per_user_voices: bool = True`.
- New skip reasons are exactly `role` and `duplicate`. Existing reasons and their order are unchanged; `role` is checked right after `ignored user`, `duplicate` right after `repeat`.
- `Msg` stays frozen and positional-compatible: `roles` is a last field with default `frozenset()`.
- `Player.submit(text, lang, user="", voice="")`, synth callable `synth(text, lang, voice="")`, `KokoroTTS.synth(text, lang, voice="")`. A bad or empty voice never fails a message.
- `seen` table is capped at 200 entries. Test voice and preview buttons pass no voice.
- Pages keep the control-center rules: labels, visible focus, `textContent` only (no `innerHTML`), no horizontal scroll from 300 px.
- All existing fast tests stay green after every task (currently 225). No new dependencies.

## Review Focus

1. Twitch badge tag that is absent, empty or malformed (`badges=`, `badges=moderator`, `badges=,`): no crash, no roles.
2. A role filter set on a platform with a message from the channel owner: always read.
3. Same text with different case, extra spaces or a different user inside the window: skipped; just outside the window: read; a message skipped for another reason must not block a later identical one.
4. Voice pick for a user whose pool is empty, or whose picked voice the model does not have: default voice, message still plays.
5. A viewer name with unusual characters (emoji, mixed case, spaces): stable voice, no crash.

---

### Task 1: Roles on messages

**Files:**
- Modify: `src/chatreader/models.py`, `src/chatreader/sources/twitch.py`, `src/chatreader/sources/youtube.py`
- Test: `tests/test_models.py` (create if absent, otherwise the existing source tests), `tests/test_twitch.py`, `tests/test_youtube.py` (use the existing test files for those sources)

**Interfaces:**
- Produces: `Msg(platform, user, text, ts, roles: frozenset[str] = frozenset())`; `parse_privmsg` fills roles from the `badges` tag; `to_msg(item)` fills roles from `item.author`.

- [ ] **Step 1: Write failing tests:** `test_msg_roles_default_empty` (`Msg("twitch","a","b",0.0).roles == frozenset()`); `test_twitch_badges_to_roles` (`badges=broadcaster/1,moderator/1,vip/1,subscriber/12` gives `{owner, mod, vip, sub}`; `founder/0` alone gives `{sub}`; `premium/1,turbo/1` gives empty); `test_twitch_bad_badges_tag` (tags `badges=`, `badges=,`, `badges=moderator`, and no badges tag at all each parse without error and give the roles the tag actually lists, otherwise empty); `test_youtube_roles` (fake author with `isChatOwner`, `isChatModerator`, `isChatSponsor` set one by one and together gives owner, mod, sub; an author object missing those attributes gives empty).
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement.** Add the field to `Msg`. In `twitch.py` a small `_roles(badges_tag: str) -> frozenset[str]` mapping `broadcaster→owner`, `moderator→mod`, `vip→vip`, `subscriber` and `founder→sub`, ignoring anything else and tolerating empty entries. In `youtube.py` read the three attributes with `getattr(..., False)`.
- [ ] **Step 4: Run the full fast suite.**
- [ ] **Step 5: Commit** `feat: roles on chat messages`.

### Task 2: Config keys

**Files:**
- Modify: `src/chatreader/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: the four new `Config` fields; `validate` errors `twitch_roles must only contain sub, vip or mod` (same for `youtube_roles`) and `repeat_seconds must be between 0 and 600`.

- [ ] **Step 1: Write failing tests:** `test_new_config_defaults` (the four defaults); `test_roles_validation` (`["sub","mod"]` valid, `[]` valid, `["owner"]` and `["admin"]` each produce the error for that key); `test_repeat_seconds_validation` (`-1` and `601` invalid, `0` and `600` valid); `test_new_keys_round_trip_toml` (save then load keeps them); `test_bad_roles_in_toml_load_defaults` (a file with `twitch_roles = ["admin"]` is renamed `.bad` and defaults load, like other invalid values).
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement** fields and validation in `validate`.
- [ ] **Step 4: Run the full fast suite.** The server's config GET/PUT and the settings page already iterate `fields(Config)`; `tests/test_config_keys.py` must stay green.
- [ ] **Step 5: Commit** `feat: chat rule config keys`.

### Task 3: Role and duplicate filters

**Files:**
- Modify: `src/chatreader/filters.py`
- Test: `tests/test_filters.py`

**Interfaces:**
- Consumes: `Msg.roles`, `Config.twitch_roles`, `Config.youtube_roles`, `Config.repeat_seconds`.
- Produces: `explain` may return `role` or `duplicate`; `FilterState.seen: dict[str, float]`; `apply` records accepted text in `seen`.

- [ ] **Step 1: Write failing tests:** `test_role_filter_empty_reads_everyone`; `test_role_filter_requires_listed_role` (twitch list `["sub"]`: message with `{sub}` passes, with `{}` or `{mod}` gives `role`); `test_role_filter_is_per_platform` (twitch list set, a youtube message with no roles still passes); `test_owner_always_passes_role_filter`; `test_role_filter_unreportable_role` (youtube list `["vip"]` skips every non-owner youtube message); `test_explain_role_before_history` (a role-skipped message leaves `recent` and `seen` untouched); `test_duplicate_from_other_user_within_window` (user a then user b same text 10 s later, window 30: second is `duplicate`); `test_duplicate_normalizes_case_and_spaces`; `test_duplicate_outside_window_passes` (31 s later); `test_duplicate_window_zero_off`; `test_skipped_message_does_not_enter_seen` (a `link` message, then the same text without the link is read; and a `role`-skipped text is read once the filter allows it); `test_seen_is_pruned_and_capped` (250 distinct texts leave at most 200 entries; entries older than the window are dropped); `test_per_user_repeat_still_reports_repeat` (same user same text reports `repeat`, not `duplicate`); `test_explain_agrees_with_apply` extended to the new reasons.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement.** `role` check right after `ignored user`: `allowed = cfg.<platform>_roles` (use `getattr(cfg, f"{msg.platform}_roles", [])`); skip when the list is non-empty, `owner` is not in `msg.roles`, and the roles do not intersect the list. `duplicate` check right after `repeat`: normalized key is `" ".join(text.casefold().split())`; skip when `cfg.repeat_seconds > 0` and `state.seen.get(key)` exists with `msg.ts - seen <= cfg.repeat_seconds`. In `apply`, after the existing history append, store `state.seen[key] = msg.ts`, drop entries older than the window, and drop the oldest while more than 200.
- [ ] **Step 4: Run the full fast suite.**
- [ ] **Step 5: Commit** `feat: role and duplicate filters`.

### Task 4: Per-user voices

**Files:**
- Create: `src/chatreader/voices.py`
- Modify: `src/chatreader/player.py`, `src/chatreader/tts.py`, `src/chatreader/controller.py`
- Test: `tests/test_voices.py` (create), `tests/test_player.py`, `tests/test_tts.py`, `tests/test_controller.py`

**Interfaces:**
- Produces: `voice_for(platform: str, user: str, pool: list[str]) -> str` (sorted pool, empty pool returns `""`); `QueueItem.voice: str = ""`; `Player.submit(text, lang, user="", voice="")` and the synth called as `synth(text, lang, voice)`; `KokoroTTS.synth(text, lang, voice="")`.
- Consumes: `KokoroTTS.voices() -> {"pt": [{"id", "label"}], "en": [...]}`; `Config.per_user_voices`.

- [ ] **Step 1: Write failing tests:** `test_voice_for_is_stable_and_case_insensitive` (same result on repeated calls and for `"Ana"` vs `"ana"`); `test_voice_for_depends_on_platform` (over a pool of 20 voices and 30 names, at least one name differs between twitch and youtube); `test_voice_for_spreads_over_pool` (200 names hit at least 80% of a 10-voice pool); `test_voice_for_empty_pool_and_odd_names` (empty pool gives `""`; names `"🔥 Ana  Maria"`, `""` and 300 characters do not raise); `test_player_passes_voice_to_synth` (every sentence of a multi-sentence message, including the prefetched one, is synthesized with the item's voice; a fake synth records the third argument); `test_submit_without_voice_uses_empty` (existing callers unchanged); `test_tts_synth_uses_given_voice` (FakeKokoro records the voice name used when `voice="af_bella"`); `test_tts_synth_falls_back_on_unknown_voice` (`voice="zz_nope"` and `voice=""` use the configured default and still return audio); `test_controller_attaches_voice_when_enabled` (FakeTTS exposing `voices()`; the submitted voice equals `voice_for(platform, user, ids)` for the detected language); `test_controller_no_voice_when_disabled_or_pool_empty` (`per_user_voices=False`, and a FakeTTS without `voices()` or with an empty list, submit `voice=""`); `test_speak_test_uses_no_voice`.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement** `voices.py` with a sha256 of `f"{platform}:{user.lower()}"`, first 8 bytes as an integer, modulo pool size. Add `voice` to `QueueItem`; `Player.submit` stores it; `_synth_safe` and the prefetch call `self._synth(text, lang, voice)`. Update every test synth stub and `FakeOutput`-style helper in the existing tests to accept `voice=""`. In `KokoroTTS.synth` use `voice` only when it is in the model's known voices and matches `VOICE_NAME_RE`, otherwise the configured one. In `Controller.on_msg`, when `cfg.per_user_voices`, build the pool from `self._tts.voices()[lang]` ids (guard with `getattr` and try/except so a missing method or error means no voice) and pass `voice_for(...)` to `submit`.
- [ ] **Step 4: Run the full fast suite;** also run `uv run python -c "import chatreader.main"` to check wiring still imports.
- [ ] **Step 5: Commit** `feat: stable per-user voices`.

### Task 5: Settings UI and docs

**Files:**
- Modify: `src/chatreader/web/app.html`, `app.css`, `settings.js`, `docs/GUIDE.md`, `README.md`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `GET/PUT /api/config` with the four new keys.

- [ ] **Step 1: Write failing tests:** `test_settings_panel_has_chat_rule_controls` (body contains ids `twitch_roles`, `youtube_roles`, `repeat_seconds`, `per_user_voices`); `test_put_rejects_bad_roles` (PUT with `twitch_roles: ["admin"]` returns 422 and names `twitch_roles`); `test_put_accepts_new_keys` (valid values reach `apply_config`).
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement.** In Sources, under each platform a "Who is read" chip group (`aria-pressed` buttons: Everyone, Subscribers, VIPs, Mods; YouTube has no VIPs; selecting Everyone clears the others, selecting a role clears Everyone; the group is `data-roles="twitch_roles"` / `"youtube_roles"` mapped to state lists using the values `sub`, `vip`, `mod`); in Reading a stepper `repeat_seconds` (0 to 600, step 5, label "Skip the same text from anyone for … seconds, 0 turns it off") and a switch `per_user_voices` ("A different voice for each viewer"). Dirty tracking, save and refresh work as for the other fields, and nothing uses `innerHTML`. Update the guide: section 7 lists `role` and `duplicate`, section 6 describes the new settings, section 8 explains per-user voices and the three Portuguese voices; the Console outcome list gains `skipped:role` and `skipped:duplicate`. README: new keys in the config table and the new test count.
- [ ] **Step 4: Run the full fast suite;** then check the settings tab in the browser pane with a scratch fake server (scratchpad, not committed) at 300, 600 and 1000 px: chips toggle and the dirty state appears, Save sends the lists, no horizontal scroll.
- [ ] **Step 5: Commit** `feat: chat rules settings and docs`.

---

## Self-review notes

- Spec coverage: roles (T1 parsing, T2 config, T3 filter, T5 UI), duplicates (T2, T3, T5), per-user voices (T4, T5 switch), error handling table (T1 tests malformed tags, T4 fallbacks), docs (T5). Control and overlay are out of scope, as in the spec.
- Task order keeps the suite green: T1 and T2 add fields with defaults; T3 uses them; T4 changes the synth signature with a default so unchanged callers work.
- JS behavior cannot be unit tested here; T5 pairs markup and API tests with a browser-pane check.
- Manual checks stay with the author: real mod and subscriber messages on both platforms, a copy-paste flood from several accounts, and listening to two viewers with different voices.

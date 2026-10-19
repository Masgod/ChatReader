# ChatReader Ease of Use Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an OBS dock, real status reporting, a first-run checklist, a speed setting, sentence-level start-up and optional YouTube live auto-detect.

**Architecture:** `Controller.snapshot()` and two new endpoints (`GET /api/status`, `POST /api/control`) feed a new `/dock` page and the settings page. New config keys (`speed`, `cpu_threads`, `youtube_channel`) flow through the existing `PUT /api/config` path. The player gains a one-clip prefetch. YouTube auto-detect is an isolated module gated by a spike.

**Tech Stack:** Python 3.11+, FastAPI, kokoro-onnx, pytest (`uv run pytest -q -m "not slow"`), plain HTML/CSS/JS pages with no build step.

**Spec:** `docs/superpowers/specs/2026-10-19-ease-of-use-design.md`

## Global Constraints

- Server binds `127.0.0.1` only; every new route sits behind the existing `LocalOnly` middleware (local Host, matching Origin, `application/json` on POST/PUT).
- Pages make no outside requests (system font stacks, no CDN). Pages work at 300 px wide, controls have labels and visible focus, state is never shown by color alone.
- `speed` is a float 0.8 to 1.4 inclusive, default `1.0`. `cpu_threads` is an int 1 to 8, default `2`. `youtube_channel` is a str, default `""`.
- `youtube_channel` accepts `@handle` (letters, digits, `_`, `.`, `-`) or a channel ID `UC` plus 22 characters.
- Status `state` values: `off`, `starting`, `connected`, `reconnecting`, `failed`, `error`, `waiting for live`. Model values: `ready`, `missing`, `loading`, `error`.
- Existing 111 fast tests stay green after every task. No new dependencies.
- Kokoro models live in `voices/`. Sentence prefetch stays only if the Task 7 gate passes (time to first audio down by about 30 percent or more).

## Review Focus

1. `/api/status` when a part throws or lacks an attribute (a fake TTS, no overlay): still returns 200 with `error` or `false` for that field. Tested in Task 1 and Task 2.
2. `/api/control` with an unknown action, a missing body, a foreign Origin or a non-JSON content type: 422 or 403, no method called. Tested in Task 2.
3. `speed` sent as JSON `1` is accepted, `true` and `NaN` are rejected, `0.79` and `1.41` are rejected. Tested in Task 5.
4. Messages with no sentence punctuation, a single long sentence, or only punctuation after splitting: exactly one clip, never zero. Tested in Task 7.
5. Waiting for a live YouTube stream: stops promptly on the stop event, never marks the source `failed`, and the video ID wins over the channel. Tested in Task 9.

---

### Task 1: Status data (model state and controller snapshot)

**Files:**
- Modify: `src/chatreader/tts.py`, `src/chatreader/controller.py`
- Test: `tests/test_tts.py`, `tests/test_controller.py`

**Interfaces:**
- Produces: `KokoroTTS.model_state: str` (property, one of `ready|missing|loading|error`), `KokoroTTS.voices_ok: dict[str, bool]` (keys `pt`, `en`).
- Produces: `Controller.snapshot() -> dict` shaped exactly like the spec's status JSON: `sources` (per source `{"configured": bool, "state": str}`), `overlay: bool`, `model: str`, `voices: {"pt": bool, "en": bool}`, `queue: int`, `paused: bool`. It never raises; a failing part becomes `"error"` (strings) or `False` (booleans) or `0` (queue).
- Keeps: `Controller.status()` unchanged, still used by the tray tooltip.

- [ ] **Step 1: Write failing tests**
  - `test_model_state_transitions` (tts): no files gives `missing`; fake loader raising gives `error`; fake loader succeeding gives `ready`.
  - `test_voices_ok_reflects_known_voices` (tts): `Config(voice_pt="zz_nope")` gives `{"pt": False, "en": True}` with the existing `FakeKokoro`.
  - `test_snapshot_shape_and_values` (controller): with `make()`, assert the key set, `sources["twitch"] == {"configured": True, "state": "connected"}` after the fake source starts, `sources["youtube"]["configured"] is False`, `queue == 0`, `paused is False` after `resume()` and `True` after `pause()` (give `FakePlayer` a `paused` bool and `pending` int).
  - `test_snapshot_survives_failing_parts` (controller): a TTS fake whose `model_state` property raises gives `"model": "error"` and the call still returns.
- [ ] **Step 2: Run them and see them fail** (`uv run pytest tests/test_tts.py tests/test_controller.py -q`).
- [ ] **Step 3: Implement.** `KokoroTTS` sets a private `_state` in `reload` (`missing` when files absent, `loading` before calling the loader, `error` on loader failure, `ready` after) and fills `_voices_ok` in the voice-selection loop. `Controller.snapshot` reads each part inside its own try/except; overlay uses the existing `_output.connected` lookup from `status()`.
- [ ] **Step 4: Run the full fast suite**; expect all passing.
- [ ] **Step 5: Commit** `feat: status snapshot and model state`.

### Task 2: Status and control endpoints

**Files:**
- Modify: `src/chatreader/server.py`, `src/chatreader/main.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `Controller.snapshot()`, `Controller.pause/resume/skip`.
- Produces: `create_app(get_config, apply_config, hub, speak_test, get_status, control)` where `get_status: Callable[[], dict]` and `control: Callable[[str], None]`; routes `GET /api/status`, `POST /api/control`, `GET /dock` (serves `web/dock.html`, created in Task 3 as a placeholder page with a `<title>` first so this task is testable).

- [ ] **Step 1: Write failing tests** (update the `env` fixture to pass `get_status=lambda: {"queue": 3}` and a `control` that records actions):
  - `test_status_returns_snapshot`: GET returns 200 and the fixture dict.
  - `test_status_survives_exception`: a `get_status` that raises still gives 200 with `{"error": ...}`.
  - `test_control_calls_action` for `pause`, `resume`, `skip`: 200 `{"ok": true}` and the recorded action.
  - `test_control_rejects_bad_requests`: action `"explode"` gives 422; missing body gives 422; foreign Origin gives 403; `text/plain` gives 403; none record an action.
  - Extend `test_overlay_and_settings_pages_served` to include `/dock`.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement** the routes in `create_app` (validate `action` against `{"pause","resume","skip"}`; status wraps the call in try/except returning `{"error": str(e)}`). In `main.py` pass `controller.snapshot` and a `control` function that dispatches to `controller.pause/resume/skip`. Create `web/dock.html` containing only `<title>chatreader dock</title>` for now.
- [ ] **Step 4: Run the full fast suite.**
- [ ] **Step 5: Commit** `feat: status and control endpoints`.

### Task 3: OBS dock page

**Files:**
- Modify: `src/chatreader/web/dock.html`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `GET /api/status`, `POST /api/control`, `POST /api/test`, `GET`/`PUT /api/config`.

- [ ] **Step 1: Write failing test** `test_dock_page_has_required_controls`: GET `/dock` body contains the ids `st-twitch`, `st-youtube`, `st-overlay`, `st-model`, `btn-pause`, `btn-skip`, `btn-test`, `yt-input`, and the link `/settings`.
- [ ] **Step 2: Run it and see it fail.**
- [ ] **Step 3: Implement the page** in the same visual style as `settings.html` (dark tokens, system fonts). Poll `/api/status` every 1000 ms; on failure show "ChatReader not reachable" and keep polling. Four rows with a dot plus a text label. `btn-pause` text follows `paused`. `btn-test` posts a sample line using the default language from `/api/config`. `yt-input`: on change, fetch config, set `youtube_video_id` to the typed value, `PUT` the full config, show returned `errors` under the field. Link "Full settings" with `target="_blank"`.
- [ ] **Step 4: Run the full fast suite;** then open `/dock` in the browser pane at 360 px and 300 px and confirm there is no horizontal scroll and the rows read correctly.
- [ ] **Step 5: Commit** `feat: OBS dock page`.

### Task 4: Settings page real status and checklist

**Files:**
- Modify: `src/chatreader/web/settings.html`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `GET /api/status`.

- [ ] **Step 1: Write failing test** `test_settings_page_has_checklist`: body contains ids `checklist`, `chk-model`, `chk-source`, `chk-overlay`.
- [ ] **Step 2: Run it and see it fail.**
- [ ] **Step 3: Implement.** Poll `/api/status` every 2000 ms. The header status text shows connected source names, otherwise `idle · :port` (replace the form-derived text). The `checklist` banner lists three items (voice model ready, at least one source configured, overlay connected) with a tick or empty marker plus text, and is hidden when all are true.
- [ ] **Step 4: Run the full fast suite;** check the page in the browser pane with a mocked status (as done for the redesign) for the shown and hidden banner.
- [ ] **Step 5: Commit** `feat: settings status and first-run checklist`.

### Task 5: Config keys

**Files:**
- Modify: `src/chatreader/config.py`, `src/chatreader/server.py` (`_type_errors`)
- Test: `tests/test_review_fixes.py` (or a new `tests/test_config_keys.py`), `tests/test_server.py`

**Interfaces:**
- Produces: `Config.speed: float = 1.0`, `Config.cpu_threads: int = 2`, `Config.youtube_channel: str = ""`; `CHANNEL_RE`; `normalize` reduces a pasted channel URL (`youtube.com/@name`, `youtube.com/channel/UC...`) to the handle or ID; `validate` returns messages for out-of-range `speed`, `cpu_threads`, bad `youtube_channel`.

- [ ] **Step 1: Write failing tests:**
  - `test_speed_bounds`: 0.8 and 1.4 pass; 0.79, 1.41 and `float("nan")` fail `validate`.
  - `test_cpu_threads_bounds`: 1 and 8 pass; 0 and 9 fail.
  - `test_channel_forms`: `@some.name-1` passes; `UC` plus 22 valid characters passes; `some name` and `@` fail; `https://www.youtube.com/@Foo/live` normalizes to `@Foo`.
  - `test_put_accepts_int_for_float_speed`: PUT with `"speed": 1` returns 200; `"speed": true` returns 422.
  - `test_load_config_accepts_int_speed`: TOML `speed = 1` loads as 1.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement.** In `_type_errors` and `_same_type`, treat a float default as accepting `int` but not `bool`. Add the three fields and validation in `config.py`.
- [ ] **Step 4: Run the full fast suite.**
- [ ] **Step 5: Commit** `feat: speed, cpu_threads and youtube_channel config`.

### Task 6: Speed and CPU threads in speech and UI

**Files:**
- Modify: `src/chatreader/tts.py`, `src/chatreader/controller.py`, `src/chatreader/web/settings.html`, `src/chatreader/web/dock.html`
- Test: `tests/test_tts.py`, `tests/test_controller.py`, `tests/test_server.py`

**Interfaces:**
- Consumes: `Config.speed`, `Config.cpu_threads`.
- Produces: loader signature becomes `loader(model: Path, voices: Path, threads: int)`; `KokoroTTS` passes `speed=cfg.speed` to `create` (the `THREADS` constant is removed).

- [ ] **Step 1: Write failing tests:** `test_speed_passed_to_create` (the fake `create` records `speed`; after `reload(Config(speed=1.2))` the next synth uses 1.2); `test_loader_gets_threads` (loader records `threads == cfg.cpu_threads` at construction; a later `reload` with a different value does not reload the model); `test_apply_config_reloads_on_speed_change` (controller: only `speed` changed triggers `tts.reload`; changing neither voice nor speed does not); update existing fake loaders to the three-argument form. Page tests: settings body contains ids `speed` and `cpu_threads`; dock body contains `speed-input`.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement.** Store speed in `reload`; thread count read once at construction. Controller reload condition adds `speed`. Settings: a Speed stepper/slider in Voices and a CPU threads stepper in System with hint "Restart required to apply" when changed (same pattern as `port`). Dock: a speed slider that does the same fetch-edit-PUT as the YouTube field.
- [ ] **Step 4: Run the full fast suite;** then the slow test (`uv run pytest -q -m slow`) with the real model.
- [ ] **Step 5: Commit** `feat: speed and cpu threads`.

### Task 7: Sentence prefetch (measurement gate)

**Files:**
- Modify: `src/chatreader/player.py`
- Test: `tests/test_player.py`

**Interfaces:**
- Produces: `split_sentences(text: str) -> list[str]` in `player.py`: splits after `.`, `!`, `?` or `…` followed by whitespace; strips pieces; drops empty pieces; returns `[text]` when nothing remains or no split applies.

- [ ] **Step 1: Measure before coding.** With the real model, time (a) full synthesis and (b) synthesis of only the first sentence for five multi-sentence chat lines (Portuguese and English, 2 to 3 sentences each). Record the numbers in the commit message. If the average time to first audio drops by less than about 30 percent, skip the rest of this task, note it in `docs/superpowers/plans/` progress notes, and go to Task 8.
- [ ] **Step 2: Write failing tests:**
  - `test_split_sentences_cases`: `"Oi. Tudo bem? Sim!"` gives three pieces; `"sem pontuacao"` gives one; `"..."` and `"?!"` give one (the original); a long text with no terminal punctuation gives one.
  - `test_message_plays_sentences_in_order`: fake synth records calls and returns the sentence bytes; fake output records `play` calls; one submit of `"A. B. C."` plays `A.`, `B.`, `C.` in order.
  - `test_next_sentence_synth_overlaps_playback`: output `play` blocks on an event; assert the synth for sentence 2 started before sentence 1's `play` returned; at most one synth runs at a time.
  - `test_skip_drops_remaining_sentences`: skip during sentence 1 means sentences 2 and 3 never reach `play`, and the next queued message plays.
  - `test_shutdown_during_prefetch_exits_cleanly`: shutdown while sentence 2 is synthesizing returns without hanging (join within the 2 s limit).
  - `test_failed_later_sentence_skips_only_it`: synth raising on sentence 2 still plays 1 and 3.
- [ ] **Step 3: Run them and see them fail.**
- [ ] **Step 4: Implement** in `Player._run`: split the message, submit sentence synthesis to a single-worker executor owned by the player, always keep at most one synthesis in flight, check `_shutdown` and the skip generation (captured when the message was popped) before each `play`. Executor is shut down in `shutdown()`.
- [ ] **Step 5: Run the full fast suite;** re-measure time to first audio with the real model and record it.
- [ ] **Step 6: Commit** `feat: sentence prefetch`.

### Task 8: YouTube live lookup spike (no code kept)

**Files:**
- Create: `docs/superpowers/plans/2026-10-19-youtube-live-spike.md` (findings only)

- [ ] **Step 1: Probe.** In the scratchpad, request `https://www.youtube.com/@<handle>/live` for a channel that is live and one that is not (ask the user for a live channel at the time; use any currently live channel for the first check). Record: HTTP status, final URL, where the video ID appears (redirect, canonical link, page data), and whether the offline channel is distinguishable.
- [ ] **Step 2: Repeat** the same requests on three occasions over a day (at least a few hours apart).
- [ ] **Step 3: Write the findings** and a decision: reliable (go to Task 9) or not (drop Task 9; also drop the `youtube_channel` key from the settings and dock UI and keep the config key unused or remove it in a small follow-up).
- [ ] **Step 4: Commit** the findings doc. Show the user the decision before Task 9.

### Task 9: YouTube channel resolver and waiting loop (only if Task 8 passes)

**Files:**
- Create: `src/chatreader/sources/youtube_live.py`
- Modify: `src/chatreader/sources/youtube.py`, `src/chatreader/controller.py`, `src/chatreader/main.py`, `src/chatreader/web/settings.html`, `src/chatreader/web/dock.html`
- Test: `tests/test_youtube_live.py`, `tests/test_sources.py`, `tests/test_controller.py`

**Interfaces:**
- Produces: `resolve_live_video(channel: str, fetch: Callable[[str], tuple[int, str, str]] | None = None) -> str | None` where `fetch(url)` returns `(status, final_url, body)`; returns an 11-character video ID or `None`; never raises; timeout 10 s on the default fetch.
- Produces: `run_youtube(video_id, on_msg, stop, on_status, chat_factory=..., channel="", resolver=resolve_live_video)`; the controller passes the channel and restarts the YouTube source when `youtube_channel` or `youtube_video_id` changes.

- [ ] **Step 1: Write failing tests:**
  - `test_resolver_live_and_offline`: recorded response fixtures (from the spike) give the ID for live and `None` for offline; a fetch that raises, a 404, and garbage bodies give `None`.
  - `test_video_id_wins_over_channel`: with both set, the resolver is never called.
  - `test_waits_for_live_without_failing`: the resolver returns `None` three times then an ID; the statuses seen are `waiting for live` (not `failed`), then `connected`; it never counts toward `max_failures`.
  - `test_waiting_stops_promptly`: setting the stop event while waiting ends `run_youtube` within 1 s.
  - Controller: with only `youtube_channel` set the source starts (`configured` is true in `snapshot`); changing the channel restarts only the YouTube source.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement.** The waiting loop polls every 30 s through `stop.wait`. `_SOURCE_VALUE["youtube"]` becomes the pair (`youtube_video_id`, `youtube_channel`) in the controller's restart comparison and start guard. UI: the dock field accepts a video link/ID or a handle/channel (set `youtube_channel` when the value starts with `@` or `UC`, else `youtube_video_id`); the settings page gets a YouTube channel field.
- [ ] **Step 4: Run the full fast suite.**
- [ ] **Step 5: Commit** `feat: youtube live auto-detect`.

### Task 10: Documentation

**Files:**
- Modify: `docs/GUIDE.md`, `README.md`

- [ ] **Step 1: Update `docs/GUIDE.md`:** a section "Control it from OBS" (Docks, Custom Browser Docks, URL `http://127.0.0.1:8765/dock`); the new settings (Speed, CPU threads, and YouTube channel if Task 9 shipped); the first-run checklist; the troubleshooting row about "ChatReader not reachable".
- [ ] **Step 2: Update `README.md`:** config table rows for `speed`, `cpu_threads`, `youtube_channel` (if shipped), the new endpoints, the fast test count, and a line saying prefetch shipped or was dropped by the gate.
- [ ] **Step 3: Run the full fast suite**, then commit `docs: dock, speed and checklist`.

---

## Self-review notes

- Spec coverage: status endpoint (T1, T2), control endpoint (T2), dock (T3), settings status and checklist (T4), config keys (T5), speed and threads (T6), prefetch and gate (T7), YouTube spike and feature (T8, T9), docs and manual checks (T10).
- The spec says `Controller.status()` returns the full dict; the plan adds `snapshot()` instead and leaves `status()` for the tray tooltip, to avoid breaking its flat format. Same data, different method name.
- The YouTube field on the dock is built in Task 3 for video IDs and extended in Task 9 for channels, so the dock is complete even if Task 9 is dropped.
- Manual checks stay with the user: loading `/dock` as a real OBS dock, CPU use during a game, and the day-long YouTube spike if no live channel is available to the agent.

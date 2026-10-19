# ChatReader Control Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One responsive app page (Live, Console, Settings tabs) with a queue you can edit, a live console of chat outcomes and app log, tray controls on the page, and a real voice picker.

**Architecture:** A thread-safe `EventLog` ring buffer is filled by the controller (chat outcomes), the player (play results) and a logging handler (app log). The server exposes it and the player's queue through polling JSON endpoints behind the existing `LocalOnly` guard. The old dock and settings pages are replaced by one page split into small JS files; `/`, `/dock` and `/settings` all serve it.

**Tech Stack:** Python 3.11+, FastAPI, pytest (`uv run pytest -q -m "not slow"`), plain HTML/CSS/JS with no build step and no outside requests.

**Spec:** `docs/superpowers/specs/2026-10-19-control-center-design.md`

## Global Constraints

- Server binds `127.0.0.1` only; every new route sits behind `LocalOnly` (local Host, matching Origin, `application/json` on POST).
- Event buffer capacity is 500. `GET /api/events?since=N` returns events with `id > N` and the latest id as `last`.
- Chat outcomes are exactly: `queued`, `played`, `failed`, `dropped`, `skipped:<reason>` with reason in `ignored user`, `command`, `link`, `no text`, `repeat`, `spam`; the plan adds `skipped` (user pressed Skip) and `removed` (removed from the queue by the user) as outcomes.
- Chat text lives in memory only; nothing in this feature writes it to disk.
- Pages: system font stacks, dark theme, real labels, visible focus, state shown by text plus color, no horizontal scroll from 300 px up, all server text inserted with `textContent` (no `innerHTML` anywhere in the app JS).
- Breakpoints: 800 px and up two-column Live; 480 to 800 single column; under 480 compact with collapsible settings sections.
- Existing 161 fast tests stay green after every task. No new dependencies.

## Review Focus

1. `GET /api/events` with `since` that is not an integer, negative or huge: 422 or treated as 0, never a crash. Tested in Task 5.
2. `remove(id)` racing with the worker taking that item: exactly one outcome (removed or played), no double play, no crash. Tested in Task 3.
3. Chat text containing HTML (`<img onerror=...>`): shown as text, never as markup. Tested in Task 7 (no `innerHTML` in the JS files) and by hand in Task 9.
4. The log mirror: an exception inside it, or logging from inside `EventLog.add`, never recurses or breaks logging. Tested in Task 1.
5. Quit and background polling: `quit` answers before the app stops; hidden tabs stop polling; a failed poll shows "not reachable" and recovers. Tested in Task 5 (quit) and checked by hand in Tasks 8 and 9.

---

### Task 1: Event log and log mirror

**Files:**
- Create: `src/chatreader/events.py`
- Test: `tests/test_events.py`

**Interfaces:**
- Produces: `EventLog(capacity: int = 500)` with `add(kind: str, level: str, **fields) -> int` (returns the new id, ids start at 1), `since(n: int = 0) -> dict` returning `{"events": [dict, ...], "last": int}` (each event has `id`, `ts`, `kind`, `level` plus its fields), `clear() -> None`.
- Produces: `LogMirror(events: EventLog)` a `logging.Handler` that adds `kind="app"` events with `message` and `logger`; levels map `DEBUG`→`debug`, `INFO`→`info`, `WARNING`→`warn`, `ERROR` and up→`error`.

- [ ] **Step 1: Write failing tests:**
  - `test_ids_increase_and_since_slices`: three adds give ids 1, 2, 3; `since(1)` returns ids 2 and 3 and `last == 3`; `since(3)` returns `[]` and `last == 3`.
  - `test_capacity_drops_oldest`: capacity 3, add 5; `since(0)` returns ids 3, 4, 5; `last == 5`.
  - `test_since_older_than_buffer_returns_remaining`: same buffer, `since(1)` returns ids 3, 4, 5.
  - `test_concurrent_writers`: 4 threads add 250 events each into capacity 2000; ids are unique and `last == 1000`.
  - `test_mirror_copies_records_with_levels`: a logger with `LogMirror` attached at level INFO: `info`, `warning`, `error` records appear with levels `info`, `warn`, `error`; a `debug` record does not appear (logger level filters it); with the logger at DEBUG it does.
  - `test_mirror_swallows_errors`: an `EventLog` whose `add` raises does not make `logger.error(...)` raise, and the mirror does not log again.
- [ ] **Step 2: Run them and see them fail** (`uv run pytest tests/test_events.py -q`; Expected: import error).
- [ ] **Step 3: Implement** both classes in `events.py`: a `collections.deque(maxlen=capacity)` plus a `threading.Lock`; `since` copies under the lock; `LogMirror.emit` wraps everything in try/except and never calls logging.
- [ ] **Step 4: Run the new tests and the full fast suite;** Expected: all pass.
- [ ] **Step 5: Commit** `feat: event log and log mirror`.

### Task 2: Filter skip reasons

**Files:**
- Modify: `src/chatreader/filters.py`
- Test: `tests/test_filters.py`

**Interfaces:**
- Produces: `explain(msg: Msg, cfg: Config, state: FilterState) -> str | None` returning the first failing reason (`ignored user`, `command`, `link`, `no text`, `repeat`, `spam`) or `None`. It never mutates `state`.
- Keeps: `apply(msg, cfg, state) -> Msg | None` with identical results, now built on `explain`.

- [ ] **Step 1: Write failing tests:** `test_explain_reasons` (one parametrized case per reason with the strings above; ignored-user check is case-insensitive; `!cmd` gives `command`; `https://x.y` gives `link`; `"..."` gives `no text`; a text equal to the same user's previous message gives `repeat`; `"aaaaaaaaaa"` gives `spam`); `test_explain_does_not_record_history` (calling `explain` twice on a fresh message returns `None` both times and does not make the second call `repeat`); `test_explain_agrees_with_apply` (for every message in the existing filter test table, `explain(...) is None` exactly when `apply(...)` returns a message, using fresh state for each).
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement** `explain` with the checks in the same order as today's `apply`; rewrite `apply` as: `if explain(...): return None`, then record the history and truncate as before.
- [ ] **Step 4: Run `tests/test_filters.py` and the full fast suite;** Expected: all pass, existing filter tests unchanged.
- [ ] **Step 5: Commit** `feat: filter skip reasons`.

### Task 3: Player queue ids, snapshot, remove, clear, events

**Files:**
- Modify: `src/chatreader/player.py`
- Test: `tests/test_player.py`

**Interfaces:**
- Produces: `QueueItem(id: int, text: str, lang: str, user: str)` (frozen dataclass).
- Produces: `Player(synth, output, maxsize, on_event: Callable[[QueueItem, str], None] | None = None)`; `submit(text, lang, user="") -> None`; `snapshot() -> dict` shaped `{"playing": QueueItem | None, "waiting": list[QueueItem]}`; `remove(id: int) -> bool` (waiting items only); `clear() -> int`.
- Produces: `on_event(item, outcome)` called with `dropped` (oldest item evicted by a full queue), `removed` (by `remove` or `clear`), `played` (every sentence handled and not skipped), `skipped` (skip generation changed), `failed` (every sentence failed to synthesize). It is called outside the player's lock, and exceptions from it are logged and ignored.

- [ ] **Step 1: Write failing tests:**
  - `test_submit_assigns_unique_ids_and_snapshot_orders_waiting`: pause the player, submit three messages with users; `snapshot()["waiting"]` is in order with strictly increasing ids and the users kept; `playing` is `None`.
  - `test_snapshot_reports_playing_item`: with a blocking output, the playing item shows up in `playing` and is gone from `waiting`; after it finishes `playing` is `None`.
  - `test_remove_waiting_unknown_and_playing`: removing a waiting id returns `True` and it never plays; an unknown id returns `False`; the playing id returns `False`.
  - `test_clear_returns_count_and_emits_removed`: three waiting, `clear()` returns 3 and `on_event` got `removed` three times.
  - `test_full_queue_emits_dropped_with_evicted_item`: `maxsize=2`, paused, submit three; `on_event` got `(first_item, "dropped")`.
  - `test_played_failed_skipped_outcomes`: a normal item gives `played`; a synth that always raises gives `failed`; skipping during playback gives `skipped` and not `played`.
  - `test_remove_races_with_worker`: submit many items with a slow output; call `remove` on all ids from another thread while the worker runs; every id has exactly one of `removed` or `played`/`skipped` in the recorded events, and no item plays after being reported removed.
  - `test_on_event_exception_is_ignored`: an `on_event` that raises does not stop the next item from playing.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement.** Queue entries become `QueueItem` with ids from a counter under `_cond`; keep the `deque(maxlen)` and detect eviction by checking `len == maxlen` before append; track `_playing` under the lock (set at pop, cleared when the item finishes, including on skip, failure and shutdown); collect events to fire and call `on_event` after releasing the lock. `set_maxsize` keeps rebuilding the deque and reports evicted items as `dropped`. The synth and prefetch code from the sentence work stays unchanged, but its per-sentence failure is counted so `failed` can be decided.
- [ ] **Step 4: Run `tests/test_player.py` and the full fast suite,** three times for the race test; Expected: all pass each time.
- [ ] **Step 5: Commit** `feat: queue ids, snapshot, remove and clear`.

### Task 4: Controller records chat outcomes

**Files:**
- Modify: `src/chatreader/controller.py`
- Test: `tests/test_controller.py`

**Interfaces:**
- Consumes: `explain` (Task 2), `EventLog.add` (Task 1), `Player.submit(text, lang, user)` (Task 3).
- Produces: `Controller(cfg, player, tts, source_factories, events: EventLog | None = None)`; `Controller.record_item_event(item: QueueItem, outcome: str) -> None` (adds a chat event `outcome=<outcome>`, `user`, `text` from the item) for `main.py` to pass as the player's `on_event`.

- [ ] **Step 1: Write failing tests** (using `FakePlayer`, which gains `submit(self, text, lang, user="")` recording the user):
  - `test_skipped_message_is_recorded_with_reason`: a message from `nightbot` gives one chat event with `outcome == "skipped:ignored user"`, the user and text, and nothing is submitted.
  - `test_each_filter_reason_is_recorded`: `!cmd`, a link, `"..."`, a repeat and spam give `skipped:command`, `skipped:link`, `skipped:no text`, `skipped:repeat`, `skipped:spam`.
  - `test_accepted_message_is_recorded_as_queued_with_user`: outcome `queued`; `FakePlayer.submitted` shows the user passed through.
  - `test_record_item_event`: calling it adds a chat event with the item's user and text and the given outcome.
  - `test_events_optional`: a `Controller` built without `events` still handles messages.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement.** In `on_msg`, under the lock call `explain(msg, cfg, state)`; if it returns a reason, add the skipped event and return; otherwise call `apply` as today and add `queued` after `submit`. `speak_test` submits with `user="test"` and records `queued`.
- [ ] **Step 4: Run the full fast suite;** Expected: all pass.
- [ ] **Step 5: Commit** `feat: controller records chat outcomes`.

### Task 5: Server endpoints

**Files:**
- Modify: `src/chatreader/server.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Produces: `create_app(get_config, apply_config, hub, speak_test, get_status, control, *, queue=None, events=None, toggle=None, voices=None)` where `queue` has `snapshot()`, `remove(id)`, `clear()`; `events` has `since(n)`; `toggle: Callable[[str, bool], None]`; `voices: Callable[[], dict]`. A missing dependency makes its routes return 503 `{"errors": ["not available"]}`.
- Produces routes: `GET /api/queue` (snapshot with items as `{"id","text","lang","user"}`), `POST /api/queue/remove` `{"id": int}` → `{"ok": true}` or 404, `POST /api/queue/clear` → `{"removed": int}`, `GET /api/events?since=N`, `POST /api/toggle` `{"name": "debug", "value": bool}`, `GET /api/voices`, and `quit` added to the actions of `POST /api/control` (the response is sent first, then `control("quit")` runs).

- [ ] **Step 1: Write failing tests** (fixtures with fake `queue`, `events`, `toggle`, `voices`):
  - `test_queue_snapshot_serializes_items`; `test_queue_remove_ok_and_404`; `test_queue_remove_bad_body_422` (missing id, string id, bool id); `test_queue_clear_returns_count`.
  - `test_events_since_slices`; `test_events_bad_since`: `since=abc`, `since=-5`, `since=99999999999999999999` each give 422 or are treated as 0, never 500.
  - `test_toggle_debug_and_unknown_name`: `debug` true calls `toggle("debug", True)`; name `bogus` gives 422; non-bool value gives 422.
  - `test_voices_returns_grouped_lists`.
  - `test_control_quit_responds_then_calls`: the response is `{"ok": true}` and the control callback received `"quit"` after the response.
  - `test_new_routes_reject_foreign_origin_and_text_plain` for each POST route (403).
  - `test_missing_dependency_returns_503`: an app built without `queue` answers `/api/queue` with 503.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement** the routes with FastAPI `BackgroundTasks` for `quit`; parse `since` with a guarded `int()` clamped to `0..2**53`.
- [ ] **Step 4: Run the full fast suite;** Expected: all pass.
- [ ] **Step 5: Commit** `feat: queue, events, toggle, voices and quit endpoints`.

### Task 6: Wiring, voices and debug toggle

**Files:**
- Modify: `src/chatreader/tts.py`, `src/chatreader/main.py`
- Test: `tests/test_tts.py`, `tests/test_main.py` (create if absent)

**Interfaces:**
- Consumes: Tasks 1 to 5.
- Produces: `KokoroTTS.voices() -> dict[str, list[dict]]` returning `{"pt": [{"id","label"}], "en": [...]}` from the loaded model's `get_voices()`: ids starting with `p` go to `pt`, ids starting with `a` or `b` go to `en`; empty lists when the model is not loaded. Labels are `"<Name> (female|male)"` from the id (second letter `f`/`m`, name capitalized).
- Produces: in `main.py`, `make_toggle(controller, apply_config) -> Callable[[str, bool], None]` that, for `debug`, builds `replace(controller.cfg, debug=value)` and calls `apply_config` (which already sets the log level and saves); other names raise `ValueError`.

- [ ] **Step 1: Write failing tests:** `test_voices_grouped_and_labelled` (fake model voices `["pf_dora","pm_alex","af_heart","bm_george","zf_xiaoyi"]` give pt `[Dora (female), Alex (male)]`, en `[Heart (female), George (male)]`, and Chinese is not listed); `test_voices_empty_when_model_missing`; `test_toggle_debug_applies_config` (a fake `apply_config` receives a config with `debug=True`); `test_toggle_unknown_name_raises`.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement.** In `main.py` create one `EventLog`, attach `LogMirror` to the root logger, pass `events` to `Controller`, pass `on_event=controller.record_item_event` to `Player`, and pass `queue=player`, `events=events`, `toggle=make_toggle(...)`, `voices=tts.voices` to `create_app`. Extend the control dispatcher so `quit` calls `icon.stop()`.
- [ ] **Step 4: Run the full fast suite;** then start the app once (`uv run python -m chatreader` in a scratch `CHATREADER_HOME`) and confirm it boots and `GET /api/voices` lists voices; stop it.
- [ ] **Step 5: Commit** `feat: wire event log, queue, toggle, voices and quit`.

### Task 7: App shell and routing

**Files:**
- Create: `src/chatreader/web/app.html`, `app.css`, `app.js`
- Modify: `src/chatreader/server.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Produces: routes `GET /` , `GET /dock`, `GET /settings` all serving `app.html`; `GET /static/{name}` serving only `app.css`, `app.js`, `live.js`, `console.js`, `settings.js` (anything else 404; path separators rejected).
- Produces in `app.js`: `window.App = { api(path, opts) -> Promise<json>, poll(fn, ms) -> stop function (skips while document.hidden), tab registry }`, tab routing from the URL hash (`#live`, `#console`, `#settings`) with `/dock` defaulting to `#live` and `/settings` to `#settings`, the last tab remembered in `localStorage` inside try/catch, a sticky header with the live status text, and a "ChatReader not reachable" banner shown when polls fail and cleared when they recover.

- [ ] **Step 1: Write failing tests:** `test_app_page_has_shell` (`/` body has the ids `tab-live`, `tab-console`, `tab-settings`, `panel-live`, `panel-console`, `panel-settings`, `status-text`, `banner`); `test_dock_and_settings_serve_app` (both return the same body as `/`); `test_static_whitelist` (`/static/app.js` and `/static/app.css` return 200 with JS and CSS types; `/static/../server.py`, `/static/nope.js` and `/static/%2e%2e%2fconfig.py` return 404); `test_app_js_never_uses_innerhtml` (read every file under `web/` matching `app*.js`, `live.js`, `console.js`, `settings.js` that exists and assert `innerHTML` is not in any).
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement** the shell with the dark tokens from the current pages, the three tab buttons and panels (empty panels now), and the responsive header. The old `dock.html` and `settings.html` stay until Task 9.
- [ ] **Step 4: Run the full fast suite;** then serve the app from a scratch script (fakes, scratchpad directory) and check in the browser pane at 300, 600 and 1000 px: tabs switch, hash and reload keep the tab, no horizontal scroll.
- [ ] **Step 5: Commit** `feat: app shell and routing`.

### Task 8: Live tab

**Files:**
- Create: `src/chatreader/web/live.js`
- Modify: `src/chatreader/web/app.html`, `app.css`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `App.api`, `App.poll`, `/api/status`, `/api/queue`, `/api/queue/remove`, `/api/queue/clear`, `/api/control`.

- [ ] **Step 1: Write failing test** `test_live_panel_has_controls`: `/` body contains the ids `st-twitch`, `st-youtube`, `st-overlay`, `st-model`, `btn-pause`, `btn-skip`, `btn-copy`, `btn-quit`, `queue-list`, `btn-clear`, and the script tag for `/static/live.js`.
- [ ] **Step 2: Run it and see it fail.**
- [ ] **Step 3: Implement.** Status rows with dot plus text from `/api/status`; Pause/Resume label follows `paused`; Skip; Copy overlay URL via `navigator.clipboard.writeText` with a rejection fallback that shows the URL selected; Quit with a second confirming click (label "Really quit?" for 4 s) then shows "ChatReader stopped" and stops all polling; the queue list shows the playing item then waiting items with a remove button each and Clear all, polling every second only while the Live tab is visible; a 404 from remove refreshes silently. Wide layout is two columns from 800 px.
- [ ] **Step 4: Run the full fast suite;** then in the browser pane with the scratch fake server check: removing and clearing items, Quit flow, hidden-tab polling stops (watch the request count), at 300, 600 and 1000 px.
- [ ] **Step 5: Commit** `feat: live tab with queue and controls`.

### Task 9: Console tab

**Files:**
- Create: `src/chatreader/web/console.js`
- Modify: `src/chatreader/web/app.html`, `app.css`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `GET /api/events?since=N`, `POST /api/toggle`, `GET /api/config`.

- [ ] **Step 1: Write failing test** `test_console_panel_has_controls`: the body contains `console-lines`, `filter-all`, `filter-chat`, `filter-log`, `toggle-debug`, `btn-pause-scroll`, `btn-clear-view`, `btn-jump`, and the script tag for `/static/console.js`.
- [ ] **Step 2: Run it and see it fail.**
- [ ] **Step 3: Implement.** Poll with the last seen id every second while the tab is visible; keep the last 500 lines; chat lines show time, user, text and an outcome tag (text plus color: green `played`/`queued`, amber `skipped:*`/`dropped`/`removed`/`skipped`, red `failed`); log lines show level and message with warn and error marked; every string goes in through `textContent`. Filter chips All, Chat, Log; Debug toggle reads `debug` from `/api/config` and posts `/api/toggle`; Pause scrolling freezes the view but keeps buffering; Clear view empties the list only; newest lines stay in view until the user scrolls up, when the "Jump to latest" button appears. Compact line layout under 480 px.
- [ ] **Step 4: Run the full fast suite;** then in the browser pane with the scratch fake server (include an event whose text is `<img src=x onerror=alert(1)>`): it shows as literal text and nothing executes; check filters, debug toggle, scroll behavior, and 300, 600, 1000 px.
- [ ] **Step 5: Commit** `feat: console tab`.

### Task 10: Settings tab, voice picker, remove the old pages

**Files:**
- Create: `src/chatreader/web/settings.js`
- Modify: `src/chatreader/web/app.html`, `app.css`, `src/chatreader/server.py`
- Delete: `src/chatreader/web/settings.html`, `src/chatreader/web/dock.html`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `GET /api/voices`, `GET/PUT /api/config`, `POST /api/test`, `GET /api/status` (for the checklist).

- [ ] **Step 1: Write failing tests:** `test_settings_panel_has_fields` (the body contains the ids `voice_pt`, `voice_en`, `speed`, `cpu_threads`, `youtube_channel`, `twitch_channel`, `youtube_video_id`, `queue_size`, `max_chars`, `repeat_window`, `port`, `btn-save`, `btn-test`, `checklist`, and the script tag for `/static/settings.js`); `test_old_page_files_removed` (no `settings.html` or `dock.html` under `web/`); the existing page tests for `/overlay`, `/settings`, `/dock` still pass.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement by porting** the current settings behavior into `settings.js` (state object, dirty detection, `Number` coercion, `ignored_users` list, 422 `errors` rendering, port/threads "restart required" hints, checklist from `/api/status`, speed slider, Test voice and ▶ previews). Voices: each voice field is a `<select>` filled from `/api/voices` for that language (grouped by gender); if the list is empty or the request fails, replace it with the text input and keep the saved value. Sections become collapsible: all open from 480 px, collapsed by default under 480 px except Sources. Footer with Save and Test voice stays sticky. Remove the two old HTML files and drop their routes' file reads.
- [ ] **Step 4: Run the full fast suite;** then in the browser pane: change a field (dirty state appears, Save enables), save with a bad value (errors list), voice picker shows grouped voices and falls back to the text box when `/api/voices` returns empty lists, at 300, 600 and 1000 px.
- [ ] **Step 5: Commit** `feat: settings tab and voice picker; remove old pages`.

### Task 11: Documentation

**Files:**
- Modify: `docs/GUIDE.md`, `README.md`

- [ ] **Step 1: Update `docs/GUIDE.md`:** the page now has Live, Console and Settings tabs; the OBS dock section points at `/dock`; add short sections for the queue (remove, clear), the console (filters, debug toggle, outcomes and what each means), the voice picker, and the tray-equivalent controls on the page including Quit.
- [ ] **Step 2: Update `README.md`:** new endpoints, the event log privacy note (chat text in memory only), the new test count, and remove references to the separate pages.
- [ ] **Step 3: Run the full fast suite,** then commit `docs: control center`.

---

## Self-review notes

- Spec coverage: event log and mirror (T1), skip reasons (T2), queue ids/snapshot/remove/clear/events (T3), controller outcomes (T4), endpoints incl. quit/toggle/voices (T5), wiring, voices grouping, debug toggle (T6), shell, routing, responsive rules (T7), Live (T8), Console (T9), Settings, voice picker, collapsible sections, old pages removed (T10), docs (T11).
- Plan extends the spec's outcome list with `skipped` (user pressed Skip) and `removed` (queue edits), because the player must report them; both are recorded as chat events.
- Task 5 uses keyword-only optional dependencies on `create_app` instead of a new parameter object, so the existing server tests keep their calls.
- JS behavior cannot be unit-tested in this project; each UI task pairs a markup test with a browser-pane check against a scratch fake server (kept in the scratchpad, not committed), and the XSS guard is a source-level test.
- Manual checks stay with the author: the page as a real OBS dock, sending real chat messages through the console, and CPU while gaming.

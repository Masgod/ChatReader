# Themed Chat Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A second OBS Browser Source, `/chat-overlay`, that shows a themed speech bubble for each chat message when the voice starts reading it, fed by a read-only multi-client event stream `/ws/view`.

**Architecture:** The Player tells a new `ViewHub` when an item starts and ends; `ViewHub` broadcasts JSON to every `/ws/view` client. Themes are folders (plus a built-in `default`) validated by a new `themes.py` and served from `/themes/...`. The page is plain HTML/JS/CSS with no build step.

**Tech Stack:** Python 3.11, FastAPI/uvicorn websockets, tomllib, pytest, vanilla JS. Run tests with `uv run pytest -q -m "not slow"`.

**Spec:** `docs/superpowers/specs/2026-10-27-chat-overlay-design.md` (phases 1 and 2 only; emote images and the guides are later plans).

**Branch:** work on `feat/chat-overlay` created from `main`.

## Global Constraints

- Tests first for every code change; watch each new test fail before implementing.
- The web pages have no build step. Chat text and theme text reach the DOM only through `textContent` / `setAttribute`, never `innerHTML`.
- `/ws/view`, `/themes/...`, `/chat-overlay` and the new `/api/...` routes sit behind the existing `LocalOnly` middleware.
- `/overlay` and `/ws` (audio) behave exactly as before.
- New `Config` keys are validated in `validate()`, appear in `config.example.toml` and `docs/CONFIGURATION.md`, and are accepted by the existing `PUT /api/config` type check.
- Commit style `feat:` / `fix:` / `docs:`; end every commit message with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- No Valve or other third-party artwork in the repo, tests or zip.

## Review Focus

Failure modes the spec implies; each has a test in the named task.

1. Hostile theme folders (a `..` path, a symlink out of the folder, an oversized file, bad TOML, a script extension) are rejected and never served (Task 5).
2. Chat text containing HTML renders as literal text: the sample bubble text is `<b>hi</b> & <img src=x>` and must show as typed (Task 6, manual).
3. A ninth `/ws/view` client is refused, a dead client is dropped, and a broadcast with no client is a no-op (Task 2).
4. An item that is skipped, removed or dropped before its audio starts produces no bubble; a started item that is skipped produces an `end` with `skipped` (Tasks 1 and 2).
5. A selected theme that is deleted or invalid falls back to `default` with a warning, and the overlay still draws bubbles (Task 5).

## File Structure

- Modify `src/chatreader/voices.py`, `player.py`, `controller.py`, `config.py`, `server.py`, `main.py`; modify web `app.html`, `settings.js`, `app.css`.
- Create `src/chatreader/themes.py`, `src/chatreader/web/chat-overlay.html`, `chat-overlay.js`, `chat-overlay.css`, `src/chatreader/web/themes/default/theme.toml`.
- Create tests `tests/test_view.py`, `tests/test_themes.py`; extend `test_player.py`, `test_controller.py`, `test_config.py`, `test_server.py`, `test_voices.py`.

---

### Task 1: Stable slot and Player start hook

**Files:**
- Modify: `src/chatreader/voices.py`, `src/chatreader/player.py`
- Test: `tests/test_voices.py`, `tests/test_player.py`

**Interfaces:**
- Produces: `voices.slot_for(platform: str, user: str) -> int` (first 4 bytes of `sha256(f"{platform}:{user.lower()}")` as big-endian int, 0 to 2**32-1).
- Produces: `QueueItem.view: dict | None = None`; `Player.submit(text, lang, user="", voice="", view=None)`; `Player(synth, output, maxsize, on_event=None, on_start=None)` where `on_start(item: QueueItem) -> None` is called once per item, outside the lock, just before the first `output.play(wav)` of that item.

- [ ] **Step 1: Write failing tests**
  - `test_voices.py::test_slot_is_stable_case_insensitive_and_platform_specific`: `slot_for("twitch","Ana") == slot_for("twitch","ana")`, differs from `slot_for("youtube","Ana")`, and `0 <= slot < 2**32`.
  - `test_player.py::test_on_start_fires_once_before_first_play_with_the_item_view`: a recording output and a two-sentence text; assert `on_start` ran once, before the first `play`, and the item carried `view={"user":"a"}`.
  - `test_on_start_not_called_when_every_sentence_fails_synthesis`: synth returns `None`; assert zero calls and outcome `failed`.
  - `test_on_start_not_called_for_an_item_skipped_before_audio`: skip during synthesis (use the existing `gated` stub pattern); assert zero calls.
  - `test_failing_on_start_does_not_stop_playback`: `on_start` raises; the clip still plays and outcome is `played`.
  - `test_submit_without_view_keeps_view_none`.
- [ ] **Step 2: Run** `uv run pytest -q tests/test_voices.py tests/test_player.py` — Expected: the new tests FAIL (missing `slot_for`, `on_start`, `view`).
- [ ] **Step 3: Implement** `slot_for` in `voices.py` (reuse the same digest input as `voice_for`). In `player.py` add the `view` field to `QueueItem`, the `view` parameter to `submit`, the `on_start` constructor argument, and in `_play_item` a local `started` flag that calls a `_start(item)` helper (same try/except-and-log isolation as `_emit`) immediately before the first `self._output.play(wav)`.
- [ ] **Step 4: Run** the same command plus `uv run pytest -q -m "not slow"` — Expected: all pass (update any existing stub `submit` signatures in tests to accept `view=None`).
- [ ] **Step 5: Commit** `git commit -m "feat: stable viewer slot and player start hook"`.

---

### Task 2: ViewHub and `/ws/view`

**Files:**
- Modify: `src/chatreader/server.py`
- Test: `tests/test_view.py` (new)

**Interfaces:**
- Consumes: `QueueItem` with `.id` and `.view` (Task 1).
- Produces in `server.py`: `class ViewHub` with `MAX_CLIENTS = 8`, `client_count` property, `async serve(ws)`, `broadcast(payload: dict) -> None` (thread-safe, fire-and-forget, 1 s send timeout per client, drops clients that fail), `on_start(item)`, `on_event(item, outcome)`.
- Behavior: `serve` refuses the ninth client by closing with code 1013 before accepting; accepted clients get `{"t":"hello","v":1}` first and their incoming messages are ignored. `on_start` does nothing when `item.view is None`; otherwise remembers `item.id` and broadcasts `{"t":"start","id":item.id, **item.view}`. `on_event` for a remembered id with outcome in `played`, `failed`, `skipped` forgets it and broadcasts `{"t":"end","id":...,"outcome":...}`; any other outcome forgets the id silently; ids never started are ignored.
- Produces: `create_app(..., view: ViewHub | None = None, ...)` adds route `@app.websocket("/ws/view")` that calls `view.serve(ws)` when `view` is given.

- [ ] **Step 1: Write failing tests** in `tests/test_view.py`, using `TestClient(app, base_url="http://127.0.0.1")` and `websocket_connect("/ws/view")`:
  - `test_hello_frame_on_connect`.
  - `test_broadcast_reaches_every_client`: two clients both receive `{"t":"config"}`.
  - `test_broadcast_with_no_clients_is_a_noop`.
  - `test_ninth_client_is_refused`: eight stay open, the ninth connection raises on connect.
  - `test_dead_client_is_dropped`: close one client, broadcast, `client_count` falls and the other still receives.
  - `test_on_start_and_on_event_send_start_then_end`: build a `SimpleNamespace(id=7, view={"user":"a","text":"oi","kind":"chat"})`; expect the start frame has `t,id,user,text,kind`, then `played` yields `end` with `outcome="played"`.
  - `test_item_without_view_sends_nothing`; `test_removed_or_dropped_item_never_sends_end`; `test_end_without_start_is_ignored`; `test_skipped_started_item_sends_end_skipped`.
  - `test_client_messages_are_ignored` (client sends text, connection stays open).
- [ ] **Step 2: Run** `uv run pytest -q tests/test_view.py` — Expected: FAIL (no `ViewHub`).
- [ ] **Step 3: Implement** `ViewHub` and the route. Capture the running loop in `serve` (as `Hub` does); `broadcast` schedules `ws.send_text(json.dumps(payload))` for each client with `asyncio.run_coroutine_threadsafe(..., loop).result(1)` inside a try, removing the client on any exception. Add `view=None` to `create_app`.
- [ ] **Step 4: Run** `uv run pytest -q -m "not slow"` — Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "feat: view hub and /ws/view event stream"`.

---

### Task 3: Controller view payload and app wiring

**Files:**
- Modify: `src/chatreader/controller.py`, `src/chatreader/main.py`
- Test: `tests/test_controller.py`, `tests/test_main.py`

**Interfaces:**
- Consumes: `slot_for`, `Player.submit(..., view=)` (Task 1), `ViewHub` (Task 2).
- Produces: `Controller.on_msg` passes `view={"platform","user","text","kind","detail","slot","lang"}` where `text` is the filtered `msg.text` (not the spoken sentence), `slot=slot_for(msg.platform, msg.user)`.
- Produces: `make_apply(controller, path, set_startup, save=save_config, on_saved=None)`; after a successful save it calls `on_saved()` (errors in `on_saved` are logged, never raised).
- Produces in `main.py`: one `ViewHub`; `Player(..., on_event=<calls controller.record_item_event then view.on_event>, on_start=view.on_start)`; `create_app(..., view=view, themes_dir=app / "themes")` (the `themes_dir` kwarg lands in Task 5; pass it there); `make_apply(..., on_saved=lambda: view.broadcast({"t": "config"}))`.

- [ ] **Step 1: Write failing tests**
  - `test_controller.py::test_view_payload_has_the_display_fields`: update `FakePlayer.submit(self, text, lang, user="", voice="", view=None)` to store `view`; send a chat `Msg` and an event `Msg(kind="bits", detail="100")`; assert the payload keys, `text` equals the message text (not "disse:"), `slot == slot_for(...)`, `lang` equals the detected language.
  - `test_speak_test_has_no_view`.
  - `test_main.py::test_make_apply_calls_on_saved_after_save` and `test_make_apply_survives_a_failing_on_saved`.
- [ ] **Step 2: Run** `uv run pytest -q tests/test_controller.py tests/test_main.py` — Expected: FAIL.
- [ ] **Step 3: Implement** the payload in `on_msg` and the `on_saved` hook; wire `main.py` as described (the `on_event` combiner must isolate exceptions from `view.on_event` so `record_item_event` always runs).
- [ ] **Step 4: Run** `uv run pytest -q -m "not slow"` — Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "feat: controller sends display payload and app wires the view hub"`.

---

### Task 4: Overlay config keys

**Files:**
- Modify: `src/chatreader/config.py`, `config.example.toml`, `docs/CONFIGURATION.md`
- Test: `tests/test_config.py`, `tests/test_config_keys.py`

**Interfaces:**
- Produces in `config.py`: `OVERLAY_POSITIONS = ["top-left","top-right","middle-left","middle-right","bottom-left","bottom-right"]`, `THEME_NAME_RE = re.compile(r"[A-Za-z0-9_-]{1,40}")`; `Config.overlay_theme: str = "default"`, `overlay_position: str = "bottom-left"`, `overlay_max_bubbles: int = 4`, `overlay_hold_seconds: int = 4`.
- Validation messages: `overlay_theme must be 1-40 letters, digits, - or _`; `overlay_position must be one of ...`; `overlay_max_bubbles must be between 1 and 10`; `overlay_hold_seconds must be between 0 and 30`.

- [ ] **Step 1: Write failing tests**: parametrized validity for each key (`overlay_max_bubbles` 0/1/10/11, `overlay_hold_seconds` -1/0/30/31, `overlay_position` valid and `"center"`, `overlay_theme` `"a b"`, `"../x"`, `""`, `"deadlock_2"`); `load_config` keeps defaults when the keys are missing from an old file; the PUT type check rejects a string for `overlay_max_bubbles`.
- [ ] **Step 2: Run** `uv run pytest -q tests/test_config.py tests/test_config_keys.py` — Expected: FAIL.
- [ ] **Step 3: Implement** the fields and validation; add the four keys with comments to `config.example.toml` and rows to `docs/CONFIGURATION.md`.
- [ ] **Step 4: Run** `uv run pytest -q -m "not slow"` — Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "feat: overlay settings keys"`.

---

### Task 5: Themes (loader, validation, serving, API)

**Files:**
- Create: `src/chatreader/themes.py`, `src/chatreader/web/themes/default/theme.toml`
- Modify: `src/chatreader/server.py`
- Test: `tests/test_themes.py` (new), `tests/test_server.py`

**Interfaces:**
- Consumes: `THEME_NAME_RE`, `Config.overlay_*` (Task 4).
- Produces in `themes.py`:
  - `class ThemeError(Exception)`.
  - `load_theme(folder: Path, name: str) -> dict`: returns the manifest `{"name","author","font"(url|None),"bubble":{"background","color","radius","animation"},"events":{"background","color"},"heroes":[{"name","images":{expression: url}}],"expressions":[{"name","chance"}],"fallback"}` or raises `ThemeError(message)`. URLs have the form `/themes/<name>/heroes/<hero>/<expression>.<ext>`; heroes are sorted by folder name; a hero's `images` lists the expression files it has.
  - `list_themes(user_dir: Path | None) -> list[dict]`: `[{"name","title","valid":bool,"error":str|None}]`, the built-in `default` first, then user folders sorted; a user folder named `default` is reported invalid.
  - `resolve_file(user_dir: Path | None, name: str, rel: str) -> Path | None`: the file to serve or `None`.
  - Rules: the extension must be one of `png jpg jpeg webp gif svg woff2 otf ttf` (plus `toml` is never served); the resolved path (symlinks followed) must stay inside the theme folder; the name must match `THEME_NAME_RE`; the built-in theme is read from the packaged `web/themes/default` folder.
  - Validation: valid TOML; `bubble.animation` in `fade slide snap none`; colors match `#rgb` or `#rrggbb`; `radius` 0 to 40; expression chances 0 to 1 and summing to at most 1; `fallback` names a listed expression; at most 200 image files; no file over 5 MB; `font` (if set) points inside `fonts/` with an allowed extension and exists.
- Produces routes in `create_app(..., themes_dir: Path | None = None)`: `GET /themes/{name}/{path:path}` (404 when `resolve_file` is `None`, correct media type otherwise), `GET /api/themes` (the `list_themes` result), `GET /api/overlay` returning `{"config": {overlay_theme, overlay_position, overlay_max_bubbles, overlay_hold_seconds}, "theme": <manifest>, "warning": str | None}` which falls back to the `default` manifest with a warning text when the selected theme is missing or invalid.

- [ ] **Step 1: Write failing tests** in `tests/test_themes.py` using `tmp_path` folders: valid theme with two heroes and expressions loads with sorted heroes and the right URLs; each invalid case in "Validation" raises `ThemeError` with a useful message (parametrize); `default` is valid; a user folder named `default` is listed invalid; `resolve_file` returns `None` for `../theme.toml`, for an absolute path, for `theme.toml`, for `x.exe`, for an oversized-extension case, and for a symlink pointing outside (skip this one cleanly when the OS refuses to create symlinks); serves a normal png. In `tests/test_server.py`: `/themes/default/...` of an allowed file 200 with `image/...`, a traversal attempt 404, `/api/themes` lists default, `/api/overlay` returns the default manifest, and an unknown `overlay_theme` returns the default manifest plus a non-empty `warning`.
- [ ] **Step 2: Run** `uv run pytest -q tests/test_themes.py tests/test_server.py` — Expected: FAIL.
- [ ] **Step 3: Implement** `themes.py`, the built-in `theme.toml` (own palette: dark purple bubble `#1f1b2e` with `#f4f1ff` text, radius 12, animation `slide`, events `#4b2a86` / `#ffffff`, no heroes), and the routes.
- [ ] **Step 4: Run** `uv run pytest -q -m "not slow"` — Expected: PASS. Also confirm `packaging/chatreader.spec` already bundles the whole `web` folder (it does: `(root/"src"/"chatreader"/"web", "chatreader/web")`); no spec change.
- [ ] **Step 5: Commit** `git commit -m "feat: theme loader, validation and serving"`.

---

### Task 6: The `/chat-overlay` page and test bubble

**Files:**
- Create: `src/chatreader/web/chat-overlay.html`, `chat-overlay.js`, `chat-overlay.css`
- Modify: `src/chatreader/server.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `/ws/view` frames (Task 2), `/api/overlay` and `/themes/...` (Task 5).
- Produces: `GET /chat-overlay` (HTML), static entries `chat-overlay.js` (`text/javascript`) and `chat-overlay.css` (`text/css`) in `_STATIC`; `POST /api/view-test` (JSON body, `LocalOnly` rules apply) that broadcasts `{"t":"start","id":0,"platform":"twitch","user":"Preview","text":"<b>hi</b> & <img src=x>","kind":"chat","detail":"","slot":<any int>,"lang":"en"}` immediately and `{"t":"end","id":0,"outcome":"played"}` after `server.TEST_BUBBLE_SECONDS` (module constant, 3.0).

- [ ] **Step 1: Write failing tests**: `/chat-overlay` returns 200 HTML containing `/static/chat-overlay.js`; both static files are served with the right types; the HTML and JS contain no `innerHTML` (read the files and assert); `POST /api/view-test` with a connected `/ws/view` client delivers the start frame (text exactly `<b>hi</b> & <img src=x>`) and then the end frame (set `server.TEST_BUBBLE_SECONDS = 0.05` with `monkeypatch`); a POST with a non-JSON content type is rejected 403 by `LocalOnly`.
- [ ] **Step 2: Run** `uv run pytest -q tests/test_server.py` — Expected: FAIL.
- [ ] **Step 3: Implement** the routes and the page. Page behavior (all in `chat-overlay.js`): connect to `ws://<host>/ws/view`, reconnect every 2 s; on `hello` and `config` fetch `/api/overlay` and apply `overlay_position` (CSS class on the container), apply theme CSS custom properties and the animation class, and register the theme font through a `FontFace` from its URL; on `start` create the bubble with `textContent` only (hero = `heroes[slot % heroes.length]`, expression chosen by rolling against the chances, falling back to `fallback` and then to the initial circle when the image is missing or errors), add the speaking class, enforce `overlay_max_bubbles` by removing the oldest first; on `end` remove the speaking class and remove the bubble after `overlay_hold_seconds` (immediately for `skipped`) with the exit animation; `kind != "chat"` bubbles use the events colors and show a one-line event description built client-side (`bits`, `subs`, `gifts`, `raids`, `superchat`, `members` plus `detail`); `prefers-reduced-motion` forces `fade`. The page background is transparent and long words use `overflow-wrap: anywhere`, bubble max width 300 px.
- [ ] **Step 4: Run** `uv run pytest -q -m "not slow"` — Expected: PASS. **Manual check** (cannot be automated): run the app from source, open `/chat-overlay` in the Browser pane, press the test endpoint (`fetch('/api/view-test',{method:'POST',headers:{'content-type':'application/json'},body:'{}'})` in the console) and confirm the bubble shows `<b>hi</b> & <img src=x>` literally, animates in, and leaves after the hold time.
- [ ] **Step 5: Commit** `git commit -m "feat: chat overlay page and test bubble"`.

---

### Task 7: Settings section and docs

**Files:**
- Modify: `src/chatreader/web/app.html`, `settings.js`, `app.css`, `docs/GUIDE.md`, `docs/STATUS.md`, `README.md`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `/api/themes`, `/api/overlay`, `/api/view-test`, the new config keys.
- Produces: an "Overlay" `<details class="sect">` in the settings panel containing: a theme `<select id="overlay_theme" data-key="overlay_theme">` filled from `/api/themes` (invalid themes shown disabled with the error text as the option label suffix); six position buttons in a `role="group"` using a new `data-choice="overlay_position"` plus `data-value` attribute pair handled in `settings.js` the same way `data-lang` is; two steppers `data-num="overlay_max_bubbles"` (1 to 10, step 1) and `data-num="overlay_hold_seconds"` (0 to 30, step 1) with the same markup as the existing steppers; a read-only URL field showing `http://127.0.0.1:<port>/chat-overlay` with a Copy button (falls back to selecting the text when the clipboard call is refused); a **Test bubble** button that POSTs `/api/view-test`.

- [ ] **Step 1: Write failing tests** in `tests/test_server.py`: the settings HTML served at `/` contains `data-key="overlay_theme"`, `data-choice="overlay_position"` six times, `data-num="overlay_max_bubbles"` and `data-num="overlay_hold_seconds"`, and an element with id `test-bubble`; `settings.js` contains no `innerHTML`.
- [ ] **Step 2: Run** `uv run pytest -q tests/test_server.py` — Expected: FAIL.
- [ ] **Step 3: Implement** the markup, the `settings.js` handlers (populate themes on load and when the tab opens, `data-choice` toggling feeding `state`, URL/Copy/Test wiring, all text via `textContent`) and minimal CSS reusing existing classes.
- [ ] **Step 4: Run** `uv run pytest -q -m "not slow"` — Expected: PASS.
- [ ] **Step 5: Docs.** In `docs/GUIDE.md` add an "Overlay" section (OBS Browser Source with `http://127.0.0.1:8765/chat-overlay`, size 450 x 600, transparent, a separate source from the audio one; the audio source is still required) and a short "Themes" section stating the folder format and that third-party artwork is the user's responsibility (the full "Make a theme" and Deadlock guides are a later plan). Update `docs/STATUS.md` roadmap (remove the text overlay, keep emotes-as-images and the guides), add a feature bullet to `README.md`, and update the test count.
- [ ] **Step 6: Manual verification** (state it in the final message, do not claim it automated): in OBS, Twitch and YouTube chat each produce a bubble when the voice starts and none for filtered messages.
- [ ] **Step 7: Commit** `git commit -m "feat: overlay settings and docs"`.

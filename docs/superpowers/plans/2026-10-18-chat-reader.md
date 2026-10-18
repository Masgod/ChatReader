# Chat Reader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Windows tray app that reads every Twitch and YouTube live chat message aloud (pt-BR and English) with local Piper TTS, played through an OBS Browser Source.

**Architecture:** One Python process. Source threads push `Msg` into a pipeline (filter, language detect, spoken text) feeding one bounded queue with a single TTS worker. A FastAPI server bound to localhost serves the overlay page (audio over WebSocket), the settings page and a config API. A pystray icon controls Pause/Skip/Settings/Quit.

**Tech Stack:** Python 3.11+, uv, piper-tts, lingua-language-detector, pytchat, websockets, fastapi, uvicorn, pystray, Pillow, tomli-w, pytest.

**Spec:** `docs/superpowers/specs/2026-10-18-chat-reader-design.md`

## Global Constraints

- Windows 11, Python >= 3.11 (uses `tomllib`); managed with `uv`; package `chatreader` under `src/chatreader/`.
- TTS is Piper on CPU only, with exactly one TTS worker thread.
- Server binds to `127.0.0.1` only; default port `8765`; no secrets stored in v1.
- Language detection is `lingua` restricted to Portuguese and English; low confidence or very short text (< 12 chars) uses `default_lang`.
- Spoken text: pt `"{user} disse: {text}"`, en `"{user} says: {text}"`, or just `{text}` when `announce_user` is false.
- Filter order: bots/ignored users, `!commands`, links, repeats from same user, emote spam, truncation to `max_chars`.
- Queue: bounded, default 20, drop the oldest waiting message when full.
- Overlay playback timeout: audio length + 2 s. Source reconnect backoff: 1 s doubling up to 30 s.
- Errors never crash the app: a failed message or source is logged and skipped. Rotating log file in the app folder, errors only unless `debug`.
- Out of scope: Kokoro/Chatterbox, per-user voices, queue viewer, extra moderation, multiple channels, message history.
- App folder = env `CHATREADER_HOME` if set, else the current working directory. `config.toml`, `voices/` and the log live there.

## Review Focus

1. Empty, whitespace-only or emoji-only message: dropped by filters, never reaches Piper. (Task 2)
2. Usernames like `xX_Gamer_Xx` or `João`: underscores read as spaces, non-ASCII kept. (Task 3)
3. Burst of 100 messages in one second: queue stays at its cap and keeps the newest. (Task 4)
4. Pasted `https://youtu.be/<id>` or `watch?v=<id>`, `#Channel` or mixed-case Twitch name: normalized instead of rejected. (Task 1)
5. `PUT /api/config` with missing fields, wrong types or an empty channel: bad input returns 422 and keeps the old config; an empty channel just disables that source. (Task 8)

---

### Task 1: Scaffold, `Msg` and config

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `config.example.toml`, `src/chatreader/__init__.py`, `src/chatreader/__main__.py` (calls `main.main()`, added in Task 10), `src/chatreader/models.py`, `src/chatreader/config.py`, `tests/test_config.py`

**Interfaces:**
- Produces:
  - `models.Msg`: frozen dataclass `(platform: str, user: str, text: str, ts: float)`.
  - `config.Config`: dataclass with defaults `twitch_channel=""`, `youtube_video_id=""`, `voice_pt="pt_BR-faber-medium"`, `voice_en="en_US-lessac-medium"`, `default_lang="pt"`, `queue_size=20`, `max_chars=200`, `announce_user=True`, `port=8765`, `start_with_windows=False`, `ignored_users=["nightbot","streamelements","streamlabs","moobot"]`, `repeat_window=5`, `debug=False`.
  - `config.load_config(path: Path) -> Config`: missing file creates it from defaults; corrupt file is renamed to `config.toml.bad` and defaults load.
  - `config.save_config(path: Path, cfg: Config) -> None`.
  - `config.normalize(cfg: Config) -> Config`: lowercases/strips `#` from `twitch_channel`; extracts the 11-char ID from YouTube URLs.
  - `config.validate(cfg: Config) -> list[str]`: error messages; Twitch `^[a-z0-9_]{3,25}$` or empty, YouTube `^[A-Za-z0-9_-]{11}$` or empty, `queue_size >= 1`, `1 <= port <= 65535`, `default_lang in ("pt","en")`.

- [ ] **Step 1: Scaffold.** `uv init --lib` equivalents by hand: `pyproject.toml` with the Tech Stack deps, dev dep `pytest`, `requires-python = ">=3.11"`, `[project.scripts] chatreader = "chatreader.main:main"`, `testpaths = ["tests"]`. `.gitignore`: `.venv/`, `voices/`, `config.toml`, `config.toml.bad`, `*.log`, `__pycache__/`. Run `uv sync` and confirm it succeeds.
- [ ] **Step 2: Write failing tests** in `tests/test_config.py` (use `tmp_path`):
  - `test_missing_file_creates_defaults`: file exists afterwards and equals `Config()`.
  - `test_roundtrip`: `save_config` then `load_config` returns an equal `Config`.
  - `test_corrupt_file_renamed_and_defaults`: garbage content, afterwards `config.toml.bad` exists and result equals `Config()`.
  - `test_normalize_twitch`: `"#SomeChannel"` becomes `"somechannel"`.
  - `test_normalize_youtube_urls`: `https://youtu.be/dQw4w9WgXcQ`, `https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=5` and the bare ID all become `"dQw4w9WgXcQ"`.
  - `test_validate_rejects_bad_values`: channel `"a b"`, video ID `"short"`, `queue_size=0`, `port=70000` each give a non-empty error list; `Config()` gives `[]`.
- [ ] **Step 3: Run** `uv run pytest tests/test_config.py -v`. Expected: FAIL (module missing).
- [ ] **Step 4: Implement** `models.py` and `config.py` as specified. Read with `tomllib`, write with `tomli_w`; unknown keys in the file are ignored.
- [ ] **Step 5: Run** the same command. Expected: all PASS.
- [ ] **Step 6: Write `config.example.toml`** with the defaults and a comment per key; commit: `git add . && git commit -m "feat: scaffold, Msg and config"`.

### Task 2: Filters

**Files:** Create `src/chatreader/filters.py`, `tests/test_filters.py`

**Interfaces:**
- Consumes: `Msg`, `Config`.
- Produces: `filters.FilterState` (holds recent texts per user, size `cfg.repeat_window`); `filters.apply(msg: Msg, cfg: Config, state: FilterState) -> Msg | None`. Returns the message with `text` stripped/truncated, or `None` when dropped.

- [ ] **Step 1: Write failing tests** (table-driven with `pytest.mark.parametrize`, helper `m(text, user="alice")`):
  - Dropped: user `"Nightbot"` (case-insensitive, via `ignored_users`); `"!so someone"`; `"look https://x.com"`; `"www.example.com"`; `"   "`; `""`; emoji-only `"😂😂😂"`; the same text from the same user twice in a row (second only); `"Kappa Kappa Kappa Kappa Kappa"`; `"aaaaaaaaaaaaaaaa"` (a char repeated >= 10 times in a row).
  - Kept: `"oi pessoal"`, `"Kappa nice play"`.
  - `test_truncates_to_max_chars`: 500-char text with `max_chars=200` gives `len(result.text) <= 200`.
  - `test_rule_order`: a `!command` from an ignored user is dropped without being recorded as a repeat (state unchanged).
- [ ] **Step 2: Run** `uv run pytest tests/test_filters.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `apply` following the Global Constraints order. Emote spam: >= 4 tokens where one token is >= 60% of them. "Emoji-only/no letters or digits" means no `str.isalnum()` character anywhere in the text. Truncate at a word boundary when possible.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit:** `git commit -am "feat: message filters"` (after `git add`).

### Task 3: Language detection and spoken text

**Files:** Create `src/chatreader/lang.py`, `tests/test_lang.py`

**Interfaces:**
- Consumes: `Msg`.
- Produces: `lang.detect_lang(text: str, default: str) -> str` (`"pt"` or `"en"`); `lang.spoken_text(msg: Msg, lang: str, announce: bool) -> str`.

- [ ] **Step 1: Write failing tests:**
  - `test_detects_pt`: `"eu gostei muito dessa jogada, muito boa"` gives `"pt"`; `test_detects_en`: `"that was an amazing play, well done"` gives `"en"`.
  - `test_short_text_uses_default`: `detect_lang("ok", "en") == "en"` and `detect_lang("ok", "pt") == "pt"`.
  - `test_spoken_text_announce`: `Msg("twitch","alice","oi",0)` with `"pt", True` gives `"alice disse: oi"`; with `"en", True` gives `"alice says: oi"`; announce False gives `"oi"`.
  - `test_username_underscores_become_spaces`: user `"xX_Gamer_Xx"` yields `"xX Gamer Xx disse: oi"`; `"João"` is kept unchanged.
- [ ] **Step 2: Run** `uv run pytest tests/test_lang.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** Build the `lingua` detector once at module level with `LanguageDetectorBuilder.from_languages(PORTUGUESE, ENGLISH)`; use `compute_language_confidence`; confidence below 0.7 or `len(text.strip()) < 12` returns `default`.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit:** `feat: language detection and spoken text`.

### Task 4: Player (queue, worker, skip, pause)

**Files:** Create `src/chatreader/player.py`, `tests/test_player.py`

**Interfaces:**
- Produces:
  - `player.Output` (Protocol): `play(wav: bytes) -> None` (blocks until finished, timed out or stopped), `stop() -> None`.
  - `player.Player(synth: Callable[[str, str], bytes], output: Output, maxsize: int)` with `submit(text: str, lang: str) -> None`, `pause()`, `resume()`, `skip()`, `start()`, `shutdown()`, properties `paused: bool` and `pending: int`.
  - `skip()` calls `output.stop()`; the worker then continues with the next item.

- [ ] **Step 1: Write failing tests** using a fake `Output` that records calls and a `synth` returning `text.encode()`; wait with `threading.Event`, never `sleep` guesses over 2 s:
  - `test_plays_in_order`: three submissions play in order, one at a time.
  - `test_drops_oldest_when_full`: with the worker paused and `maxsize=3`, submitting 5 leaves `pending == 3` and, after `resume()`, the played items are the last 3.
  - `test_burst_of_100_keeps_cap_and_newest`: `maxsize=20`, 100 submissions while paused; `pending == 20`; the last played is item 99.
  - `test_pause_holds_items`: while paused nothing plays; after `resume()` it does.
  - `test_skip_calls_output_stop`: `skip()` during a blocking `play` calls `stop()` and the next item then plays.
  - `test_synth_error_skips_message`: `synth` raising on one item does not stop later items.
  - `test_output_error_skips_message`: `play` raising is logged and the worker continues.
- [ ] **Step 2: Run** `uv run pytest tests/test_player.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** `collections.deque` guarded by a `threading.Condition`; one daemon worker thread; log exceptions with `logging.getLogger(__name__).exception`.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit:** `feat: queue player`.

### Task 5: Piper TTS and voice download

**Files:** Create `src/chatreader/tts.py`, `tests/test_tts.py`

**Interfaces:**
- Consumes: `Config`.
- Produces: `tts.voice_urls(name: str) -> tuple[str, str]` (the `.onnx` and `.onnx.json` URLs on `https://huggingface.co/rhasspy/piper-voices/resolve/main/<lang>/<locale>/<speaker>/<quality>/<name>.onnx[.json]`); `tts.ensure_voices(voices_dir: Path, names: list[str], download=urllib-based default) -> list[str]` (returns names that could not be obtained); `tts.PiperTTS(voices_dir: Path, cfg: Config, on_warning: Callable[[str], None])` with `synth(text: str, lang: str) -> bytes` (WAV bytes) and `reload(cfg: Config) -> None`.

- [ ] **Step 1: Check the installed Piper API.** Run `uv run python -c "import piper; print(piper.__version__ if hasattr(piper,'__version__') else piper)"` and read how `PiperVoice.load` and the synthesize-to-WAV call are named in the installed version; use those names. If `piper-tts` fails to install on this Python version, stop and report it.
- [ ] **Step 2: Write failing tests:**
  - `test_voice_urls`: `voice_urls("pt_BR-faber-medium")` returns `.../pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx` and the `.json` twin.
  - `test_ensure_voices_skips_existing_and_reports_failures`: with a fake `download` that fails for one name, existing files are not re-downloaded and the failed name is returned.
  - `test_synth_falls_back_to_other_voice`: with only the English voice loaded (fake loader), `synth("oi","pt")` uses it and calls `on_warning` once.
  - Slow, marked `@pytest.mark.slow`, runs only when voices exist in `./voices`: `test_real_piper_returns_wav` checks the result starts with `b"RIFF"` and is longer than 1000 bytes.
- [ ] **Step 3: Run** `uv run pytest tests/test_tts.py -v -m "not slow"`. Expected: FAIL.
- [ ] **Step 4: Implement.** Inject the voice loader and downloader so tests need no network or model files. Register the `slow` marker in `pyproject.toml`.
- [ ] **Step 5: Run** the same command. Expected: PASS. Then download the two default voices (`uv run python -c "from chatreader.tts import ensure_voices; ..."`), read both voices' model cards on Hugging Face for the license, and note the license of each in `README.md` (Task 11). If a license forbids use on a monetized stream, stop and ask the user. Run the slow test.
- [ ] **Step 6: Commit:** `feat: piper tts and voice download`.

### Task 6: Source runner and Twitch

**Files:** Create `src/chatreader/sources/__init__.py`, `src/chatreader/sources/common.py`, `src/chatreader/sources/twitch.py`, `tests/test_sources.py`

**Interfaces:**
- Consumes: `Msg`.
- Produces:
  - `common.run_with_backoff(fn: Callable[[], None], stop: threading.Event, on_status: Callable[[str], None], sleep: Callable[[float], None] = stop.wait-based, max_failures: int | None = None) -> None`. Calls `fn` repeatedly; on exception or return, waits 1, 2, 4 ... 30 s; a call to `fn` that delivered at least one message before ending resets the delay to 1 s (`fn` signals this by calling `on_status("connected")`); after `max_failures` consecutive failures calls `on_status("failed")` and returns. Statuses: `"connected"`, `"reconnecting"`, `"failed"`.
  - `twitch.parse_privmsg(line: str) -> Msg | None`: handles tagged lines (`@display-name=Alice;...`) using `display-name`, falls back to the nick; returns `None` for non-PRIVMSG lines.
  - `twitch.run_twitch(channel: str, on_msg: Callable[[Msg], None], stop: threading.Event, on_status: Callable[[str], None]) -> None`: anonymous login (`NICK justinfan<random>`), `CAP REQ :twitch.tv/tags`, `JOIN #channel`, answers `PING` with `PONG`, over `wss://irc-ws.chat.twitch.tv:443` using `websockets.sync.client`, wrapped in `run_with_backoff`.

- [ ] **Step 1: Write failing tests** in `tests/test_sources.py`:
  - `test_parse_privmsg_with_tags`: `"@display-name=Alice;color=#fff :alice!alice@alice.tmi.twitch.tv PRIVMSG #chan :oi pessoal"` gives `Msg("twitch","Alice","oi pessoal", ts)` with `ts > 0`.
  - `test_parse_privmsg_without_tags_uses_nick`; `test_parse_ignores_ping_and_join` returns `None`.
  - `test_parse_message_containing_colons`: text `"oi: tudo bem: sim"` is kept whole.
  - `test_backoff_delays`: fake `sleep` records waits for an `fn` that always raises; the first waits are `[1, 2, 4, 8, 16, 30, 30]`.
  - `test_backoff_resets_after_success`: a success between failures restarts at 1.
  - `test_failed_status_after_max_failures`: `max_failures=3` ends with `on_status("failed")` and the function returns.
  - `test_stop_event_ends_loop`.
- [ ] **Step 2: Run** `uv run pytest tests/test_sources.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** both modules as specified. The socket read loop uses a short `recv` timeout so `stop` is honored within about a second.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit:** `feat: backoff runner and twitch source`.

### Task 7: YouTube source

**Files:** Create `src/chatreader/sources/youtube.py`; add tests to `tests/test_sources.py`

**Interfaces:**
- Consumes: `Msg`, `run_with_backoff`.
- Produces: `youtube.to_msg(item) -> Msg` (item has `.author.name`, `.message`; `ts` from `time.time()`); `youtube.run_youtube(video_id: str, on_msg, stop, on_status, chat_factory=pytchat.create) -> None` using `max_failures=5`. Chat ending (`is_alive()` false) counts as a failure so it retries and eventually reports `"failed"`.

- [ ] **Step 1: Write failing tests** with a fake chat object:
  - `test_to_msg_maps_fields`.
  - `test_run_youtube_delivers_items_then_stops`: fake chat yields two items then the `stop` event is set; `on_msg` got both.
  - `test_chat_ended_reports_failed_after_retries`: fake chat always `is_alive() == False`, fake sleep; ends with `on_status("failed")`.
- [ ] **Step 2: Run** `uv run pytest tests/test_sources.py -v -k youtube`. Expected: FAIL.
- [ ] **Step 3: Implement** `youtube.py` with `pytchat.create(video_id=...)`, loop `while chat.is_alive() and not stop.is_set(): for c in chat.get().sync_items(): on_msg(to_msg(c))`, small `stop.wait(0.5)` between polls.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit:** `feat: youtube source`.

### Task 8: Server, overlay and settings pages

**Files:** Create `src/chatreader/server.py`, `src/chatreader/web/overlay.html`, `src/chatreader/web/settings.html`, `tests/test_server.py`

**Interfaces:**
- Consumes: `Config`, `load_config/save_config/normalize/validate`, `Output` protocol.
- Produces:
  - `server.Hub` implementing `Output`: `play(wav: bytes)` sends bytes to the connected overlay WebSocket and blocks until it replies `"done"`, or `wav_duration + 2` s (duration from the `wave` module), or `stop()`; with no overlay connected `play` returns immediately without waiting (message is consumed). `stop()` sends `"stop"` to the overlay. Property `connected: bool`.
  - `server.create_app(get_config: Callable[[], Config], apply_config: Callable[[Config], None], hub: Hub, speak_test: Callable[[str], None]) -> FastAPI` with routes `GET /overlay`, `GET /settings`, `GET /api/config`, `PUT /api/config`, `POST /api/test` and `WS /ws`.
  - `server.run_server(app: FastAPI, port: int) -> Callable[[], None]`: starts `uvicorn` on `127.0.0.1` in a daemon thread and returns a shutdown function.
- Behavior of `PUT /api/config`: body must contain every `Config` field with the right type, otherwise 422; values are normalized, then validated, errors return 422 with `{"errors": [...]}`; on success calls `apply_config` and returns 200. An empty channel/video ID is valid.

- [ ] **Step 1: Write failing tests** (`fastapi.testclient.TestClient`):
  - `test_get_config_returns_current`; `test_put_valid_config_calls_apply`; `test_put_normalizes_pasted_youtube_url_and_channel`: body has `"#SomeChannel"` and a youtu.be URL, `apply_config` receives `somechannel` and the 11-char ID.
  - `test_put_invalid_returns_422_and_keeps_old`: `queue_size=0` returns 422 with an `errors` list and `apply_config` not called.
  - `test_put_missing_fields_or_wrong_types_422`: `{}` and `{"port": "abc"}` return 422.
  - `test_put_empty_channel_is_ok`.
  - `test_overlay_and_settings_pages_served`: 200 and `text/html`.
  - `test_hub_play_waits_for_done`: connect `client.websocket_connect("/ws")`, call `hub.play(wav)` in a thread, receive bytes, send `"done"`, the thread finishes.
  - `test_hub_play_times_out`: tiny silent WAV, a fake clock or a patched timeout constant; no reply still returns.
  - `test_hub_play_without_overlay_returns_immediately`.
  - `test_post_test_calls_speak_test`.
- [ ] **Step 2: Run** `uv run pytest tests/test_server.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `server.py`. The Hub keeps the event loop and active WebSocket; the worker thread uses `asyncio.run_coroutine_threadsafe` and a `threading.Event` set by the WS handler on `"done"`. Pages are read from `web/` via `importlib.resources`.
- [ ] **Step 4: Write `overlay.html`:** connects to `ws://<host>/ws`, on binary message plays the audio through an `Audio` element created from a Blob, sends `"done"` on `ended`/`error`, stops and sends `"done"` on a `"stop"` text message, reconnects every 2 s if closed. No visible UI.
- [ ] **Step 5: Write `settings.html`:** a form with one field per `Config` field, loads `GET /api/config`, saves with `PUT`, shows the `errors` list, and has a "Test voice" button posting to `/api/test` with a sample sentence in the chosen language.
- [ ] **Step 6: Run** `uv run pytest tests/test_server.py -v`. Expected: PASS.
- [ ] **Step 7: Commit:** `feat: server, overlay and settings pages`.

### Task 9: Controller (pipeline and live reconfiguration)

**Files:** Create `src/chatreader/controller.py`, `tests/test_controller.py`

**Interfaces:**
- Consumes: `Config`, `filters.apply/FilterState`, `lang.detect_lang/spoken_text`, `Player`, source `run_*` functions.
- Produces: `controller.Controller(cfg: Config, player: Player, tts: PiperTTS, source_factories: dict[str, Callable])` with `on_msg(msg: Msg) -> None` (filter, detect, spoken text, `player.submit`), `apply_config(new: Config) -> None` (saves nothing; swaps `cfg`, calls `tts.reload`, resizes the player queue if `queue_size` changed, restarts only the Twitch source when `twitch_channel` changed and only the YouTube source when `youtube_video_id` changed; an empty value stops that source and starts none), `status() -> dict[str, str]` (`{"twitch": ..., "youtube": ..., "overlay": ...}`), `pause()`, `resume()`, `skip()`, `speak_test(text: str)`, `start()`, `shutdown()`.
- `source_factories` maps `"twitch"` and `"youtube"` to `(value, on_msg, stop_event, on_status) -> None` so tests can pass fakes.

- [ ] **Step 1: Write failing tests** with a fake player (records `submit`) and fake factories:
  - `test_on_msg_pipeline`: `Msg("twitch","alice","eu gostei muito dessa jogada",0.0)` reaches `submit("alice disse: eu gostei muito dessa jogada","pt")`.
  - `test_filtered_message_not_submitted`.
  - `test_apply_config_restarts_only_changed_source`: change only the channel, the YouTube fake is not restarted.
  - `test_apply_config_empty_channel_stops_source`.
  - `test_announce_toggle_applies_live`.
  - `test_status_reports_source_states`.
- [ ] **Step 2: Run** `uv run pytest tests/test_controller.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `Controller`. Each source runs in its own daemon thread with its own `threading.Event`; restarting sets the old event and joins briefly. Add `Player.set_maxsize(n: int)` to `player.py` with a test in `tests/test_player.py` (`test_set_maxsize_drops_oldest_when_shrinking`).
- [ ] **Step 4: Run** `uv run pytest -v -m "not slow"`. Expected: PASS.
- [ ] **Step 5: Commit:** `feat: controller pipeline and live reconfiguration`.

### Task 10: Tray, startup shortcut, logging and main

**Files:** Create `src/chatreader/tray.py`, `src/chatreader/startup.py`, `src/chatreader/main.py`, `tests/test_startup.py`

**Interfaces:**
- Consumes: `Controller`, `server.create_app/run_server/Hub`, `config`.
- Produces: `startup.shortcut_path() -> Path` (`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\ChatReader.lnk`); `startup.set_start_with_windows(enabled: bool, app_dir: Path, run=subprocess.run) -> None` (creates the shortcut through a PowerShell `WScript.Shell` command whose target is `pythonw.exe -m chatreader` with `WorkingDirectory` set to `app_dir`, or deletes it); `tray.build_icon(controller, settings_url: str, overlay_url: str, quit_cb) -> pystray.Icon` with menu items Pause/Resume, Skip current, Settings..., Copy overlay URL, Quit and a status tooltip; `main.main() -> None`.

- [ ] **Step 1: Write failing tests** in `tests/test_startup.py` with an injected `run`: enabling calls `run` once with a command string containing `pythonw`, `-m chatreader` and the app dir; disabling removes the file and never calls `run`; `shortcut_path()` ends with `Startup\ChatReader.lnk`.
- [ ] **Step 2: Run** `uv run pytest tests/test_startup.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `startup.py`. Run the test; expected PASS.
- [ ] **Step 4: Implement `main.main()`:** resolve the app folder; set up a `RotatingFileHandler` (1 MB, 3 backups) at `<app>/chatreader.log`, level `ERROR` unless `cfg.debug`; `load_config`; `ensure_voices` and a tray notification for missing ones; build `PiperTTS`, `Hub`, `Player`, `Controller` with the real source factories; wire `apply_config` to also `save_config` and `set_start_with_windows`; start the server (on a bind failure show a tray notification naming the port and exit); open the settings page on first run (config file did not exist); run the tray icon on the main thread; `shutdown` everything on Quit. Write `__main__.py` to call it.
- [ ] **Step 5: Implement `tray.py`:** icon drawn with Pillow (a simple filled circle), Pause and Resume as one toggle item, Copy overlay URL via `subprocess` `clip`, tooltip from `controller.status()` refreshed every few seconds.
- [ ] **Step 6: Run** `uv run pytest -m "not slow" -v`. Expected: all PASS. Launch `uv run python -m chatreader`; expected: a tray icon appears and `http://127.0.0.1:8765/settings` loads.
- [ ] **Step 7: Commit:** `feat: tray app, startup shortcut, logging and main`.

### Task 11: Manual smoke test and README

**Files:** Create `README.md`

- [ ] **Step 1: Write `README.md`:** install (`uv sync`), run (`uv run python -m chatreader`, or `pythonw -m chatreader` for no console), add the overlay URL to OBS as a Browser Source (check "Control audio via OBS"), settings page and tray menu, the voice licenses found in Task 5, and known limits (pytchat can break; Piper pt-BR voices are few).
- [ ] **Step 2: Run the spec's manual checklist** and record pass/fail for each of its 5 items in the README under "Verified": tray icon with no console; settings Test button audible in OBS with its own slider; live Twitch chat and live YouTube chat for a few minutes each; Pause, Skip and Quit; CPU use while a game runs (report the number).
- [ ] **Step 3: Commit:** `docs: README and smoke test results`.

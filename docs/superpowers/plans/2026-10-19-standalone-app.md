# ChatReader Standalone App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship ChatReader as a zipped, windowless Windows app (taskbar icon only) that needs no Python, with a data folder in `%APPDATA%`, registry autostart, single-instance behaviour and a headless self check.

**Architecture:** Small, injectable modules (`paths`, `startup` on `winreg`, `instance`, `selfcheck`) called from `__main__.py`/`main.py`, so each is tested without the OS. A PyInstaller spec and build script in `packaging/` produce the folder build and zip; `--check` proves the bundle works.

**Tech Stack:** Python 3.11+, PyInstaller (dependency group `build`), stdlib `winreg` and `ctypes`, pytest (`uv run pytest -q -m "not slow"`).

**Spec:** `docs/superpowers/specs/2026-10-19-standalone-app-design.md`

## Global Constraints

- Data folder order: `--home` option, `CHATREADER_HOME`, `%APPDATA%\ChatReader` when `sys.frozen`, else the current directory.
- Autostart: value name `ChatReader` under `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`; no PowerShell anywhere in the app after this work; the old Startup-folder `ChatReader.lnk` is removed on enable and on disable.
- Frozen autostart command: the quoted `ChatReader.exe`. Source command: quoted `pythonw.exe` plus `-m chatreader --home "<app_dir>"`.
- Mutex name `Local\ChatReader`. Second launch opens `http://127.0.0.1:<port>/` and exits 0.
- `--check` prints exactly one JSON line to stdout and exits 0 or 1.
- Existing 268 fast tests stay green after every task. No new runtime dependencies; PyInstaller only in the `build` group.
- Model is never bundled or committed. Build outputs (`build/`, `dist/`) are git-ignored.

## Review Focus

1. Paths with spaces, apostrophes and non-ASCII characters in the data folder and the exe path: the autostart command stays one correctly quoted command.
2. `sys.stdout`/`sys.stderr` being `None` (windowless): nothing in startup, logging or the libraries raises.
3. A registry that refuses the write (policy): the settings save reports an error and applies nothing, like the PowerShell path did.
4. Second launch when the first instance is still starting (port not yet listening): the second does not crash and does not open a dead page forever.
5. `--check` with the model missing: still exits 0 if the other steps pass and says the synthesis step was skipped.

---

### Task 1: Data folder, `--home`, windowless streams

**Files:**
- Create: `src/chatreader/paths.py`
- Modify: `src/chatreader/__main__.py`, `src/chatreader/main.py`
- Test: `tests/test_paths.py`

**Interfaces:**
- Produces: `app_dir(home: str | None = None, env=os.environ, frozen: bool | None = None, cwd=os.getcwd) -> Path` (creates the folder when it is the frozen default); `ensure_streams(log_stream) -> None` (replaces `sys.stdout`/`sys.stderr` that are `None`); `parse_args(argv: list[str]) -> argparse.Namespace` with `--home` and `--check`; `main.main(home: str | None = None)`.

- [ ] **Step 1: Write failing tests:** `test_home_option_wins` (option over env over frozen); `test_env_override`; `test_frozen_uses_appdata_and_creates_it` (fake env `APPDATA`, tmp dir; the `ChatReader` folder exists afterwards); `test_plain_run_uses_cwd`; `test_ensure_streams_replaces_none` (monkeypatch `sys.stdout`/`sys.stderr` to `None`, call, then `print("x")` and `sys.stderr.write("y")` do not raise); `test_ensure_streams_leaves_real_streams`; `test_parse_args` (`--home C:\x y` and `--check`, none given gives `None`/`False`).
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement** `paths.py` (plus `parse_args`) and call `ensure_streams` early in `main.main` once the log file stream exists (open it with `open(app/"chatreader.log", "a", encoding="utf-8")` for the fallback). `main.main` takes the home option and replaces the inline `Path(os.environ.get(...))`. `__main__.py` parses args and passes `--home` through; `--check` is wired in Task 4.
- [ ] **Step 4: Run the full fast suite.**
- [ ] **Step 5: Commit** `feat: data folder resolution, --home and windowless streams`.

### Task 2: Autostart on the registry

**Files:**
- Modify: `src/chatreader/startup.py`, `src/chatreader/main.py`
- Test: `tests/test_startup.py`

**Interfaces:**
- Produces: `set_start_with_windows(enabled: bool, app_dir: Path, reg=winreg, frozen: bool | None = None, executable: str | None = None) -> None`; `startup_command(app_dir, frozen, executable) -> str`; `shortcut_path()` kept for migration.
- Consumes: the existing call in `main.py` (`startup.set_start_with_windows(on, app)`), which keeps working through defaults.

- [ ] **Step 1: Write failing tests (rewrite the PowerShell-based ones):** `test_enable_writes_run_value_frozen` (fake `winreg` records `SetValueEx`; the value is the quoted exe path); `test_enable_source_command` (`"<pythonw>" -m chatreader --home "<dir>"`); `test_command_quotes_spaces_and_apostrophes_and_unicode` (paths like `C:\Users\Ana María's PC\Chat Reader` stay inside double quotes, one command); `test_disable_deletes_value_and_old_shortcut` (an existing fake shortcut file is removed); `test_disable_missing_value_is_not_an_error` (fake `DeleteValue` raising `FileNotFoundError`); `test_registry_error_propagates` (fake raising `PermissionError` on enable reaches the caller); `test_enable_removes_old_shortcut`; and `tests/test_main.py::test_failing_toggle_applies_and_saves_nothing` stays green.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement** with `winreg.CreateKey`/`OpenKey` on the Run key, `SetValueEx(..., REG_SZ, command)` and `DeleteValue`. Drop the `subprocess` and PowerShell code and the `_q` helper. `frozen` defaults to `getattr(sys, "frozen", False)`.
- [ ] **Step 4: Run the full fast suite;** grep `src` for `powershell` and expect no matches.
- [ ] **Step 5: Commit** `feat: autostart through the registry Run key`.

### Task 3: Single instance

**Files:**
- Create: `src/chatreader/instance.py`
- Modify: `src/chatreader/__main__.py`
- Test: `tests/test_instance.py`

**Interfaces:**
- Produces: `acquire(name="Local\\ChatReader", create_mutex=_create_mutex) -> bool` (True when this process is the first); `open_running(port: int, open_url=webbrowser.open) -> None`; `_create_mutex(name) -> tuple[handle, already_exists]` using `ctypes.windll.kernel32.CreateMutexW` and `GetLastError() == 183`. The handle is kept alive in a module-level variable.

- [ ] **Step 1: Write failing tests:** `test_first_launch_acquires` (fake mutex reports not existing, returns True); `test_second_launch_does_not_acquire` (fake reports existing, returns False); `test_open_running_opens_root_url` (`open_url` called with `http://127.0.0.1:8765/`); `test_main_second_launch_opens_page_and_exits` (in `__main__.run(argv, acquire, open_running, start)` with fakes: when `acquire` is False, `open_running` is called with the configured port and `start` is not called; exit code 0); `test_main_first_launch_starts` (the reverse); `test_port_read_from_config` (the port comes from `config.toml` in the data folder, default 8765 when missing or unreadable).
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement.** Refactor `__main__.py` into `run(argv, acquire=..., open_running=..., start=...) -> int` called by `if __name__ == "__main__"`, reading the port with `load_config` guarded by try/except (any failure means 8765). The second launch does not wait for the first to listen: it just opens the URL (the first instance's page loads once it is up; the browser shows its own error if it is not yet).
- [ ] **Step 4: Run the full fast suite.**
- [ ] **Step 5: Commit** `feat: single instance with second launch opening the page`.

### Task 4: Self check

**Files:**
- Create: `src/chatreader/selfcheck.py`
- Modify: `src/chatreader/__main__.py`
- Test: `tests/test_selfcheck.py`

**Interfaces:**
- Produces: `run_check(app: Path, steps=DEFAULT_STEPS) -> tuple[int, dict]` and `main_check(app) -> int` printing the JSON line. Steps are named callables returning a detail string or raising: `imports`, `language`, `server` (starts `create_app` with fakes on port 0 via `run_server`, requests `/`, `/static/app.js`, `/api/status` with `urllib`, expects 200, shuts down), `synth` (skipped with `"skipped": "no model"` when the model files are absent, otherwise synthesizes `"ok"` and checks the result starts with `RIFF`).

- [ ] **Step 1: Write failing tests:** `test_all_steps_ok_exits_0` (fake steps; result dict has each step `ok`); `test_one_failing_step_exits_1_and_names_it`; `test_missing_model_skips_synth_and_still_ok`; `test_output_is_single_json_line` (capture stdout, one line, parseable, keys `ok` and `steps`); `test_check_flag_dispatches` (`run(["--check"], ...)` calls `main_check` and does not acquire the mutex or start the tray); `test_server_step_real` (not fake: the real `server` step passes against the real app in the test run).
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement.** `--check` is handled first in `run`, before the single-instance check, so a check works while the app is running. Use port 0 and read the bound port from the uvicorn server socket (add an optional `on_port` hook or read `server.servers[0].sockets` inside the step, whichever keeps `run_server` unchanged for other callers).
- [ ] **Step 4: Run the full fast suite;** then `uv run python -m chatreader --check` from source prints one JSON line with `"ok": true`.
- [ ] **Step 5: Commit** `feat: --check self test`.

### Task 5: Packaging files

**Files:**
- Create: `packaging/chatreader.spec`, `packaging/build.py`, `packaging/make_icon.py`, `packaging/README.md`, `THIRD_PARTY_NOTICES.txt`
- Modify: `pyproject.toml` (dependency group `build = ["pyinstaller"]`), `.gitignore` (`build/`, `dist/`, `packaging/icon.ico`)
- Test: `tests/test_packaging.py`

**Interfaces:**
- Produces: `packaging/build.py` exposes `version(pyproject: Path) -> str`, `zip_name(version) -> str` (`ChatReader-<version>-win64.zip`), `write_checksum(zip_path) -> Path` (SHA-256 file `<zip>.sha256`), and `main()` which runs `make_icon`, PyInstaller with the spec, copies notices and a short `README.txt` into `dist/ChatReader/`, zips it and writes the checksum.

- [ ] **Step 1: Write failing tests:** `test_version_from_pyproject`; `test_zip_name`; `test_checksum_file_matches_sha256` (tmp file, known digest, file contents `<hex>  <name>`); `test_notices_list_all_runtime_dependencies` (every name in `pyproject` `dependencies` appears in `THIRD_PARTY_NOTICES.txt`, plus Kokoro-82M with Apache-2.0); `test_spec_collects_data_packages` (the spec text names `kokoro_onnx`, `espeakng_loader`, `lingua`, `pytchat`, the `web` data folder, and `console=False`).
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement.** The spec: entry `src/chatreader/__main__.py`, `console=False`, `icon=packaging/icon.ico`, `collect_all` for the four packages, `datas` for `src/chatreader/web`, hidden imports for `uvicorn.logging`, `uvicorn.loops.auto`, `uvicorn.protocols.http.auto`, `uvicorn.protocols.websockets.auto`, `uvicorn.lifespan.on`, `pystray._win32`, onedir output named `ChatReader`. `make_icon.py` draws the tray icon at 16, 32, 48 and 256 px using the same function as `tray.build_icon`'s image (reuse it, do not duplicate) and saves an `.ico`. `THIRD_PARTY_NOTICES.txt` lists each dependency with its licence name and a pointer to the upstream licence file. `packaging/README.md` documents the build command, installing PyInstaller from source for a locally compiled bootloader, the checksum, and submitting a false-positive report per release.
- [ ] **Step 4: Run the full fast suite.**
- [ ] **Step 5: Commit** `feat: PyInstaller packaging`.

### Task 6: Build, verify, document

**Files:**
- Modify: `docs/GUIDE.md`, `README.md`

- [ ] **Step 1: Build:** `uv run --group build python packaging/build.py`. Expected: `dist/ChatReader/ChatReader.exe`, the zip and its `.sha256`.
- [ ] **Step 2: Run the built self check:** `dist/ChatReader/ChatReader.exe --check` from a terminal. Expected: one JSON line with `"ok": true` (synth skipped without a model). Copy the model into a temp data folder and run it again with `--home <that folder>`; expect synth ok. Any missing-module or missing-data failure: add it to the spec's `collect_all`/hidden imports and rebuild, ledger each fix as a ruling.
- [ ] **Step 3: Smoke the app:** start the exe, confirm the tray icon appears and `http://127.0.0.1:8765/` answers (use `curl`), launch it a second time and confirm it exits quickly and only one process remains, then quit from the page and confirm the process is gone.
- [ ] **Step 4: Update docs.** Guide: a new first section "Install (no Python)" with unzip, run, first-run download, data folder, Start with Windows, SmartScreen "More info, Run anyway" and the checksum; the source install stays as the second option. README: build command, notices file, new test count, a note that antivirus flags are possible and what to do. Troubleshooting rows: SmartScreen, antivirus quarantine, second launch just opens the page.
- [ ] **Step 5: Run the full fast suite,** then commit `docs: standalone app`.

---

## Self-review notes

- Spec coverage: data folder and windowless (T1), autostart and migration (T2), single instance (T3), self check (T4), build, icon, notices, antivirus steps (T5), build verification and docs (T6). Installer, signing and auto-update are out of scope, as in the spec.
- Order keeps the suite green: T1 adds `app_dir` behind the old behaviour; T2 replaces `startup` with the same call signature; T3 and T4 refactor `__main__.py` once each.
- Manual checks stay with the author on a clean machine: Defender/SmartScreen behaviour, OBS audio from the built app, sign-out/sign-in autostart, and the first-run model download.
- Building and the PyInstaller bootloader compile need a Windows machine with network access and, for a locally compiled bootloader, the MSVC build tools; T6 uses the stock bootloader and records that as the default.

# ChatReader standalone app: design

Date: 2026-10-19
Status: Draft for review

## Goal

Run ChatReader as a taskbar-icon-only Windows app that needs no Python, no `uv`
and no terminal: unzip, double-click, and use it through the control center in a
browser or OBS dock, with the voice coming through the OBS Browser Source. The
runtime is already like this (tray icon, web UI, overlay); this work is
packaging and the things packaging breaks.

## Decisions

| Topic | Decision |
|---|---|
| Shape | A folder build ("onedir") zipped for download, windowless, with `ChatReader.exe` inside. No installer in this round. |
| Tool | PyInstaller, kept in a separate `build` dependency group. The spec and build script live in `packaging/`. |
| Model | Not bundled. Downloaded on first run, as now, into the data folder. |
| Data folder | `%APPDATA%\ChatReader` when running as the built app; `CHATREADER_HOME` still overrides; running from source keeps using the current folder. |
| Start with Windows | A registry Run key (`HKCU\...\Run`), written with the standard library. PowerShell is removed from the app. |
| Second launch | Opens the control center of the running instance instead of failing on the port. |
| Self check | `ChatReader.exe --check` starts the server on a free port, loads the bundled files, and exits 0 or 1, so the built app can be tested headless. |
| Notices | `THIRD_PARTY_NOTICES.txt` ships in the zip with the Apache-2.0 and MIT notices. |

## Out of scope

An installer (Inno Setup), code signing, auto-update, a single-file exe,
macOS or Linux, bundling the model, a native window.

## Data folder

`app_dir()` in a new `paths.py` returns, in order: `CHATREADER_HOME` if set; the
`%APPDATA%\ChatReader` folder when `sys.frozen` is true (created on demand);
otherwise the current directory. `main.py` uses it instead of the inline
expression. Existing source installs are unaffected. The built app does not
migrate files from a source install; the guide says to copy `config.toml` and
`voices/` if wanted.

## Windowless runtime

A windowless build has no `sys.stdout` or `sys.stderr`. At startup, when they are
`None`, both are pointed at the log file's stream so libraries that print (or
`logging.lastResort`) cannot crash the app. Uncaught errors already go to the log.

## Start with Windows

`startup.py` is rewritten around `winreg`:

- Enable: set `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\ChatReader` to
  the command line: the quoted path of `ChatReader.exe` when frozen, otherwise
  the quoted `pythonw.exe` with `-m chatreader` (source installs). The working
  directory is not needed because the data folder no longer depends on it; source
  installs add `CHATREADER_HOME` is not required either since they run from the repo folder
  via their own launcher, so the source command is `cmd /c cd /d "<app_dir>" && "<pythonw>" -m chatreader` hidden with `start /b`.
- Disable: delete the value. Also delete the old Startup-folder `ChatReader.lnk`
  if present, so users of the earlier version are migrated.
- The registry module is passed in (`winreg` by default) so tests use a fake.
- Errors still propagate so the settings save reports them, as today.

## Single instance

At startup, before building the tray icon:

1. Create a named mutex (`Local\ChatReader`) with `ctypes`. If it already exists, this is a second launch.
2. A second launch opens `http://127.0.0.1:<port>/` in the browser (port read from the shared config) and exits with code 0.

A stale mutex cannot survive a crashed process (Windows frees it), so there is no lock file to clean up. The existing "port in use" notification stays for the case where a different program holds the port.

## Build

- `packaging/chatreader.spec`: entry `chatreader/__main__.py`, `console=False`, the app icon (generated from the same drawing as the tray icon at build time into `packaging/icon.ico`), `datas` for `src/chatreader/web`, and `collect_all` for `kokoro_onnx`, `espeakng_loader`, `lingua` (language data), `pytchat`, plus hidden imports for `uvicorn` protocol modules and `pystray._win32`.
- `packaging/build.py`: runs PyInstaller with the spec, copies `THIRD_PARTY_NOTICES.txt` and a short `README.txt` into the output, and zips `dist/ChatReader/` to `dist/ChatReader-<version>-win64.zip`. The version comes from `pyproject.toml`.
- `uv run --group build python packaging/build.py` is the one build command.

## Self check

`--check` (parsed in `__main__.py` before the tray starts):

1. Imports every runtime module; loads the language detector and runs one detection.
2. Starts the server on port 0, requests `/`, `/static/app.js`, `/api/status` and expects 200.
3. If `voices/` in the data folder holds the model, synthesizes one short phrase and expects a WAV.
4. Prints one JSON line to stdout (visible when run from a terminal) and exits 0 on success, 1 on any failure.

## Testing

Automated (pytest, no network, no audio):

- `paths.app_dir`: env override wins; frozen uses `%APPDATA%\ChatReader` and creates it; plain run uses the current directory.
- `startup` with a fake `winreg`: enable writes the right value for frozen and source cases, quoting paths with spaces and apostrophes; disable deletes it and the old shortcut; deleting a missing value is not an error; registry errors propagate.
- Single instance: the second-launch path opens the browser URL and does not start the tray (mutex and browser injected).
- `--check`: with fakes, returns 0 on success and 1 when any step fails; output is one JSON line.
- Windowless streams: with `sys.stdout` set to `None`, startup replaces it and printing does not raise.

Manual (author, on a clean Windows account or machine without Python):

1. Build, unzip somewhere with spaces in the path, run `ChatReader.exe --check`, then start it.
2. First run downloads the model, the tray icon appears, the control center opens.
3. OBS Browser Source plays a test voice.
4. Turn on Start with Windows, sign out and in, confirm it starts and no second instance appears.
5. Launch it twice; the second launch opens the page and exits.
6. Windows Defender or SmartScreen behavior on the zip and exe is noted for the guide.

## Build order

1. `paths.app_dir` and its use in `main.py`; windowless streams.
2. `startup.py` on `winreg` with migration of the old shortcut.
3. Single instance.
4. `--check`.
5. `packaging/` spec, icon, build script, notices; the build dependency group.
6. Build and run the self check on this machine; docs (guide install section, README, troubleshooting for SmartScreen).

Each step keeps the full test suite green; step 5 is verified by the build itself.

## Risks

- PyInstaller misses data files for `kokoro_onnx`, `espeakng_loader` or `lingua`; the self check and a real synthesis in step 6 are the guard.
- Antivirus or SmartScreen warnings on an unsigned exe. Documented, not solved here.
- The zip is large (about 150 to 300 MB). The model is not in it.
- Moving autostart to the registry changes where users look to turn it off; the settings switch stays the way to do it, and Task Manager's Startup tab also lists it.
- A failed registry write now fails the settings save with a message, as the PowerShell path did.

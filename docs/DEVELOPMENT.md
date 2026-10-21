# Development

Running from source, building the app, and how it works. Test status and known limits are in [Status](STATUS.md).

## Requirements

- Windows 10 or 11
- Python 3.11 or newer, and [uv](https://docs.astral.sh/uv/)
- Internet access for chat and for the first-run model download

## Install

```
uv sync
```

## Run

```
uv run python -m chatreader
```

This keeps a console window open. For daily use without a console window:

```
pythonw -m chatreader
```

`uv run chatreader-tray` starts the same app through its GUI entry point.

On first run the app:

- downloads the Kokoro model (about 120 MB: `kokoro-v1.0.int8.onnx` and `voices-v1.0.bin`) into `voices/`,
- creates `config.toml` with the default values,
- opens the settings page in your browser.

The app lives in the system tray (purple circle icon). Set `CHATREADER_HOME` to choose the folder for `config.toml`, `voices/` and `chatreader.log`. The default is the current working directory. The log rotates at 1 MB, keeps 3 backups, and records errors only unless `debug` is on.

## Packaged app

`uv run --group build python packaging/build.py` builds `dist/ChatReader/ChatReader.exe` (a windowless tray app, no Python needed), a zip and its SHA-256 file; `ChatReader.exe --check` self-tests the build (exit code 0 = ok; the result is saved as `check-result.json` in the data folder). Data lives in `%APPDATA%\ChatReader` (override with `--home <folder>` or `CHATREADER_HOME`). Start with Windows uses the per-user registry Run key. The build is unsigned, so Windows or antivirus may warn; see `packaging/README.md`. The zip bundles GPL-3.0 components (phonemizer, espeak-ng): `THIRD_PARTY_NOTICES.txt` and the `licenses` folder in the zip list everything and what redistribution requires.

## How it works

1. The Twitch source (anonymous IRC over WebSocket) and the YouTube source (`pytchat`) each run in a thread. Each reconnects with backoff, from 1 s up to 30 s.
2. Filters drop bots and ignored users, `!commands`, links, repeats, and spam (a run of 10 or more identical characters, or one token making up 60% or more of a message of four or more tokens). The rest is truncated to `max_chars`.
3. a small fastText model picks the language among the enabled `languages` (confidence at least 0.7, otherwise `default_lang`). The text becomes "<user> disse: ..." or "<user> says: ...".
4. A bounded queue feeds one worker thread, which synthesizes the text with Kokoro on the CPU (2 threads).
5. The WAV goes to the overlay over a local WebSocket. The overlay plays it and replies `done`. The worker waits for that reply (clip length plus 2 s) before the next clip, so lines never overlap.

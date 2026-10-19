# ChatReader

A Windows tray app that reads Twitch and YouTube live chat aloud, in Portuguese (BR) and English. Speech is generated locally on the CPU with [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) (via `kokoro-onnx`). Audio reaches the stream through an OBS Browser Source.

Status: early version (0.1.0). The automated tests pass; the manual checks listed under "Still to verify" are not done yet.

## Voice licences

The engine is Kokoro-82M. Its code (`kokoro-onnx`, MIT) and weights (Apache-2.0) are permissively licensed, and the model card says it was trained on permissive or non-copyrighted audio.

- Not verified: where the training data of the individual Portuguese voices (`pf_dora`, `pm_alex`, `pm_santa`) comes from. The VOICES.md file does not document it. Ask the author (hexgrad) or get written legal advice before relying on it for a monetized stream.
- Phonemes come from espeak-ng (GPL-3.0+) through `kokoro-onnx`. This matters if you redistribute the app, not for the generated audio. This is not legal advice.
- An earlier version used Piper voices. Those were dropped because `en_US-lessac-medium` is under a research-only licence and the Portuguese Piper voices are finetuned from it.

Voices can be swapped in the settings page (`voice_pt`, `voice_en`). Model files are downloaded at runtime and are never committed (`voices/` is git-ignored).

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

## OBS setup

1. Start ChatReader.
2. In OBS, add a **Browser** source with the URL `http://127.0.0.1:8765/overlay`. Use the port from your config if you changed it.
3. Tick **Control audio via OBS**. The source then appears in the OBS mixer with its own volume and mute controls.

Open the overlay in one place only. Only one overlay connection is supported.

## Settings page and tray menu

The settings page is at `http://127.0.0.1:8765/settings`. It opens on first run and from the tray menu ("Settings..."). It edits every key in the table below. Saving writes `config.toml` and applies the change immediately. Filters and voices apply at once. Changing the Twitch channel or YouTube video ID reconnects that source. Invalid values are rejected with a message, and the previous config stays active. The **Test voice** button speaks a sample line with the selected voice.

The tray menu has:

- **Pause / Resume**: pauses the worker. Messages keep queuing up to the cap.
- **Skip current**: stops the clip now playing and moves on.
- **Settings...**: opens the settings page.
- **Copy overlay URL**: copies the overlay URL to the clipboard.
- **Quit**: stops the sources, the player and the server.

The tray tooltip shows the status of each source and of the overlay.

## config.toml

The file uses the defaults below when a key is missing. Keys that are not known are ignored. A file that cannot be parsed is renamed to `config.toml.bad`, and the defaults are loaded.

| Key | Default | Meaning |
|---|---|---|
| `twitch_channel` | `""` | Twitch channel name without `#`. Empty disables Twitch. |
| `youtube_video_id` | `""` | YouTube live video ID or URL (a URL is reduced to the ID). Empty disables YouTube. |
| `voice_pt` | `"pf_dora"` | Kokoro voice for Portuguese messages (`pf_dora`, `pm_alex`, `pm_santa`). |
| `voice_en` | `"af_heart"` | Kokoro voice for English messages (for example `af_heart`, `af_bella`, `am_michael`). |
| `default_lang` | `"pt"` | Language used when detection is unsure or the text is under 12 characters. `"pt"` or `"en"`. |
| `queue_size` | `20` | Messages waiting to be spoken. When full, the oldest waiting message is dropped. |
| `max_chars` | `200` | Longer messages are cut at a word boundary. |
| `announce_user` | `true` | Say "<user> disse:" or "<user> says:" before the text. |
| `port` | `8765` | Port of the local server (bound to `127.0.0.1` only). |
| `start_with_windows` | `false` | Adds or removes a `ChatReader.lnk` shortcut in the Startup folder. |
| `ignored_users` | `["nightbot", "streamelements", "streamlabs", "moobot"]` | Users whose messages are never read. |
| `repeat_window` | `5` | A message is skipped if the same user sent the same text within their last N messages. |
| `debug` | `false` | Write debug-level entries to the log. |

`config.example.toml` lists the same keys with comments. The app does not copy it; it writes the defaults.

## How it works

1. The Twitch source (anonymous IRC over WebSocket) and the YouTube source (`pytchat`) each run in a thread. Each reconnects with backoff, from 1 s up to 30 s.
2. Filters drop bots and ignored users, `!commands`, links, repeats, and spam (a run of 10 or more identical characters, or one token making up 60% or more of a message of four or more tokens). The rest is truncated to `max_chars`.
3. `lingua` picks Portuguese or English (confidence at least 0.7, otherwise `default_lang`). The text becomes "<user> disse: ..." or "<user> says: ...".
4. A bounded queue feeds one worker thread, which synthesizes the text with Kokoro on the CPU (2 threads).
5. The WAV goes to the overlay over a local WebSocket. The overlay plays it and replies `done`. The worker waits for that reply (clip length plus 2 s) before the next clip, so lines never overlap.

## Verified

Automated:

- `uv run pytest -q -m "not slow"`: 100 passed.

Headless smoke launch with an empty config folder:

- The app started. `GET /settings` returned 200, `GET /overlay` returned 200, and `GET /api/config` returned the default values.
- `config.toml` and `chatreader.log` were created.
- The port was released after the process was killed.

## Still to verify by you

The following checks need live chat, OBS and a running game. They have not been run.

- [ ] The tray icon appears with no console window (`pythonw -m chatreader`).
- [ ] The settings page Test button is audible in OBS, and the source has its own volume slider.
- [ ] Live Twitch chat, then live YouTube chat, for a few minutes each.
- [ ] Pause, Skip and Quit work from the tray.
- [ ] CPU use while a game runs: ______ %

## Known limits and risks

- `pytchat` scrapes YouTube and can break when YouTube changes. `sources/youtube.py` is isolated. The official YouTube API is a possible fallback; it is not implemented.
- Measured on this PC with 2 CPU threads: about 0.65 s of compute per second of audio, so a 3 s message takes about 2 s to synthesize. It keeps up in steady state but adds latency. The thread count is `THREADS` in `tts.py`.
- CPU use while a game runs has not been measured.
- Runs of 10 or more identical characters (for example "kkkkkkkkkk") are dropped as spam.
- Only one overlay connection is supported. A second connection takes over the audio.

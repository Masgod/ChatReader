# ChatReader

A Windows tray app that reads Twitch and YouTube live chat aloud, in Portuguese (BR) and English. Speech is generated locally on the CPU with [Piper](https://github.com/rhasspy/piper). Audio reaches the stream through an OBS Browser Source.

Status: early version (0.1.0). The automated tests pass; the manual checks listed under "Still to verify" are not done yet.

## Voice licences

**Read this before using ChatReader on a monetized stream.**

- `en_US-lessac-medium`: its model card points to the Lessac Blizzard 2013 Research Licence. It is for research purposes only, does not allow commercial use, and clause 7 restricts distribution. https://www.cstr.ed.ac.uk/projects/blizzard/2013/lessac_blizzard2013/license.html
- `pt_BR-faber-medium`: the dataset is CC0 (OHF-Voice/voice-datasets), but its model card says the voice was finetuned from the US English lessac voice, so it may inherit that restriction.
- The `rhasspy/piper-voices` README says MIT, but the individual model cards do not repeat the Lessac restriction. The legal status for a monetized stream is unclear.

Do not use these voices commercially without checking the licences yourself. Voices can be swapped in the settings page (`voice_pt`, `voice_en`). Voice files are downloaded at runtime and are never committed (`voices/` is git-ignored).

## Requirements

- Windows 10 or 11
- Python 3.11 or newer, and [uv](https://docs.astral.sh/uv/)
- Internet access for chat and for the first-run voice download

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

- downloads the two Piper voices (`pt_BR-faber-medium`, `en_US-lessac-medium`) into `voices/`,
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
| `voice_pt` | `"pt_BR-faber-medium"` | Piper voice for Portuguese messages. |
| `voice_en` | `"en_US-lessac-medium"` | Piper voice for English messages. |
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
4. A bounded queue feeds one worker thread, which synthesizes the text with Piper on the CPU.
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
- Piper pt-BR voices are few (`faber` medium, `edresson` low) and sound robotic.
- Windows CPU use has not been measured, and no real-time benchmarks were found for Piper.
- Runs of 10 or more identical characters (for example "kkkkkkkkkk") are dropped as spam.
- Only one overlay connection is supported. A second connection takes over the audio.

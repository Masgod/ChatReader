# Status

Version 0.2.0, an early release. What has been tested, what has not, and the known limits.

## Verified

Automated:

- `uv run pytest -q -m "not slow"`: 541 passed, 1 skipped.

Headless smoke launch with an empty config folder:

- The app started. `GET /settings` returned 200, `GET /overlay` returned 200, and `GET /api/config` returned the default values.
- `config.toml` and `chatreader.log` were created.
- The port was released after the process was killed.

## Not tested yet

The unchecked items need live chat, OBS and a running game.

- [ ] The tray icon appears with no console window (`pythonw -m chatreader`).
- [ ] The settings page Test button is audible in OBS, and the source has its own volume slider.
- [x] Live Twitch chat (tested by the author on their own stream).
- [ ] Live YouTube chat, for a few minutes.
- [ ] Pause, Skip and Quit work from the tray.
- [ ] The chat overlay in OBS: a bubble appears when the voice starts for Twitch and for YouTube chat, and none for filtered messages.
- [ ] CPU use while a game runs: ______ %

## Known limits and risks

- `pytchat` scrapes YouTube and can break when YouTube changes. `sources/youtube.py` is isolated. The official YouTube API is a possible fallback; it is not implemented.
- Measured on this PC with 2 CPU threads: about 0.65 s of compute per second of audio, so a 3 s message takes about 2 s to synthesize. It keeps up in steady state but adds latency. The thread count is the `cpu_threads` setting.
- CPU use while a game runs has not been measured.
- Runs of 10 or more identical characters (for example "kkkkkkkkkk") are dropped as spam.
- Only one overlay connection is supported. A second connection takes over the audio.

## Roadmap

Planned, in no fixed order. Open an issue to discuss or vote on any of these.

- **Emote images in the chat overlay bubbles**, and a step-by-step "make a theme" guide (plus one for a game-hero theme). The text overlay itself is done; see the guide section 3a.
- **Priority for events** in the speech queue, so cheers and subs are not dropped when the queue is full.
- **Channel point rewards** (custom Twitch rewards). Needs a Twitch login (OAuth), so it needs its own design.
- **Installer and code signing**, to avoid the SmartScreen warning and allow updates.

Contributions welcome:

- **Stream Deck / hotkeys** (pause, skip, mute). The maintainer has no Stream Deck, so this is open for someone who does: please open an issue or a pull request.


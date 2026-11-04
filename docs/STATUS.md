# Status

Version 0.3.0, an early release. What has been tested, what has not, and the known limits.

## Verified

Automated:

- `uv run pytest -q -m "not slow"`: 648 passed, 1 skipped (a symlink test that needs Windows Developer Mode).
- The Twitch device-code login and chat-message calls were compared with the current Twitch documentation. One difference was fixed: Twitch can answer 200 with `is_sent: false` (for example AutoMod held the message), and that now counts as not sent.

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
- [x] Twitch chat replies (tested by the author): Connect Twitch (device code), then `!hero`, `!random`, `!hero <name>` in the streamer's own chat; revoke the app and check chat reading keeps working.
- [x] The Restart button and tray item relaunch the app once, on the same port (tested by the author).
- [x] The Touch layout (4 big buttons, submenus, one page at a time) in a real OBS dock (tested by the author); not yet on a phone.
- [ ] The built zip starts on a machine without Python and serves every page.

## Known limits and risks

- `pytchat` scrapes YouTube and can break when YouTube changes. `sources/youtube.py` is isolated. The official YouTube API is a possible fallback; it is not implemented.
- Measured on this PC with 2 CPU threads: about 0.65 s of compute per second of audio, so a 3 s message takes about 2 s to synthesize. It keeps up in steady state but adds latency. The thread count is the `cpu_threads` setting.
- CPU use while a game runs has not been measured.
- Runs of 10 or more identical characters (for example "kkkkkkkkkk") are dropped as spam.
- Only one overlay connection is supported. A second connection takes over the audio.
- The Twitch login is stored in `twitch_token.json` in the app folder, readable only by the current Windows user (set with `icacls`). Anyone with that user's access can still send chat messages as the streamer; revoke the app at twitch.tv/settings/connections to cut it off.
- Replies only go to Twitch chat, never YouTube.
- Small known issues that were reviewed and left for later are listed in `docs/superpowers/plans/2026-10-28-release-0.3.md` under "Deferred minors".
- The Portuguese Kokoro voices have unverified training-data provenance, see [LICENSES](LICENSES.md).

## Roadmap

Planned, in no fixed order. Open an issue to discuss or vote on any of these.

- **Emote images in the chat overlay bubbles**, and a step-by-step "make a theme" guide (plus one for a game-hero theme). The text overlay itself is done; see the guide section 3a.
- **Priority for events** in the speech queue, so cheers and subs are not dropped when the queue is full.
- **Channel point rewards** (custom Twitch rewards). Needs a Twitch login (OAuth), so it needs its own design.
- **Installer and code signing**, to avoid the SmartScreen warning and allow updates.

Contributions welcome:

- **Stream Deck / hotkeys** (pause, skip, mute). The maintainer has no Stream Deck, so this is open for someone who does: please open an issue or a pull request.


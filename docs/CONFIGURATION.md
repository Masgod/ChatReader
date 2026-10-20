# Configuration and API

Everything you can change, and the local API. For a step-by-step walkthrough see the [user guide](GUIDE.md).

## Settings page and tray menu

The Settings tab is at `http://127.0.0.1:8765/settings`. It opens on first run and from the tray menu ("Settings..."). It edits every key in the table below. Saving writes `config.toml` and applies the change immediately. Filters and voices apply at once. Changing the Twitch channel or YouTube video ID reconnects that source. Invalid values are rejected with a message, and the previous config stays active. The voice fields are dropdowns built from the model's real voice list (a text box if the model is not loaded). The **Test voice** button speaks a sample line with the saved voice.

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
| `speed` | `1.0` | Speech speed, 0.8 to 1.4. |
| `cpu_threads` | `2` | CPU threads for speech, 1 to 8. Needs a restart. |
| `twitch_roles` / `youtube_roles` | `[]` | Who is read on that platform: empty means everyone, otherwise any of `sub`, `vip`, `mod` (the owner is always read). |
| `repeat_seconds` | `30` | Skip the same text from anyone within this many seconds; `0` turns it off. |
| `per_user_voices` | `true` | Give each viewer a stable voice picked from the model's voices. |
| `youtube_channel` | `""` | `@handle` or `UC...` channel ID. When set and `youtube_video_id` is empty, the app waits for the channel's live stream and connects by itself. |

`config.example.toml` lists the same keys with comments. The app does not copy it; it writes the defaults.

## OBS dock and status API

The control center is one page with three tabs: **Live** (status, queue with remove and clear, Pause/Resume, Skip, Copy overlay URL, Quit), **Console** (chat activity with the outcome of each message, plus the app log and a debug toggle) and **Settings**. Add `http://127.0.0.1:8765/dock` in OBS under Docks, Custom Browser Docks (it opens on Live); `/` and `/settings` open the same page. It works from about 300 px wide up. API: `GET /api/status`, `POST /api/control` (`pause`, `resume`, `skip`, `quit`), `GET /api/queue`, `POST /api/queue/remove` (`{"id": n}`), `POST /api/queue/clear`, `GET /api/events?since=N`, `POST /api/toggle` (`{"name": "debug", "value": bool}`), `GET /api/voices`. All are protected like the rest of the local server. Chat text shown in the console is kept in memory only (last 500 events) and is never written to disk by this feature. Long messages start speaking after their first sentence is synthesized (sentence prefetch).

# ChatReader guide

ChatReader reads your **Twitch** and **YouTube** live chat out loud, in Portuguese (BR) and English. It runs on your PC, hides in the Windows system tray, and sends the voice to **OBS** so you can control its volume like any other source.

- [1. Install](#1-install)
- [2. First start](#2-first-start)
- [3. Add it to OBS](#3-add-it-to-obs)
- [3b. Control it from OBS](#3b-control-it-from-obs)
- [4. Connect your chats](#4-connect-your-chats)
- [5. The tray icon](#5-the-tray-icon)
- [6. Settings explained](#6-settings-explained)
- [7. What gets read, what gets skipped](#7-what-gets-read-what-gets-skipped)
- [8. Voices](#8-voices)
- [9. Daily use](#9-daily-use)
- [10. Troubleshooting](#10-troubleshooting)
- [11. Before you monetize](#11-before-you-monetize)

---

## 1. Install

You need Windows 10/11, [Python 3.11+](https://www.python.org/downloads/) and [uv](https://docs.astral.sh/uv/).

Open a terminal in the project folder and run:

```
uv sync
```

## 2. First start

```
uv run python -m chatreader
```

On the very first run ChatReader will:

1. Download the voice model (about 120 MB). This takes a minute; the tray icon is already there while it downloads.
2. Create `config.toml` with default settings.
3. Open the **settings page** in your browser.

If the download fails you get a tray notification. Check your internet and start it again; it only fetches what is missing.

> The console window stays open with this command. For daily use, see [Daily use](#9-daily-use).

## 3. Add it to OBS

ChatReader does not play sound itself. It sends it to OBS through a Browser Source, so you get a separate volume slider and mute button.

1. In OBS, under **Sources**, click **+** and choose **Browser**.
2. Name it, for example `Chat voice`.
3. Set **URL** to `http://127.0.0.1:8765/overlay`.
4. Tick **Control audio via OBS**.
5. Click **OK**.

The source now appears in the OBS **Audio Mixer**.

**Hear it yourself:** OBS sends source audio to the stream and recording, not to your own speakers, unless you monitor it. In OBS open **Edit → Advanced Audio Properties** (or the gear next to the source in the Audio Mixer), find `Chat voice`, and set **Audio Monitoring** to **Monitor and Output**. Without this you will hear nothing locally even though the audio works.

**The source must be active:** OBS only mixes a Browser Source that is in the scene currently on air. If you switch scenes, put the source in a scene of its own (for example `TTS`) and add that scene as a source inside each scene you use, so the voice works everywhere.

**Test it:** open the settings page and press **Test voice**. You should hear a sample line, and the Chat voice meter in OBS should move.

Good to know:

- Add the overlay in **one place only**. Don't also open `/overlay` in a normal browser tab, because it takes over the audio.
- While OBS isn't connected, messages wait in the queue instead of being lost (up to your queue size).
- If the source is hidden in a scene OBS may unload it. Keep it visible, or right-click the source and untick "Shutdown source when not visible".

## 3b. Control it from OBS

You can keep a small control panel next to your scenes, so you never leave OBS.

1. In OBS, open **Docks** → **Custom Browser Docks**.
2. Name it `ChatReader` and set the URL to `http://127.0.0.1:8765/dock`. Click **Apply**.

The panel shows green, amber or red status for Twitch, YouTube, the OBS overlay and the voice model, plus how many messages are waiting. It has **Pause / Resume**, **Skip**, **Test voice**, a **Speed** slider and a field for your YouTube link or channel.

On first run the settings page also shows a short **Getting started** checklist (voice model ready, a chat source set, OBS overlay connected). It is shown whenever one of the three is not done (for example when OBS is closed) and disappears when all three are done.

## 4. Connect your chats

Open the settings page (tray icon → **Settings...**, or `http://127.0.0.1:8765/settings`).

**Twitch:** type your channel name under **Twitch channel**, for example `mychannel`. No login is needed; ChatReader reads chat anonymously. You can also paste `twitch.tv/mychannel` and it is cleaned up for you.

**YouTube:** paste the **video ID or the full link** of your live stream under **YouTube video**, for example `https://www.youtube.com/watch?v=abcdefghijk`. The video ID changes on every stream, so update this field each time you go live.

**YouTube without pasting a link every stream:** type your channel handle (for example `@yourchannel`) under **YouTube channel**. ChatReader then waits for your live stream and connects by itself when it starts, and again for the next stream. If a video link or ID is also set, the video link wins. This works by reading YouTube's public live page, so it can stop working if YouTube changes it. The manual link always keeps working.

Press **Save**. The sources connect right away, no restart needed. Leave a field empty to turn that platform off.

## 5. The tray icon

Look for the purple circle near the clock (you may need to click the `^` arrow). Right-click it:

| Item | What it does |
|---|---|
| **Pause / Resume** | Stops speaking. New messages keep queuing up to your queue size. |
| **Skip current** | Cuts off the message being read and goes to the next one. |
| **Settings...** | Opens the settings page. |
| **Copy overlay URL** | Copies the OBS Browser Source address. |
| **Quit** | Closes ChatReader completely. |

Hover over the icon to see the status of Twitch, YouTube and the OBS connection.

## 6. Settings explained

The page has a footer with **Save** and **Test voice**. When you change something it says *Unsaved changes*; **Save** applies it immediately.

### Sources
- **Twitch channel**, **YouTube video**: see [section 4](#4-connect-your-chats).

### Voices
- **Default language**: used when ChatReader isn't sure which language a message is in (very short messages like `gg`, or mixed text).
- **Portuguese voice** / **English voice**: which voice speaks each language. The ▶ button plays a sample of the *saved* voice, so press **Save** first after changing it. See [Voices](#8-voices).

### Speed and CPU
- **Speed** (Voices): 0.8 to 1.4. Higher is faster speech.
- **CPU threads** (System): how many CPU threads speech uses, 1 to 8, default 2. Lower leaves more CPU for your game, higher makes speech start sooner. Needs a restart.

ChatReader also starts speaking a long message after its first sentence is ready, so you hear the beginning sooner.

### Reading
- **Announce user name**: says "viewer disse: ..." (Portuguese) or "viewer says: ..." (English) before each message. Turn it off to hear only the text.
- **Queue size**: how many messages can wait. When it is full, the oldest waiting one is dropped, so the voice stays close to live chat. Lower = more current, higher = fewer missed messages.
- **Max characters**: longer messages are cut at a word boundary.
- **Repeat window**: skips a message if the same person sent the same text within their last N messages. `0` turns it off.

### Ignored users
Bots and people you never want read. Type a name and press **Add**, or click **×** on a chip to remove it. Names are not case sensitive, and a leading `@` is ignored. You can add several at once separated by spaces or commas. Common bots (nightbot, streamelements, streamlabs, moobot) are there by default.

### System
- **Port**: the local port. Leave it unless something else uses 8765. Changing it needs a restart, and you must update the OBS URL.
- **Start with Windows**: starts ChatReader when you sign in (adds a shortcut to your Startup folder).
- **Debug**: writes more detail to the log file. Leave it off normally.

## 7. What gets read, what gets skipped

ChatReader reads **every message** except:

- messages from **ignored users**
- **commands** starting with `!` (like `!discord`)
- messages with **links**
- messages with **no letters or numbers** (only emotes/symbols)
- **repeats** from the same person (see Repeat window)
- **spam**: ten or more identical characters in a row (`aaaaaaaaaa`), or one word making up most of a message (`LUL LUL LUL LUL`)

Language is detected for each message, so one chat can mix Portuguese and English and each message gets the right voice.

## 8. Voices

ChatReader uses **Kokoro**. You can type any Kokoro voice name in the voice fields, or pick one from the suggestions:

| Language | Suggestions |
|---|---|
| Portuguese (BR) | `pf_dora` (female, default), `pm_alex`, `pm_santa` (male) |
| English | `af_heart` (default), `af_bella`, `am_michael`, `bf_emma` |

If you type a name that doesn't exist, you get a warning and that language is not spoken.

## 9. Daily use

**Without a console window:**

```
pythonw -m chatreader
```

Put a shortcut to that command on your desktop, or just turn on **Start with Windows** in the settings.

**Where files live:** the folder you start it from (or the folder set in the `CHATREADER_HOME` environment variable) holds:

- `config.toml`: your settings. The settings page edits it for you.
- `voices/`: the downloaded voice model.
- `chatreader.log`: errors and, with Debug on, more detail.

**Every stream:** start ChatReader (or let Windows do it), paste the new YouTube video link if you stream there, and check the tray tooltip says the sources are connected.

## 10. Troubleshooting

| Problem | What to try |
|---|---|
| **No sound in OBS** | Is the Browser Source visible and does the URL match your port? Is *Control audio via OBS* ticked and the mixer not muted? Press **Test voice**. |
| **Test voice is silent but the tray says OBS is connected** | Open the OBS source properties and press **Refresh cache of current page**. |
| **"Failed to start" notification** | Usually the port is taken. Close the other copy of ChatReader, or change `port` in `config.toml`. Details are in `chatreader.log`. |
| **YouTube shows failed** | The video ID must belong to a stream that is **live** and has chat. It retries on its own; fix the ID in settings and Save. |
| **Messages are late** | Speech takes a bit longer than the audio it makes, so a busy chat builds a queue. Lower **Queue size** so old messages are dropped instead of read late. |
| **Message missing** | It was probably filtered ([section 7](#7-what-gets-read-what-gets-skipped)) or dropped because the queue was full. |
| **Settings won't save** | A red box lists what to fix, for example a Twitch name must be 3–25 letters, digits or `_`. |
| **Config broke** | A file ChatReader can't read is renamed `config.toml.bad` and defaults load. Delete `config.toml` to start fresh. |
| **Game stutters** | Lower **CPU threads** in settings (System), at the cost of slower speech. Restart ChatReader afterwards. |
| **Dock says "ChatReader not reachable"** | ChatReader is not running, or uses another port. Check the tray icon and that the dock URL has your port. |

## 11. Before you monetize

- The Kokoro model and code are permissively licensed (Apache-2.0 / MIT). The Portuguese voices' own training data isn't documented. If your stream earns money, ask the model's author or get legal advice. Details are in the README under *Voice licences*.
- Twitch chat is read from the public chat feed, and YouTube chat is read by scraping the public page. Check each platform's terms for your use.
- Everything runs locally and the server only listens on your own PC (`127.0.0.1`).

# ChatReader guide

ChatReader reads your **Twitch** and **YouTube** live chat out loud, in Portuguese (BR), English, Spanish, French or Italian. It runs on your PC, hides in the Windows system tray, and sends the voice to **OBS** so you can control its volume like any other source.

- [1. Install](#1-install) (packaged app or from source)
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

### Option A: the packaged app (no Python)

Unzip `ChatReader-<version>-win64.zip` anywhere and run `ChatReader.exe`. Nothing else to install. A purple icon appears in the taskbar tray, the control center opens in your browser, and the voice model (about 120 MB) downloads on first run. Your settings, log and voice model live in `%APPDATA%\ChatReader`.

- Windows may show "Windows protected your PC" because the app is not signed. Choose **More info**, then **Run anyway**. You can verify the download with the `.sha256` file next to the zip (`certutil -hashfile ChatReader-<version>-win64.zip SHA256`).
- Run it a second time and it just opens the control center of the copy that is already running.
- **Start with Windows** (Settings, System) adds an entry for the current user. Turn it off there, or in Task Manager's Startup tab.
- `ChatReader.exe --check` runs a quick self test. The app has no console window, so run it as `Start-Process -Wait -PassThru .\ChatReader.exe -ArgumentList '--check'` in PowerShell: the exit code is 0 when everything is ok, and the result (one line of JSON) is saved in `check-result.json` in the data folder.
- The zip bundles components under several licences, including GPL-3.0 ones (see `THIRD_PARTY_NOTICES.txt`). Read it before you share the zip.

### Option B: from source

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
3. Open the **control center** (the Settings tab) in your browser.

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

## 3a. Show the chat on screen (optional)

The chat overlay shows a speech bubble for each message, at the moment its voice starts, and removes it a few seconds after the voice ends. Messages that are filtered out or skipped never get a bubble. The audio source from section 3 must be connected, because the bubble follows the voice: with no audio source, messages wait in the queue and no bubble shows.

1. In OBS add **another** Browser source (the audio one above is still required) with URL `http://127.0.0.1:8765/chat-overlay`.
2. Set the size to about 450 × 600. The background is transparent.
3. Open **Settings → Chat overlay** to pick the theme and the position (six places), how many bubbles stay on screen (1 to 10) and how many seconds a bubble stays after the voice ends (0 to 30), and the **Size** of the whole overlay in percent (50 to 200, in steps of 10).
4. Press **Test bubble** to see a sample. It uses the saved settings, so save first.

Events (bits, subs, gifts, raids, Super Chat, members) get their own colors and a one-line description when you have **Read events aloud** on.

### Themes

A theme is a folder in `themes` inside the app folder (`%APPDATA%\ChatReader\themes\<name>`). The built-in `default` theme needs no folder. A theme folder holds:

- `theme.toml`: the look. `[bubble]` has `background`, `color` (like `#1f1b2e`), `radius` (0 to 40), `animation` (`fade`, `slide`, `snap` or `none`) and `layout` (`side`, the default, puts the portrait left of the text; `top` puts it above the text box), `portrait_width` and `portrait_height` (pixels, 16 to 320; the defaults are 56 × 56 for `side` and 96 × 96 for `top`); `[events]` has `background` and `color`; `[sender]` has `color` (default `#ffffff`) and `outline` (default `#000000`) for the viewer's name, which the `top` layout draws beside the portrait with a contour; optional `font = "fonts/name.woff2"`; optional `[[expressions]]` entries (`name`, `chance` from 0 to 1, adding up to at most 1) and `fallback` (one of those names).
- `heroes/<hero>/<expression>.png`: one avatar folder per character. Each viewer is given the same hero every time, and a random expression each time a bubble is shown. The format limits are 200 images, 5 MB per file, and `png`, `jpg`, `webp`, `gif` or `svg` images and `woff2`, `otf` or `ttf` fonts.

A theme with a mistake is listed as not usable in Settings, and the overlay shows the default theme instead. Artwork from games or other people is your responsibility: ChatReader ships none, so make sure you are allowed to use what you put in a theme.

### Chat command: `!random`

A viewer who types `!random` in chat gets a new random hero, and keeps it: the choice is saved in `viewer_heroes.json` in the app folder, so it survives restarts. The command is never read aloud. To stop people spamming it, each use makes the next wait longer: a viewer waits 10 s after the first use, then 20 s, 40 s and so on up to 5 minutes, and the whole chat shares a similar wait (2 s up to 60 s). After a quiet minute the waits start over. A `!random` sent too early is ignored. The four wait values are in `config.toml` (`random_*`, see CONFIGURATION.md). Delete a viewer's line in `viewer_heroes.json` (with ChatReader closed) to give them their original hero back.

`!hero` tells a viewer which hero they have now (it uses the same waits, counted on its own). `!hero wraith` or `!hero grey talon` picks that hero from the active theme (upper or lower case, spaces or `_` all work) and counts as a `!random` for the waits. A name the theme doesn't have gets the answer `herói não encontrado` (at most as often as `!hero` alone) and costs no wait.

#### Answering in your Twitch chat (optional)

With a Twitch login, ChatReader replies as your own account: after `!random`, `@viewer agora é Wraith`; after `!hero`, `@viewer é Wraith`. Without it the commands still work, silently. YouTube chat never gets replies. One-time setup:

1. Go to [dev.twitch.tv/console](https://dev.twitch.tv/console) (Twitch asks you to turn on two-factor authentication first), choose **Register Your Application**, give it any name, set the OAuth Redirect URL to `http://localhost`, the category to Chat Bot, and the client type to **Public**. Copy the **Client ID**.
2. Settings, Twitch section: paste the Client ID into **Twitch Client ID** and press Save.
3. Press **Connect Twitch**. Open the link it shows while logged in as the account that should answer, enter the code, and authorize. The permission asked is only `user:write:chat` (send chat messages).

The login is kept in `twitch_token.json` in the app folder, renewed by itself, and never leaves your computer except to talk to Twitch. Treat it like a password: don't share it or put it in a repository. Delete the file to log out; you can also revoke the app at twitch.tv/settings/connections. Replies are sent in the channel set as **Twitch channel**.

## 3b. Control it from OBS

You can keep a small control panel next to your scenes, so you never leave OBS.

1. In OBS, open **Docks** → **Custom Browser Docks**.
2. Name it `ChatReader` and set the URL to `http://127.0.0.1:8765/dock`. Click **Apply**.

The page has three tabs and works from a narrow dock (about 300 px) up to a full browser tab. `/` and `/settings` open the same page.

- **Live**: green, amber or red status for Twitch, YouTube, the OBS overlay and the voice model; **Pause / Resume**, **Skip**, **Copy overlay URL**, **Restart** (closes the app and starts it again by itself, then reloads the page) and **Quit** (click twice to confirm either one), the same as the tray menu; and the **queue**: the message being read, then those waiting. Click **×** to remove one waiting message, or **Clear all**. The one being read is ended with **Skip**.
- **Console**: every chat message with what happened to it, plus ChatReader's own log. Outcomes: `queued` (accepted), `played`, `failed` (the voice could not make audio), `dropped` (the queue was full), `skipped` (you pressed Skip), `removed` (you removed it) and `skipped:<reason>` for filtered messages (ignored user, role, command, link, no text, repeat, duplicate, spam). Use the **All / Chat / Log** chips, **Pause scrolling**, **Clear view** and the **Debug** switch. The console is kept in memory only (the last 500 lines) and is not saved to disk.
- **Settings**: everything in [section 6](#6-settings-explained).

On first run the Settings tab also shows a short **Getting started** checklist (voice model ready, a chat source set, OBS overlay connected). It is shown whenever one of the three is not done and disappears when all three are done.

## 4. Connect your chats

Open the Settings tab (tray icon → **Settings...**, or `http://127.0.0.1:8765/settings`).

**Twitch:** type your channel name under **Twitch channel**, for example `mychannel`. No login is needed; ChatReader reads chat anonymously. You can also paste `twitch.tv/mychannel` and it is cleaned up for you.

**YouTube:** paste the **video ID or the full link** of your live stream under **YouTube video**, for example `https://www.youtube.com/watch?v=abcdefghijk`. The video ID changes on every stream, so update this field each time you go live.

**YouTube without pasting a link every stream:** type your channel handle (for example `@yourchannel`) under **YouTube channel**. ChatReader then waits for your live stream and connects by itself when it starts, and again for the next stream. If a video link or ID is also set, the video link wins. This works by reading YouTube's public live page, so it can stop working if YouTube changes it. The manual link always keeps working.

Press **Save**. The sources connect right away, no restart needed. Leave a field empty to turn that platform off.

## 5. The tray icon

Look for the purple circle near the clock (you may need to click the `^` arrow). Right-click it:

| Item | What it does |
|---|---|
| **Pause / Resume** | (also on the Live tab) Stops speaking. New messages keep queuing up to your queue size. |
| **Skip current** | Cuts off the message being read and goes to the next one. |
| **Settings...** | Opens the control center. |
| **Copy overlay URL** | Copies the OBS Browser Source address. |
| **Quit** | Closes ChatReader completely. |

Hover over the icon to see the status of Twitch, YouTube and the OBS connection.

## 6. Settings explained

The page has a footer with **Save** and **Test voice**. When you change something it says *Unsaved changes*; **Save** applies it immediately.

### Sources
- **Twitch channel**, **YouTube video**: see [section 4](#4-connect-your-chats).
- **Who is read** (one per platform): Everyone, or only Subscribers (Members on YouTube), VIPs (Twitch only) and/or Mods. The channel owner is always read. If the platform doesn't report a role for a viewer, that viewer counts as having none. Messages that don't match show as `skipped:role` in the Console.

### Events
- **Read events aloud**: off by default; turn it on to hear events. **Which events** picks the ones spoken, as "Fulano doou 100 bits: message". Twitch gives bits, subs and resubs, gift subs and raids without logging in. YouTube gives Super Chat, Super Stickers and new members. Events skip the role, repeat and command rules; only **Ignored users** still blocks them. A link or spam in the attached message is left out, the announcement is still read. Channel point rewards are not supported (Twitch requires a login for them), and YouTube gift memberships are not reported by the chat library.
- **Minimum bits**: cheers below this are not read (`skipped:min bits` in the Console; switched-off kinds show `skipped:event off`).

### Voices
- **Languages**: tick the languages to read. Portuguese and English are on by default; Spanish, French and Italian are marked beta because their wording (for example "dijo", "dit", "ha detto" and the event sentences) has not been checked by a native speaker. At least one stays on, and messages in other languages are read with whichever enabled language fits best.
- **Default language**: used when ChatReader isn't sure which language a message is in (very short messages like `gg`, or mixed text). Only enabled languages are offered.
- **A voice for each enabled language**: pick from the voices the model actually has (a text box if the model is not loaded yet). The ▶ button plays a sample of the *saved* voice, so press **Save** first after changing it. See [Voices](#8-voices).

### Speed and CPU
- **Speed** (Voices): 0.8 to 1.4. Higher is faster speech.
- **CPU threads** (System): how many CPU threads speech uses, 1 to 8, default 2. Lower leaves more CPU for your game, higher makes speech start sooner. Needs a restart.

ChatReader also starts speaking a long message after its first sentence is ready, so you hear the beginning sooner.

### Reading
- **Announce user name**: says "viewer disse: ..." (Portuguese) or "viewer says: ..." (English) before each message. Turn it off to hear only the text.
- **Queue size**: how many messages can wait. When it is full, the oldest waiting one is dropped, so the voice stays close to live chat. Lower = more current, higher = fewer missed messages.
- **Max characters**: longer messages are cut at a word boundary.
- **Repeat window**: skips a message if the same person sent the same text within their last N messages. `0` turns it off.
- **Skip the same text** (seconds): skips a message if anyone sent the same text in the last N seconds (ignoring capitals and extra spaces), so copy-paste floods are read once. Default 30; `0` turns it off.
- **A different voice for each viewer**: see [Voices](#8-voices).
- **Read laughs, skip emotes**: on by default. `LUL`, `KEKW`, `kkkk`, `rsrs` and `haha` are read as a laugh; `Kappa`, `PogChamp`, `<3` and `:name:` emotes are left out, and a message that is only emotes is skipped (`skipped:emotes only` in the Console).

### Ignored users
Bots and people you never want read. Type a name and press **Add**, or click **×** on a chip to remove it. Names are not case sensitive, and a leading `@` is ignored. You can add several at once separated by spaces or commas. Common bots (nightbot, streamelements, streamlabs, moobot) are there by default.

### System
- **Style**: Touch (the default) has big buttons and one column in Settings, made for a tablet, a phone or a touch screen; Mouse is the compact layout. It is remembered per device and browser (an OBS dock keeps its own), not in `config.toml`.
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
- **duplicates**: the same text from anyone within the last few seconds (see Skip the same text)
- viewers whose **role** is not allowed (see Who is read)
- **spam**: ten or more identical characters in a row (`aaaaaaaaaa`), or one word making up most of a message (`LUL LUL LUL LUL`)

Language is detected for each message, so one chat can mix the enabled languages and each message gets the right voice.

## 8. Voices

ChatReader uses **Kokoro**. You can type any Kokoro voice name in the voice fields, or pick one from the suggestions:

| Language | Suggestions |
|---|---|
| Portuguese (BR) | `pf_dora` (female, default), `pm_alex`, `pm_santa` (male) |
| English | `af_heart` (default), `af_bella`, `am_michael`, `bf_emma` |
| Spanish (beta) | `ef_dora` (default), `em_alex`, `em_santa` |
| French (beta) | `ff_siwis` |
| Italian (beta) | `if_sara` (default), `im_nicola` |

If you type a name that doesn't exist, you get a warning and that language is not spoken.

**A voice for each viewer:** with the switch on (the default), each viewer gets one voice, chosen once from that language's voices and kept across streams and restarts. The per-language voice settings stay as the defaults, used for the Test voice button and when no voice list is available. Portuguese has only three voices, so several viewers share them. Turn the switch off to use one voice per language for everyone. There is no screen yet to pick a viewer's voice by hand.

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
| **Windows says "protected your PC" or antivirus flags the exe** | The app is unsigned. Choose More info, Run anyway; compare the zip with its `.sha256` file; if your antivirus quarantines it, restore it and add the folder as an exception, or build it yourself (`packaging/README.md`). |
| **Starting it again does nothing** | That is on purpose: a second start opens the control center of the running copy. |
| **Dock says "ChatReader not reachable"** | ChatReader is not running, or uses another port. Check the tray icon and that the dock URL has your port. |

## 11. Before you monetize

- The Kokoro model and code are permissively licensed (Apache-2.0 / MIT), but the phonemizer it needs (phonemizer, espeak-ng) is GPL-3.0. Using ChatReader yourself is fine; if you share the built zip with others, read `THIRD_PARTY_NOTICES.txt` first, because redistribution comes with GPL obligations. The Portuguese voices' own training data isn't documented. If your stream earns money, ask the model's author or get legal advice. Details are in [Licences](LICENSES.md).
- Twitch chat is read from the public chat feed, and YouTube chat is read by scraping the public page. Check each platform's terms for your use.
- Everything runs locally and the server only listens on your own PC (`127.0.0.1`).

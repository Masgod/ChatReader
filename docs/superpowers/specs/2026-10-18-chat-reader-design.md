# Chat Reader: Design

Date: 2026-10-18
Status: Draft for review

## Goal

A small Windows tray app that reads every YouTube and Twitch live chat message
aloud, in Portuguese (BR) and English, using a free, open-source, local TTS
engine. Audio reaches the stream through an OBS Browser Source.

## Decisions (from brainstorming)

| Topic | Decision |
|---|---|
| Scope | Read every message, with filters and a bounded queue |
| Languages | Portuguese (BR) and mixed pt/en, detected per message |
| Hardware | NVIDIA GPU shared with the game, so TTS runs on CPU |
| TTS engine | Piper on CPU. Kokoro and Chatterbox are possible later behind the same interface |
| Audio path | OBS Browser Source plays the audio. OBS gives a separate volume and mute |
| App shape | Single Python process, hidden in the Windows system tray |
| Settings | Tray menu opens a local settings page in the default browser |
| Controls | Tray menu: Pause/Resume, Skip, Settings, Copy overlay URL, Quit |
| Extras | Message filters, optional username announcement |

## Architecture

```
Twitch IRC ─┐
            ├─► normalize ─► filter ─► lang-detect ─► queue ─► Piper (CPU) ─► WAV
YouTube ────┘     (Msg)       (rules)   (pt/en)     (bounded)               │
                                                                            ▼
Tray (Pause/Skip/Settings/Quit) ──► controller          FastAPI ──► /overlay (WebSocket)
                                                                            │
                                                                OBS Browser Source plays audio
```

Modules, one job each:

- `sources/twitch.py`, `sources/youtube.py`: yield `Msg(platform, user, text, ts)`.
  Twitch uses anonymous IRC over WebSocket (no login). YouTube uses `pytchat`
  (scraper, no API key). Each source is swappable.
- `filters.py`: pure function `Msg -> Msg | None`.
- `lang.py`: `lingua`, restricted to Portuguese and English. Low confidence or very
  short text uses the default voice.
- `tts.py`: wraps Piper. Returns WAV bytes. One pt-BR voice and one English voice.
- `player.py`: bounded queue, single worker, skip and pause.
- `server.py`: FastAPI bound to `127.0.0.1`. Serves `/overlay`, `/settings`,
  `/api/config`, and the overlay WebSocket.
- `tray.py`: pystray icon and menu.
- `config.py`: loads and validates `config.toml`.
- `web/overlay.html`, `web/settings.html`: plain HTML with a small script, no build step.

## Data flow (one message)

1. A source thread builds `Msg` and puts it through the pipeline.
2. Filters run in this order: bots and ignored users, `!commands`, links, repeats from
   the same user, emote spam, truncation to a max length. A dropped message ends here.
3. `lang.py` picks `pt` or `en`.
4. Text to speak: `"{user} disse: {text}"` (pt), `"{user} says: {text}"` (en), or only
   the text when the username announcement is off.
5. The bounded queue (default 20) takes it. When full, the oldest waiting message is dropped.
6. One worker thread takes the next message, runs Piper, and sends the WAV to the overlay.
7. The overlay plays it and replies `done`. The worker waits for `done` (timeout: audio
   length plus 2 s) before the next message, so lines never overlap.
8. Skip sends `stop` to the overlay and moves on. Pause stops the worker taking new items;
   messages keep queuing up to the cap.

Only one thread runs TTS, so CPU use stays predictable while gaming.

## Settings

- `GET /api/config` and `PUT /api/config`. PUT validates, writes `config.toml`, and
  reloads: filters and voices apply instantly; a changed Twitch channel or YouTube
  video ID reconnects that source.
- A test button speaks a sample line with the chosen voice.
- Settings: Twitch channel, YouTube video ID, voices, filter rules, queue size, max
  message length, username announcement, port, start with Windows (adds or removes a
  Startup shortcut).
- First run: if `config.toml` is missing, create it from `config.example.toml` and open
  the settings page.
- The server binds to `127.0.0.1` only. No secrets are stored in v1. If a YouTube API key
  is added later, it stays in the local `config.toml`.

## Error handling

| Failure | Behavior |
|---|---|
| Twitch disconnect | Reconnect with backoff (1 s up to 30 s); tray tooltip shows status |
| YouTube reader breaks or stream ends | Retry with backoff; after repeated failures mark it failed in the tray; Twitch keeps running |
| Bad channel or video ID | PUT rejects it with a message; old config stays active |
| Piper voice file missing | Tray notification naming the file; fall back to the other voice |
| One message fails in TTS | Log, skip, continue |
| Overlay not connected | Messages wait in the queue up to the cap; tray tooltip shows status |
| Overlay never sends `done` | Timeout, then the worker moves on |
| Corrupt config | Rename to `config.toml.bad`, load defaults, notify |
| Port in use | Notify with the port number; user changes it in config |

Logging: rotating log file, errors only by default; a `debug` setting logs every message.

## Testing

Automated (pytest, no network or audio):

- Filters: table-driven cases per rule, plus rule order.
- Language detection: pt, en, too-short lines, low-confidence fallback.
- Spoken-text building: username on and off, both languages.
- Queue: drop-oldest when full, pause, skip.
- Config: valid load, corrupt file recovery, rejected channel and video IDs.
- Sources: recorded sample lines produce the right `Msg`; backoff uses a fake clock.
- TTS: a fake engine in worker tests; one slow test runs real Piper and checks non-empty WAV.

Manual smoke checklist:

1. Tray icon appears, no console window.
2. Overlay URL added to OBS as a Browser Source; the settings test button is audible in OBS
   with its own volume slider.
3. Live Twitch chat, then live YouTube chat, a few minutes each.
4. Pause, Skip, Quit from the tray.
5. CPU use while a game runs.

## Project layout

```
TTS-test/
├─ pyproject.toml
├─ config.example.toml
├─ voices/                  # Piper voice files, git-ignored, downloaded on first run
├─ src/chatreader/
│  ├─ main.py
│  ├─ sources/{twitch,youtube}.py
│  ├─ filters.py  lang.py  tts.py  player.py  server.py  tray.py  config.py
│  └─ web/{overlay.html,settings.html}
├─ tests/
└─ docs/superpowers/specs/
```

Dependencies: `piper-tts`, `lingua-language-detector`, `pytchat`, `websockets`,
`fastapi`, `uvicorn`, `pystray`, `Pillow`; `pytest` for development.

## Running and distribution

- v1: run from source with `uv run chatreader`; a `pythonw` shortcut for daily use with
  no console window.
- v1.1 (easy install): PyInstaller folder build, zipped or wrapped with an Inno Setup
  installer. Voices download on first run to keep the package small. A true one-file
  `.exe` unpacks itself on every launch, so it starts slowly and triggers antivirus
  warnings more often.
- Tauri is not planned. It would only wrap a web UI around the same Python engine, which
  would still need bundling as a sidecar.
- Expect a bundle of a few hundred MB (`onnxruntime`, Piper, `lingua`). Restricting
  `lingua` to Portuguese and English reduces it.
- A tiny single binary would need a rewrite in Rust or Go around the Piper ONNX models.
  That is a separate project.

## Risks

- `pytchat` scrapes YouTube and can break when YouTube changes. `youtube.py` is isolated,
  and the official YouTube API is the fallback.
- Piper pt-BR voices are few (`faber` medium, `edresson` low) and sound robotic. Each
  voice has its own license; check the model card before choosing defaults.
- No Windows real-time benchmarks were found for Piper; verify CPU use in the smoke test.

## Out of scope for v1

Kokoro or Chatterbox engines, per-user voices, a queue viewer, moderation tools beyond
the filters, multiple channels at once, saved message history.

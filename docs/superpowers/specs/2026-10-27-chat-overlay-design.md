# Themed chat overlay (speech bubbles synced with the voice)

## Goal

A second OBS Browser Source, `/chat-overlay`, that draws a speech bubble for each chat message **at the moment
the voice starts reading it**. Looks come from theme folders, so a streamer can make a Deadlock-style overlay
(hero portrait per viewer, snappy animation) without ChatReader shipping anyone else's artwork.

The same read-only event stream that feeds the overlay is the "local events API" from the roadmap: other tools
can subscribe to it.

## Non-goals

- Animating a character's mouth to the audio.
- Online theme gallery or an automatic downloader for third-party images.
- Translating text.
- Showing messages that are never read (filtered, queue-dropped, removed): nothing appears for them.
- Changes to audio. `/overlay` and its WebSocket `/ws` keep working exactly as today.

## Decisions taken in the design talk

- Bubbles appear when the voice starts, not when the message arrives (so filtered messages never show).
- Themes are folders served by the local server; no hotlinking to the wiki. Valve artwork is never bundled
  or hosted by ChatReader; the Deadlock theme is a guide that tells the user which files to provide.
- Visual events are a separate broadcast channel with many clients; the audio `Hub` (one client) is untouched.

## Design

### Components

| Unit | Responsibility |
|---|---|
| `ViewHub` (`server.py`) | Keeps the set of `/ws/view` clients, `broadcast(dict)` from any thread, drops dead clients. |
| `Player` hooks (`player.py`) | Tells the app when an item starts and when it ends. |
| `Controller` (`controller.py`) | Builds the display payload for each queued message. |
| `themes.py` (new) | Finds built-in and user themes, validates `theme.toml`, resolves file URLs. |
| `web/chat-overlay.html`, `chat-overlay.js`, `chat-overlay.css` (new) | The Browser Source page. |
| Settings "Overlay" section | Theme, position, limits, URL to copy, test bubble. |

### Event stream: `/ws/view`

Text frames, JSON, server to client only (client messages are ignored). Passes the same `LocalOnly` check as `/ws`.
Up to 8 clients at once; a ninth is refused. There is no history: a client that connects late sees only new events.

```
{"t":"hello","v":1}                                  sent once on connect
{"t":"start","id":12,"platform":"twitch","user":"Fulano","text":"oi pessoal",
 "kind":"chat","detail":"","slot":2417785001,"lang":"pt"}
{"t":"end","id":12,"outcome":"played"}               played | failed | skipped
{"t":"config"}                                       settings were saved: refetch /api/overlay
```

`kind` and `detail` are the existing `Msg` fields (`chat`, or `bits`, `subs`, `gifts`, `raids`, `superchat`,
`members`). `text` is the viewer's message (already filtered and truncated), not the spoken sentence.
`slot` is a stable 32-bit number from `sha256(platform + ":" + user.lower())`, the same recipe as `voice_for`,
so a viewer keeps the same hero for good. `id` is the player's `QueueItem.id`.

### Player and Controller changes

- `QueueItem` gets `view: dict | None = None`; `Player.submit(text, lang, user="", voice="", view=None)`.
- `Player.__init__` gets `on_start: Callable[[QueueItem], None] | None`. It is called once per item, right
  before the first sentence's `output.play(wav)`, outside the lock, with the same error isolation as `_emit`.
  An item with no audio (every sentence failed) never starts, so it never shows.
- `on_event` already reports the end (`played`, `failed`, `skipped`, `removed`, `dropped`). Only
  `played`, `failed` and `skipped` for an item that started produce an `end` frame.
- `Controller.on_msg` builds `view` from the `Msg` that passed the filters. `speak_test` and previews pass no
  `view`, so they show no bubble.
- `main.py` wires `ViewHub.broadcast` to `on_start`/`on_event`. The overlay stream never blocks playback: a
  broadcast is fire-and-forget with a 1 s per-client send timeout.

### Themes

Folders in `%APPDATA%\ChatReader\themes\<name>\` (the data folder) plus one built-in theme `default`, packaged
under `src/chatreader/web/themes/default/`. A user theme may not use the name `default`. Names match
`[A-Za-z0-9_-]{1,40}`.

```
theme.toml
heroes/<hero>/<expression>.png     (png, jpg, webp, gif, svg)
fonts/<file>.woff2                 (woff2, otf, ttf)
```

```toml
name = "Deadlock"
author = "you"
font = "fonts/deadlock.otf"          # optional; system sans-serif if missing
[bubble]
background = "#FFEFD7"
color = "#111111"
radius = 5                           # px
animation = "snap"                   # fade | slide | snap | none
[heroes]
expressions = [{ name = "normal", chance = 0.7 }, { name = "gloat", chance = 0.1 }]
fallback = "normal"                  # used when a hero lacks the rolled expression
[events]
background = "#2b1b3d"
color = "#ffffff"
```

- **Hero per viewer:** the sorted list of hero folders; `hero = heroes[slot % len(heroes)]`.
- **Expression per message:** a random roll against `chance`; the rest of the weight goes to `fallback`.
- **No `heroes/`:** the theme has no portraits (bubble only). The built-in `default` draws a circle with the
  viewer's initial, colored from the slot.
- **Validation** (in `themes.py`, tested): bad TOML, missing fields, unknown animation, colors that are not
  `#rgb`/`#rrggbb`, and more than 200 images or any file over 5 MB make the theme invalid. An invalid theme is
  listed with its error in Settings and never selected; the overlay falls back to `default` with a log warning.
- **Serving:** `GET /themes/{name}/{path:path}` serves only the allowed extensions from inside that theme's folder.
  The resolved path must stay under the theme folder (rejects `..` and symlink escapes) or the answer is 404.

### Config (new keys, all in `Config` and validated)

| Key | Default | Rule |
|---|---|---|
| `overlay_theme` | `"default"` | theme name; an unknown name falls back to `default` at runtime |
| `overlay_position` | `"bottom-left"` | `top-left`, `top-right`, `middle-left`, `middle-right`, `bottom-left`, `bottom-right` |
| `overlay_max_bubbles` | `4` | 1 to 10 (the oldest bubble leaves first) |
| `overlay_hold_seconds` | `4` | 0 to 30 (time a bubble stays after its voice ends) |

`GET /api/overlay` returns these, the validated theme (colors, animation, font URL, hero list, expression
chances, image URLs) and `GET /api/themes` lists themes with their validation errors.

### The page: `/chat-overlay`

A transparent page (OBS Browser Source, recommended size 450 by 600; the page works at any size).

- Connects to `/ws/view`, reconnects every 2 s, and refetches `/api/overlay` on `hello` and on `config`.
- `start`: builds the bubble with `textContent` only (no HTML from chat), shows the portrait (or the initial
  circle) and runs the entry animation. Events (`kind != "chat"`) use the `[events]` colors and show the
  event line (for example "Fulano cheered 100 bits") above the message.
- While the clip plays the bubble is marked "speaking" (a CSS class themes can style).
- `end`: the bubble leaves after `overlay_hold_seconds` (immediately on `skipped`) with the exit animation.
- More than `overlay_max_bubbles` bubbles: the oldest leaves at once.
- A very long word wraps (`overflow-wrap: anywhere`); the bubble has a maximum width of 300 px.
- With `prefers-reduced-motion`, animations are `fade`.

### Settings (aba "Overlay")

Theme dropdown (invalid themes shown disabled with the error), position pills, steppers for the two limits,
the URL `http://127.0.0.1:<port>/chat-overlay` with a Copy button, and a **Test bubble** button
(`POST /api/view-test`, JSON body, sends a sample `start` then `end` to the connected overlays). Saving
settings broadcasts `{"t":"config"}`.

### Error handling

- No overlay connected: broadcasts do nothing; audio is unaffected.
- A client that errors or is slow is dropped; the page reconnects.
- A theme file that disappears after selection: the image 404s and the bubble shows the initial circle.
- Everything the page renders from the stream goes through `textContent`; theme colors are validated before
  they reach CSS custom properties.

### Docs

`docs/GUIDE.md` gets the Overlay section and a "Make a theme" page with the folder format and a step-by-step
**Deadlock theme guide** (names of hero folders, where to get portraits, and a note that the user must make sure
they may use those images; ChatReader does not provide them). `docs/STATUS.md` roadmap drops the text overlay.

### Tests

- `ViewHub`: broadcast reaches all clients, a dead client is removed, the ninth client is refused, a broadcast
  with no clients is a no-op, a slow client does not block others.
- Player: `on_start` fires once per item before the first `play`, not for an item whose synthesis failed, not
  for a skipped item before its audio; a failing `on_start` does not stop playback.
- Controller: `view` has the expected fields and the slot equals the `voice_for` hash input; test speak has no view.
- Themes: valid theme loads; every invalid case above is rejected with a message; `default` name is reserved;
  path traversal and symlink escapes return 404; disallowed extensions return 404.
- Config: new keys validate; unknown theme name falls back.
- Server: `/chat-overlay`, `/api/overlay`, `/api/themes`, `/ws/view` hello frame, `/api/view-test`.
- The repo has no JavaScript test runner, so the page script is not unit tested. It is kept small, and the
  Test bubble button plus a manual OBS check with Twitch and YouTube chat cover it.

### Phases

1. `ViewHub`, `/ws/view`, Player and Controller hooks, the page and the built-in theme.
2. Theme folders, validation, serving, config keys and the Settings section.
3. Emote images in bubbles (Twitch gives positions in the `emotes` tag) and the event styling polish.
4. Guides: "Make a theme" and the Deadlock theme.

Phases 1 and 2 are the first plan; 3 and 4 are separate plans.

## Out of scope for the first plan

Emote images (phase 3), the guides (phase 4), and any change to `/overlay` audio.

## Risks

- OBS's embedded browser is a Chromium build that may be older than the user's browser; the page uses only
  widely supported CSS and no build step.
- The audio `Hub` holds the queue until an audio overlay connects. The bubble overlay does not change that:
  with only `/chat-overlay` open and no audio source, nothing is read and nothing is shown.
- Windows and Twitch/YouTube behavior cannot be verified from automated tests; the OBS check stays manual.

# ChatReader control center: design

Date: 2026-10-19
Status: Draft for review

## Goal

Replace the separate dock and settings pages with one responsive app page that
shows the queue and status, a live console of chat activity and app log, and the
settings, with the tray controls (Pause, Skip, Copy overlay URL, Quit) available
on the page. It must work as a narrow OBS dock, a medium window and a full tab.

## Decisions (from brainstorming)

| Topic | Decision |
|---|---|
| Shape | One page at `/` with three tabs: Live, Console, Settings |
| Console content | Chat activity (with outcome and reason) plus the app log |
| Queue | View, remove one item, clear all |
| Live data transport | Polling with a cursor, no push connections |
| Settings | A tab, not an overlay. Sections collapse when narrow |
| Voices | Dropdown built from the model's real voice list, with preview |
| Privacy | Chat text lives in memory only, never written by this feature |
| Stack | Plain HTML, CSS and JS, no build step, local-only server |

## Out of scope

Reordering the queue, per-user voices, saved chat history, push (SSE or
WebSocket) updates, a native window, packaging as an exe, auto-pause rules.

## Architecture

```
/ (app page: Live | Console | Settings)
  ├─ GET  /api/status ─────────► Controller.snapshot()            (exists)
  ├─ GET  /api/queue ──────────► Player.snapshot()
  ├─ POST /api/queue/remove ───► Player.remove(id)
  ├─ POST /api/queue/clear ────► Player.clear()
  ├─ GET  /api/events?since=N ─► EventLog.since(N)
  ├─ POST /api/toggle ─────────► debug on/off (saved)
  ├─ POST /api/control ────────► pause | resume | skip | quit     (quit is new)
  ├─ GET  /api/voices ─────────► KokoroTTS.voices() grouped by language
  └─ GET/PUT /api/config, POST /api/test                           (exist)
/dock and /settings → serve the same page, opened on the right tab
```

Units, one job each:

- `events.py` (new): `EventLog`, the ring buffer, and `LogMirror`, a logging handler feeding it.
- `player.py`: queue items get ids; `snapshot()`, `remove(id)`, `clear()`.
- `controller.py`: records chat outcomes into the `EventLog`.
- `tts.py`: `KokoroTTS.voices() -> list[str]`.
- `server.py`: the new routes behind the existing `LocalOnly` guard.
- `web/app.html`, `web/app.css`, `web/app.js`: the page, split so no file grows past one job.
- `main.py`: wires the `EventLog`, the quit action and the log mirror.

## Event log

`EventLog(capacity=500)` is thread-safe and holds events
`{"id": int, "ts": float, "kind": "chat" | "app", "level": "debug" | "info" | "warn" | "error", ...}`.

- Chat events add `user`, `text` and `outcome`: `queued`, `played`, `failed`,
  `dropped` (queue full), or `skipped:<reason>` with reason one of
  `ignored user`, `command`, `link`, `no text`, `repeat`, `spam`.
- App events add `message` and `logger`. `LogMirror` copies records from the root
  logger. Debug records are included only while debug is on.
- `since(n) -> {"events": [...], "last": int}` returns events with `id > n`.
  If `n` is older than the buffer start, it returns what is left; the page
  shows no gap marker.
- Nothing is persisted by this feature.

To name the skip reason, `filters.apply` gets a sibling `explain(msg, cfg, state)`
that returns the reason, or `None` when the message passes. `apply` keeps its
signature and result, so behavior does not change.

## Queue

`Player` queue entries become `QueueItem(id: int, text: str, lang: str, user: str)`.

- `snapshot() -> {"playing": QueueItem | None, "waiting": [QueueItem, ...]}`.
- `remove(id) -> bool`: removes a waiting item. The playing item is ended with
  Skip, not removal. Unknown ids return `False`.
- `clear() -> int`: removes all waiting items and returns the count.
- `submit(text, lang, user="")` gains the optional `user`. Existing callers keep working.
- Chat events for `played`, `failed` and `dropped` are emitted from the player
  through an optional `on_event(item, outcome)` callback.

## Endpoints

All behind `LocalOnly` (local Host, matching Origin, `application/json` on POST).

| Route | Request | Response |
|---|---|---|
| `GET /api/queue` | none | the snapshot above |
| `POST /api/queue/remove` | `{"id": int}` | `{"ok": true}` or 404 |
| `POST /api/queue/clear` | `{}` | `{"removed": int}` |
| `GET /api/events?since=N` | query `since` (default 0) | the `since` result |
| `POST /api/toggle` | `{"name": "debug", "value": bool}` | `{"ok": true}`; unknown name 422 |
| `POST /api/control` | `{"action": ...}` adds `quit` | `{"ok": true}` |
| `GET /api/voices` | none | `{"pt": [...], "en": [...]}` |

- `toggle debug` sets the log level, mirrors it to `config.toml`, and updates
  `Config.debug` through `apply_config`.
- `quit` responds first, then stops the tray icon, so the page can show "ChatReader stopped".
- `/api/voices` groups by voice prefix: `p*` for Portuguese; `a*` and `b*` for
  English. Each entry is `{"id": "pf_dora", "label": "Dora (female)"}`. If the
  model is not loaded, both lists are empty and the page falls back to a text box.

## UI

### Structure

A sticky header (logo, live status text) and three tabs. The selected tab is kept
in the URL hash (`#live`, `#console`, `#settings`) and in `localStorage` (wrapped
in try/catch). `/dock` opens `#live`, `/settings` opens `#settings`.

### Live tab

- Status card: Twitch, YouTube, OBS overlay, voice model, each with a dot and a text label.
- Controls: Pause or Resume (label follows `paused`), Skip, Copy overlay URL, Quit.
  Quit needs two clicks (the label changes to "Really quit?" for 4 s).
  Copy uses `navigator.clipboard`; if refused, the URL is shown selected.
- Queue: the playing item, then waiting items in order, each with a remove button,
  and Clear all. The list polls `/api/queue` every second while the tab is visible.

### Console tab

- Polls `/api/events?since=<last>` every second while visible; keeps the last 500 lines.
- Lines show time, user and text, and an outcome tag (text plus color). Log lines
  show the level and message; warnings and errors are marked.
- Toolbar: filter chips All, Chat, Log; a Debug toggle; Pause scrolling; Clear view.
- Newest lines stay at the bottom until the user scrolls up, and then a
  "Jump to latest" button appears.
- All text is inserted with `textContent`.

### Settings tab

- The current sections (Sources, Voices, Reading, Ignored users, System) with the
  current save, dirty and error behavior, and the footer with Test voice and Save.
- Voices: a grouped dropdown per language filled from `/api/voices`, with the
  preview button. The dropdown holds only that language's voices. Fallback: a text box.
- Port, CPU threads and similar show "Restart required" as they do now.

### Responsive rules

| Width | Layout |
|---|---|
| 800 px and up | Live is two columns (status and controls left, queue right). Settings sections stacked. |
| 480 to 800 px | Single column. |
| Under 480 px | Compact header and tabs. Settings sections are collapsible, collapsed by default except the first. Console lines wrap. Works at 300 px with no horizontal scroll. |

Dark theme as today, system fonts, real labels, visible focus, and state is never
shown by color alone. No outside requests.

## Error handling

| Failure | Behavior |
|---|---|
| Server not reachable | Header shows "ChatReader not reachable"; polling continues |
| Remove for an unknown id (already played) | 404; the page refreshes the queue silently |
| Events cursor older than the buffer | Returns what remains |
| `/api/voices` empty (model not loaded) | Voice fields fall back to text boxes |
| Quit while a save is pending | Quit proceeds; unsaved edits are lost, as with the tray |
| Log mirror raises | Swallowed and never recurses into logging |

## Testing

Automated (pytest, no network or audio):

- `EventLog`: ids increase, `since` returns the right slice, capacity drops the oldest, thread safety under concurrent writers, debug records filtered when debug is off.
- `LogMirror`: records appear as app events; an exception inside the mirror does not propagate.
- `filters.explain`: one case per reason, matches `apply` for every case in the existing filter tests.
- Player: queue ids unique; `snapshot`, `remove` (waiting, unknown, playing), `clear`; `on_event` called with `played`, `failed`, `dropped`.
- Endpoints: each route including bad bodies (422), unknown ids (404), foreign Origin and non-JSON (403), `toggle` unknown name, `quit` calls the callback after responding.
- `/api/voices`: grouping with a fake voice list; empty when the model is missing.
- Pages: `/`, `/dock` and `/settings` serve the app; the HTML contains the tab and control ids.

Manual (by the author):

1. Load `/dock` in OBS at the dock's narrow width and go through all three tabs.
2. Send test messages from another account and check the console outcomes.
3. Remove a queued message and clear the queue.
4. Check the page at 300, 600 and 1000 px.

## Build order

1. `EventLog`, `LogMirror`, `filters.explain`.
2. Player queue ids, `snapshot`, `remove`, `clear`, `on_event`; controller records outcomes.
3. New endpoints and the `quit` action; `KokoroTTS.voices()` and `/api/voices`.
4. App shell: `app.html`, `app.css`, `app.js` with tabs, header, routing, polling helper.
5. Live tab.
6. Console tab.
7. Settings tab ported from the current page, with the voice dropdown and collapsible sections.
8. Route `/`, `/dock`, `/settings` to the app; remove the old pages; update the guide and README.

Each step keeps the full test suite green and ships on its own.

## Risks

- The player gets a second API surface (remove, clear) next to the prefetch
  logic that was reviewed for races. Removal only touches waiting items under the
  existing lock, and has its own tests.
- A 500-line feed in the browser is cheap, but the page must stop polling when
  its tab is hidden, or the OBS dock would poll while another dock is in use.
- Chat text appears in the console. It stays in memory, and is wiped by quit or
  Clear view.
- Replacing the settings page is a large move of working code. The port keeps the
  current behavior and the existing JS contract with `/api/config`.

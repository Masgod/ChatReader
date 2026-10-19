# ChatReader ease of use: design

Date: 2026-10-19
Status: Draft for review

## Goal

Make ChatReader easy to run on stream day for one streamer (the author): less to
type each stream, control from inside OBS, and a clear view of whether it works.
No installer, no auto-update, no public release in this round.

## Decisions (from brainstorming)

| Topic | Decision |
|---|---|
| Audience | Just the author. Setup stays `uv sync` and `uv run`. |
| In-OBS control | A compact page loaded as an OBS custom browser dock |
| Status | One JSON endpoint feeds the dock, the settings page and a first-run checklist |
| YouTube | Optional channel setting that finds the live video itself. Spike first |
| Speed | `speed` setting, sentence-level start-up, optional CPU thread setting |
| Kept as is | Local-only server on 127.0.0.1, CPU speech, OBS Browser Source audio, tray menu |

## Out of scope

Installer or auto-update, a native settings window, one-click OBS setup through
OBS WebSocket, direct output to an audio device, per-user voices, a queue viewer.

## Architecture

```
/dock (OBS dock) ──┐                    ┌── Controller.status()
/settings + banner ┼─► GET /api/status ─┤   sources, overlay, model, queue, paused
                   │                    └── Hub.connected, tts.ready, player.pending
/dock buttons ─────┴─► POST /api/control ─► Controller.pause / resume / skip
/dock fields ─────────► PUT /api/config (existing)
```

New or changed units, one job each:

- `controller.py`: `status()` returns the full status dict (see below).
- `tts.py`: `KokoroTTS.ready`, `speed` and `threads` handling.
- `server.py`: `GET /api/status`, `POST /api/control`, `GET /dock`.
- `web/dock.html`: the OBS dock page.
- `web/settings.html`: checklist banner, real status in the header, new fields.
- `config.py`: new keys and validation.
- `sources/youtube_live.py`: resolves a channel to its current live video ID.
- `sources/youtube.py`: waits for a live video when only a channel is set.

## Status endpoint

`GET /api/status` returns, and never raises:

```json
{
  "sources": {
    "twitch":  {"configured": true,  "state": "connected"},
    "youtube": {"configured": true,  "state": "waiting for live"}
  },
  "overlay": true,
  "model": "ready",
  "voices": {"pt": true, "en": true},
  "queue": 3,
  "paused": false
}
```

- `state` values: `off`, `starting`, `connected`, `reconnecting`, `failed`, `error`,
  and `waiting for live` (YouTube channel mode only). These come from the existing
  source status plus the new value.
- `overlay` is `Hub.connected`.
- `model` is `ready` when the Kokoro model is loaded, `missing` when the files are
  not on disk, `loading` while the first load runs, `error` when loading failed.
- `voices` says whether the configured Portuguese and English voice names exist in
  the model.
- `queue` is `Player.pending`.

The tray tooltip keeps using the same `Controller.status()` data.

## Control endpoint

`POST /api/control` with `{"action": "pause" | "resume" | "skip"}`. Unknown actions
return 422. It calls the matching `Controller` method and returns `{"ok": true}`.

Both new endpoints sit behind the existing `LocalOnly` middleware: local Host,
matching Origin, and `application/json` for POST.

## OBS dock page

`GET /dock` serves `web/dock.html`, designed for a panel about 360 px wide.

- Polls `/api/status` once per second. If the request fails, it shows "ChatReader
  not reachable" and keeps retrying.
- Four status rows (Twitch, YouTube, OBS overlay, Voice model) with a colored dot
  and a text label, so state is not shown by color alone. Queue length beside them.
- Buttons: Pause or Resume (label follows `paused`), Skip, Test voice.
- Speed slider (0.8 to 1.4) and a YouTube field (video link or channel handle).
  Changing either fetches `/api/config`, edits that one key, and sends the full
  config with `PUT /api/config`, as the settings page does. Errors from the PUT
  are shown under the field.
- A "Full settings" link opens `/settings` in a normal browser tab.
- Real labels on controls, visible keyboard focus, and layout that holds at 300 px.
- Setup instructions go in `docs/GUIDE.md`: Docks, Custom Browser Docks, URL
  `http://127.0.0.1:8765/dock`.

Two writers (dock and settings page) can edit the config. The last save wins. That
is acceptable for one user.

## Settings page changes

- The header status dot and text use `/api/status`, not the form values.
- A checklist banner above the sections, shown until all items are true:
  voice model ready, at least one source configured, overlay connected. A Test
  voice button is already in the footer, so a test result is not tracked.
- New fields: Speed, CPU threads (hint: restart required), YouTube channel.

## Config changes

| Key | Type | Default | Rule |
|---|---|---|---|
| `speed` | float | `1.0` | 0.8 to 1.4 inclusive |
| `cpu_threads` | int | `2` | 1 to 8. Replaces the `THREADS` constant. Applied on restart |
| `youtube_channel` | str | `""` | `@handle` (letters, digits, `_`, `.`, `-`) or a channel ID `UC` plus 22 characters. Normalized: a pasted channel URL is reduced to the handle or ID |

- The exact-type check in `server._type_errors` and `config._same_type` accepts an
  int for a float field (JSON writes `1` for `1.0`) but still rejects bool.
- `normalize` handles `youtube_channel` the same way it handles the video ID.
- `controller.apply_config` calls `tts.reload` when either voice or `speed` changed.
  `cpu_threads` changes show "restart required", like `port`.
- A changed `youtube_channel` restarts the YouTube source, like a changed video ID.

## Speed and start-up latency

- `KokoroTTS` keeps the speed from the config and passes it to `create`.
- Sentence start-up: the player splits a message into sentences and synthesizes the
  first one, then synthesizes the next while the first plays. Only one extra
  synthesis runs at a time, so CPU use stays bounded. The existing skip generation
  counter and shutdown checks apply to every clip.
- Measure before and after on the same sentences (time to first audio). If the
  gain is under about 30 percent for typical chat messages, drop the prefetch and
  keep only the speed setting.
- `cpu_threads` is the performance mode: the user raises it when no game is running.

## YouTube auto-detect

Spike first. The question: can the current live video of a channel be found
reliably without an API key? Probe: request `https://www.youtube.com/@handle/live`
and read the video ID from the redirect or the page, for a live and a non-live
channel, several times over a day. If it is not reliable, drop this part and
everything else still ships.

If it works:

- `sources/youtube_live.py` has `resolve_live_video(channel, fetch) -> str | None`.
  `fetch` is injectable so tests use recorded responses. It has a timeout, returns
  `None` when the channel is not live, and never raises.
- `run_youtube` gets the channel and the video ID. If the video ID is set, it is
  used and the channel is ignored. If only the channel is set, each session first
  calls the resolver. While the result is `None`, the status is `waiting for live`
  and it retries every 30 seconds, stopping promptly when the stop event is set.
- This path does not count toward `max_failures`, so waiting for a stream never
  marks the source as failed.

## Error handling

| Failure | Behavior |
|---|---|
| Status endpoint cannot read a value | Returns `error` or `false` for that field, still 200 |
| Dock cannot reach the server | Shows "ChatReader not reachable" and keeps polling |
| PUT from the dock is rejected | Shows the server's error messages under the field |
| Channel resolver fails or times out | Treated as not live, retried in 30 s |
| Invalid `speed`, `cpu_threads` or `youtube_channel` | 422 with a message, old config stays active |

## Testing

Automated (pytest, no network or audio):

- Status: values for each source state, overlay on and off, model states,
  paused, queue length; the endpoint never raises when a part throws.
- Control: each action calls the right method; unknown action gives 422; foreign
  Origin and non-JSON are rejected.
- Dock and settings pages are served as HTML.
- Config: new keys load, validate, normalize, and reject bad values; int accepted
  for `speed`; bool still rejected.
- Speed: passed to the fake Kokoro; reload triggered by a speed change only.
- Prefetch: clips play in order, skip and shutdown stop the pending synthesis.
- YouTube: resolver with recorded live and non-live responses; waiting loop retries
  and stops on the stop event; video ID wins over channel.

Manual (by the author):

1. Load `/dock` as an OBS custom browser dock and use every button during a stream.
2. Compare time to first audio before and after the prefetch change.
3. Watch CPU use during a game at `cpu_threads` 2.
4. The YouTube spike over a day, with a live and an offline channel.

## Build order

1. Status endpoint, control endpoint, `tts.ready`.
2. Dock page.
3. Settings page: real status and checklist banner.
4. Config keys, speed, `cpu_threads`.
5. Sentence prefetch, with a measurement gate.
6. YouTube spike, then the resolver and waiting loop if it passes.
7. Update `docs/GUIDE.md` and the README.

Each step ships on its own and keeps the full test suite green.

## Risks

- The YouTube live lookup is scraping and can break when YouTube changes. It is
  optional and isolated in one module.
- The prefetch adds concurrency to the player. The fix rounds on skip and shutdown
  in earlier tasks show these races are easy to get wrong, so it has its own tests
  and a measurement gate.
- Custom browser docks need a reasonably recent OBS. The author's version is not verified.
- The Portuguese Kokoro voices have no documented training data. Resolve this
  before relying on them on a monetized stream.

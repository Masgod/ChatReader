# YouTube live lookup spike

Date: 2026-10-19. Question: can the current live video of a channel be found without an API key?

## Probe

`GET https://www.youtube.com/@<handle>/live` with a desktop browser User-Agent and the cookie `CONSENT=YES+1`, following redirects. Two rounds, a few minutes apart, on three channels.

| Channel | State | HTTP | Canonical link in the page | `"isLiveNow"` |
|---|---|---|---|---|
| @LofiGirl | live | 200 | `https://www.youtube.com/watch?v=1-LpQekNa9g` | `true` (both rounds) |
| @NASA | live | 200 | `https://www.youtube.com/watch?v=M3HKLzjvKPc` | `true` |
| @google | not live | 200 | `https://www.youtube.com/channel/UCK8sQmJBp8GCxrOtXWBpyEA` | absent |

The URL does not redirect, so the redirect is no use. The signal is in the HTML: a live channel's canonical link is `watch?v=<id>` and the page contains `"isLiveNow":true`. An offline channel's canonical link is the channel URL. An offline page still contains other `"videoId"` values, so scanning for any video ID would give wrong answers.

## Decision

Reliable enough to build: return the ID only when the canonical link is a `watch?v=` link AND the page contains `"isLiveNow":true`; otherwise `None` (offline, upcoming or unparsable). Retry every 30 s.

## Not verified

- The agreed repeat at three times over a day was not done. Only two rounds a few minutes apart. The author should keep an eye on it for the first week; if YouTube changes the page, the resolver returns `None` and the manual video ID keeps working.
- No consent-page case was seen with the cookie set. Without it, EU consent pages may replace the content.

# ChatReader: agent instructions

Applies to every agent (Claude, Gemini, OpenCode models). `CLAUDE.md` only imports this file.

Windows tray app that reads Twitch and YouTube chat aloud with Kokoro TTS. Python 3.11+, uv, FastAPI + WebSocket overlay, pystray. Public repo (MIT, `LICENSE`; bundled GPL parts listed in `THIRD_PARTY_NOTICES.txt`).

## Where things are

- How it works, run, build: `docs/DEVELOPMENT.md`
- Config keys: `docs/CONFIGURATION.md`. Test status and known limits: `docs/STATUS.md`
- Code: `src/chatreader/` (sources in `sources/`, overlay/settings UI in `web/`). Tests: `tests/`
- Specs: `docs/superpowers/specs/`. Plans: `docs/superpowers/plans/`

## Gate (run before saying "done", paste the output)

```bash
uv sync
uv run pytest -q -m "not slow"     # CI runs exactly this on windows-latest
```

Passing = exit 0 and no failures. `-m slow` tests need the Kokoro model in `./voices` and are optional.
If you touched packaging: `uv run --group build python packaging/build.py`, then `dist/ChatReader/ChatReader.exe --check` must exit 0.

## Do not touch

- `config.toml`, `voices/`, `chatreader.log`, `stdio.log`, `build/`, `dist/`: local user data and build output.
- `THIRD_PARTY_NOTICES.txt` and the `licenses` bundle: change only together with a dependency change.

## Team workflow

- Plan in `docs/superpowers/plans/<date>-<feature>.md` with numbered checkbox tasks. Whoever executes a task ticks it and adds the commit hash.
- One task = one branch or worktree (`.claude/worktrees/`). Never commit straight to `main`.
- Public repo: free OpenCode models may work here. Never paste secrets, tokens or real chat logs.
- No merge without a review of the diff by the Arquiteto.

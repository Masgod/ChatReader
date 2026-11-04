# Voice Quality Plan (after 0.3.0)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the spoken chat sound right on stream: names and slang pronounced the way the streamer wants, and every voice at a similar loudness. Check two ideas from hangry-labs/kokoroTTS before building them.

**Architecture:** Two small text/audio stages in the existing path (`Controller.on_msg` → `spoken_text` → `Player` → `KokoroTTS.synth`). The pronunciation rules are applied to the final spoken string in the controller. Loudness is applied to the float samples in `KokoroTTS.synth` before the 16-bit conversion. Two further tasks are measurements with a go/no-go gate, not features.

**Tech Stack:** Python 3.11+, numpy (already used in `tts.py`), pytest.

**Spec:** none; the source is the comparison with https://github.com/hangry-labs/kokoroTTS (README read, code not read). Nothing is copied from it.

## Global Constraints

- No new dependency.
- Defaults must keep today's behaviour for anyone who changes nothing, except loudness, which is on by default (Task 2 states why).
- Pronunciation rules are user text: never executed, matched as plain text (escape every key), capped in size.
- Integration branch: `feat/voice-quality` (worktree `.claude/worktrees/voice-quality`). One branch per task (`voice/task-N-<slug>`) off it, merged back after the Arquiteto reviews the diff. Push to these branches is fine; push to `main`, tag or release only with the owner's explicit yes.

## Review Focus

- A rule key with regex characters (`c++`, `a.b`, `(x)`) must match literally, not as a pattern.
- A name ending the message, followed by punctuation or an emote (`kekw!`, `fulano,`) is still replaced.
- A rule must not rewrite part of a longer word (`bit` inside `bits`).
- Silence or a one-sample clip must not divide by zero or become a loud click.
- A very quiet clip must not be amplified into noise (gain cap), and a loud one must never clip.
- Portuguese accents and non-ASCII names (`João`, `Zé`) match.
- `Player` synthesizes one sentence at a time, so loudness is normalized per sentence: two sentences of the same message must not jump in level (test it).
- The Test button (`controller.py` `self._player.submit(text, lang, "test")`) also goes through the pronunciation rules, so the streamer can hear a rule before going live.

---

### Task 1: Pronunciation rules

**Files:**
- Create: `src/chatreader/pronounce.py`
- Modify: `src/chatreader/config.py`, `src/chatreader/controller.py`, `src/chatreader/web/app.html`, `src/chatreader/web/settings.js`, `src/chatreader/web/touchnav.js`, `config.example.toml`, `docs/CONFIGURATION.md`, `docs/GUIDE.md`
- Test: `tests/test_pronounce.py`, `tests/test_controller.py`, `tests/test_config_keys.py`, `tests/test_ui_style.py`

**Interfaces:**
- Produces: `apply_pronunciations(text: str, rules: dict[str, str]) -> str`; `Config.pronunciations: dict[str, str]` (default `{}`; TOML table `[pronunciations]`).

- [ ] **Step 1: Write `tests/test_pronounce.py`.** Cases: `("oi Zé", {"zé": "ze"}) → "oi ze"` (case-insensitive, accents); `("kekw!", {"kekw": "kek double you"})` replaced before `!`; `("bits", {"bit": "x"})` unchanged (whole word only); `("c++ rocks", {"c++": "see plus plus"})` literal; two keys where one contains the other (`"hi"`, `"hi there"`) → the longer one wins; empty rules returns the text untouched. Run `uv run pytest -q tests/test_pronounce.py`. Expected: FAIL (module missing).
- [ ] **Step 2: Implement `apply_pronunciations`.** One compiled pattern per call from the keys sorted longest first, each `re.escape`d, wrapped as `(?<!\w)(?:k1|k2)(?!\w)` with `re.IGNORECASE`; replacement looks the matched text up case-insensitively. Return the text unchanged when `rules` is empty. Run the same command. Expected: PASS.
- [ ] **Step 3: Config.** Add the field; `normalize` strips keys and values and drops empty ones; `validate` rejects more than 200 rules, a key over 40 characters, a value over 80, or control characters. Tests in `tests/test_config_keys.py`: round trip through TOML, the three limits, trimming. Run it red, then green.
- [ ] **Step 4: Controller.** Apply `apply_pronunciations(..., cfg.pronunciations)` to the string built by `spoken_text(...)` right before `self._player.submit(...)`, so announced user names are covered too; the overlay text (`view["text"]`) stays as typed. Test in `tests/test_controller.py`: a queued item's text has the replacement, the view text does not. Run the suite.
- [ ] **Step 5: UI.** New section `id="sect-pronunciations"` (two text inputs "Word" and "Say it as", an Add button, one chip per rule with a remove button, reusing the Ignored users chip code and styles), a "Pronunciations" page under the Voice group in `touchnav.js`. Static test in `tests/test_ui_style.py` that the section id exists and appears in `touchnav.js`. Look at it in the browser pane at 715×384 and 425×580.
- [ ] **Step 6: Docs and commit.** Document the table in `config.example.toml` and `docs/CONFIGURATION.md`, one paragraph in `docs/GUIDE.md`. Commit `feat: pronunciation rules`.

### Task 2: Loudness normalization

**Files:**
- Modify: `src/chatreader/tts.py`, `src/chatreader/config.py`, `src/chatreader/web/app.html`, `config.example.toml`, `docs/CONFIGURATION.md`
- Test: `tests/test_tts.py`

**Interfaces:**
- Produces: `normalize_loudness(samples: np.ndarray, target_rms: float = 0.1, max_gain: float = 2.5, peak: float = 0.97) -> np.ndarray`; `Config.normalize_volume: bool = True`.

Why on by default: different Kokoro voices come out at different levels, and a streamer cannot fix that per voice in OBS. A single RMS target with a gain cap changes the level but not the sound; it can be turned off.

- [ ] **Step 1: Write the tests.** Quiet clip (RMS 0.02) rises toward the target but by no more than `max_gain`; loud clip (RMS 0.3) is lowered to the target; all-zero clip and a 1-sample clip come back unchanged with no warning; output peak never exceeds `peak`; output dtype is float32. Add one test that `synth` calls it only when `normalize_volume` is true (inject a fake Kokoro that returns known samples). Run `uv run pytest -q tests/test_tts.py`. Expected: FAIL.
- [ ] **Step 2: Implement `normalize_loudness` and call it in `synth` before the int16 conversion** when `self._normalize` is set (read in `__init__` and in `reload(cfg)`, like `speed`). Gain = `min(target_rms / rms, max_gain)`; then scale down if the peak would pass `peak`. Run the suite.
- [ ] **Step 3: Config field, a switch in the Reading page ("Even out voice volume"), docs.** Look at the page in the browser pane.
- [ ] **Step 4 (owner): listen.** With the real model, send the same sentence in three different voices with the switch off and on. Expected: similar loudness on, noticeably different off. If the quiet voices turn into hiss, lower `max_gain` and say so in the commit.
- [ ] **Step 5: Commit** `feat: even out voice volume`.

### Task 3: Idle unload of the model (measure first)

**Files:**
- Modify (only if the gate passes): `src/chatreader/tts.py`, `src/chatreader/main.py`
- Test: `tests/test_tts.py`

- [x] **Step 1: Measure.** Start the app with the model loaded and idle; record the process working set (`Get-Process ChatReader | Select WorkingSet64`); stop, start with the model not loaded (rename the model file, or the `missing` state); record again. Also time the first synth after a load. Write both numbers in `docs/STATUS.md`. _(done, measured not worth it: 120 MB saving < 150 MB, voice/task-3-measure)_
- [x] **Step 2: Gate.** Build it only if the saving is at least 150 MB **and** the first-message delay stays under about 2 s. Otherwise record "measured, not worth it" in STATUS and stop; this task is then done. _(done, measured not worth it: 120 MB saving < 150 MB, voice/task-3-measure)_
- [ ] **Step 3 (only if the gate passes): write the failing tests.** After `idle_unload_minutes` with no `synth`, `_kokoro` is released and `model_state` becomes `ready` (unloaded) without breaking `voices()`; the next `synth` reloads it once, even with two threads asking at the same time; Settings still lists voices while unloaded (cache the voice list at load time). Then implement with a lock around load/unload and a timer checked from the player worker, setting `idle_unload_minutes: int = 0` (off by default).
- [ ] **Step 4: Commit** (code or the measurement note).

### Task 4: Confirm long text is safe

**Files:**
- Test: `tests/test_tts_long.py` (marked `slow`, skipped when the model is not downloaded)

- [x] **Step 1: Write the test.** `kokoro-onnx` already splits phonemes into batches of at most 510 (`MAX_PHONEME_LENGTH`); confirm it with a 900-character text without punctuation and `max_chars` raised in the config. Expected: a WAV longer than 20 s, no exception. (e1fd76e)
- [x] **Step 2: Run it** (`uv run pytest -q -m slow tests/test_tts_long.py`). (e1fd76e: 903 chars → 57.6 s WAV, no exception, 1 passed) If it raises, add the split in `player.split_sentences` by length and ledger the finding; if it passes, commit the test only.

### Task 5: Docs and release note

- [ ] **Step 1: Add the new settings to the Touch menu docs in `docs/GUIDE.md`, move the finished items out of the roadmap in `docs/STATUS.md`, bump the version if shipping as 0.4.0.**
- [ ] **Step 2: Run the suite and the build check** (`uv run pytest -q -m "not slow"`, `uv run --group build python packaging/build.py`, exe `--check`). Expected: all green, exit code 0.

## Left out on purpose

SSML and IPA overrides (too much for chat; the pronunciation table covers the real need), extra output formats, pitch control, Docker/CUDA, MCP endpoint, and the OpenAI-compatible HTTP endpoint (no stated need). New languages stay in the separate languages plan.

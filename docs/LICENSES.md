# Licences

ChatReader itself is MIT ([LICENSE](../LICENSE)). The components it uses have their own licences, listed in [THIRD_PARTY_NOTICES.txt](../THIRD_PARTY_NOTICES.txt).

## Voices and the voice model

The engine is Kokoro-82M. Its code (`kokoro-onnx`, MIT) and weights (Apache-2.0) are permissively licensed, and the model card says it was trained on permissive or non-copyrighted audio. The phonemizer that Kokoro needs (`phonemizer`, espeak-ng) is GPL-3.0: installing from source is fine, but redistributing a built zip that contains it carries GPL obligations (see `THIRD_PARTY_NOTICES.txt`).

- Not verified: where the training data of the individual Portuguese voices (`pf_dora`, `pm_alex`, `pm_santa`) comes from. The VOICES.md file does not document it. Ask the author (hexgrad) or get written legal advice before relying on it for a monetized stream.
- Phonemes come from espeak-ng (GPL-3.0+) through `kokoro-onnx`. This matters if you redistribute the app, not for the generated audio. This is not legal advice.
- An earlier version used Piper voices. Those were dropped because `en_US-lessac-medium` is under a research-only licence and the Portuguese Piper voices are finetuned from it.

Voices can be swapped in the settings page (`voice_pt`, `voice_en`). Model files are downloaded at runtime and are never committed (`voices/` is git-ignored).


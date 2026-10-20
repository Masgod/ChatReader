# Building ChatReader

```
uv run --group build python packaging/build.py
```

Output: `dist/ChatReader/ChatReader.exe`, `dist/ChatReader-<version>-win64.zip` and its `.sha256`.
Check the build with `Start-Process -Wait -PassThru dist\ChatReader\ChatReader.exe -ArgumentList '--check'` (the exe has no console: exit code 0 means ok, and the JSON line is saved as `check-result.json` in the data folder; add `--home <folder>` to choose it).

## Fewer antivirus false positives

- Keep the folder build (not a single file). Single-file exes unpack to a temp folder and look like malware.
- Optionally compile the PyInstaller bootloader yourself instead of using the prebuilt one: install the
  Visual Studio Build Tools (C++), then `uv pip install --no-binary pyinstaller --reinstall pyinstaller`.
  Stock bootloaders are the ones antivirus vendors fingerprint.
- Publish the `.sha256` file next to the zip.
- If a vendor flags a release, submit the zip to them as a false positive
  (Microsoft: https://www.microsoft.com/wdsi/filesubmission).
- Code signing is not set up. It is the real fix for SmartScreen, if the app is ever shared widely.

## Licences

The bundle contains GPL-3.0 components (phonemizer, espeak-ng). Read `THIRD_PARTY_NOTICES.txt` before
redistributing a build.

# Verification

Checked on Windows with Python 3.11.9, PySide6 6.12.0, httpx 0.28.1, and keyring 25.7.0.

- 40 tests run: **39 passed, 1 skipped**.
- Skipped: creating a Windows symbolic link requires a privilege unavailable to the test process. Other path escape and protected-folder checks passed.
- Desktop startup, Settings, chat submission, streamed simulated replies, merge orchestration, persistence, contribution storage, key exclusion from saved test data, and explicit denial of a proposed write were checked using hidden native Windows widgets.
- Welcome and simulated merge screenshots were rendered and visually reviewed. The merge screenshot is deliberately labelled as simulated.
- Real Gemini/Groq calls were not made: the owner has not configured API keys.
- Actual Docker execution was not tested: Docker is not installed in this environment. The no-Docker refusal and absence of host-code fallback were tested.
- Voice tests cover WAV encoding, transcription uploads and quota errors, simulated microphone capture/stop, missing-device handling, local transcript review, and exclusion of code/actions from spoken output. No actual microphone was recorded and no live transcription was sent.
- Theme tests cover all five palettes, Cancel restoration, and saved preferences.
- Update tests cover release validation, approved installations, checksum mismatch, unsafe redirects, path traversal and Windows archive paths, required files/version checks, history preservation, separate installation/activation, and stable-launcher selection. Real GitHub publication and downloading are checked separately after publishing.

Run again from this folder:

```powershell
..\.venv-kareem\Scripts\python.exe -m unittest discover -s tests -v
```

For a copied/downloaded installation, use your own `.venv\Scripts\python.exe` instead.

# Verification

Checked on Windows with Python 3.11.9, PySide6 6.12.0, httpx 0.28.1, and keyring 25.7.0.

- 68 tests run: **67 passed, 1 skipped** locally for version 0.3.1.
- Skipped: creating a Windows symbolic link requires a privilege unavailable to the test process. Other path escape and protected-folder checks passed.
- Desktop startup, Settings, chat submission, streamed simulated replies, merge orchestration, persistence, contribution storage, key exclusion from saved test data, and explicit denial of a proposed write were checked using hidden native Windows widgets.
- Welcome and simulated merge screenshots were rendered and visually reviewed. The merge screenshot is deliberately labelled as simulated.
- Real Gemini/Groq calls were not made: the owner has not configured API keys.
- Actual Docker execution was not tested: Docker is not installed in this environment. The no-Docker refusal and absence of host-code fallback were tested.
- Voice tests cover WAV encoding, transcription uploads and quota errors, simulated microphone capture/stop, missing-device handling, local transcript review, and exclusion of code/actions from spoken output. No actual microphone was recorded and no live transcription was sent.
- Theme tests cover all five palettes, Cancel restoration, and saved preferences.
- Update tests cover release validation, approved installations, checksum mismatch, unsafe redirects, path traversal and Windows archive paths, required files/version checks, history preservation, separate installation/activation, and stable-launcher selection. Real GitHub publication and downloading are checked separately after publishing.
- New checks verify that merge instructions preserve the original request and require natural answers, enumerate voices across languages while restoring the selected voice, preview a selected voice without saving, and persist the explicitly saved voice choice. Mocked model replies test orchestration; they do not establish live model wording.
- Read-only voice discovery on this PC found Microsoft David, Microsoft Mark, Microsoft Zira, and Microsoft Naayf (Arabic) with Windows' modern speech engine. No audio was played by that discovery check.
- Cloud-speech checks cover all 12 voice/model pairings, request-size/count bounds, multipart-independent JSON speech requests, PCM/WAV concatenation, invalid audio, missing keys, quota errors without retries/fallback, denied consent, cancellation, stale-result suppression, and in-memory PCM playback setup. Provider responses and speaker playback are mocked in the automated suite; no real Groq voice request was made.
- A separate native playback check sent 0.1 seconds of synthetic silence through the Logitech USB Headset using QAudioSink. Playback reached IdleState with NoError and the UI reported completion. The check used no microphone, cloud request, or audible speech. Qt audio status callbacks use no-argument slots to support the binding's legacy QAudio signal type name.
- A live diagnostic request with the app's saved Groq credential returned `model_terms_required` (HTTP 400). The credential was not printed, and no microphone/audio playback was used. New tests verify explicit setup guidance, fixed-host setup URLs for each selected model, no automatic retries, and exclusion of echoed private data from the error message. No model terms were accepted during diagnosis.
- After the owner completed model setup, a live response exposed Groq's unknown-length streaming WAV markers. Regression tests now cover that exact header shape, metadata padding, finite truncation, incomplete frames, and real duration limits. A further real Austin request decoded to 111,356 mono 16-bit frames at 24 kHz and completed muted headset playback with IdleState/NoError. Audio was kept in memory only, and the saved credential was never printed.
- Character tests cover all twelve distinct profiles and short previews, shared character instructions across both drafts and final Merge, single-provider Arabic style instructions, cloud-only picker contents, preview without saving, saved picker synchronization, and migration from an old Windows voice while preserving model/theme settings. Removed tests for the intentionally removed Windows voice discovery feature.
- Live Groq character checks with generic test prompts returned Austin as a practical builder and Diana as a concise strategist. These checks used the saved chat model and sent no conversation history, recorded audio, or personal files. The source and character settings screens were also rendered and visually checked with hidden native widgets.
- Error/recovery tests cover HTTP context failures, streamed quota/tool-generation failures, exclusion of private raw provider data, both-provider error summaries, interrupted/length-limited replies, and a manual Groq-only retry that sends no Gemini request, does not duplicate the last user message, and preserves the user's next draft. No saved chat content was replayed for these checks.

Run again from this folder:

```powershell
..\.venv-kareem\Scripts\python.exe -m unittest discover -s tests -v
```

For a copied/downloaded installation, use your own `.venv\Scripts\python.exe` instead.

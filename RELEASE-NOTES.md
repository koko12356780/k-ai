# Kareem AI 0.2.0

- Added push-to-talk voice input: choose a microphone, approve recording, stop, transcribe with Groq, review, then send.
- Added Windows spoken replies, Read aloud, Mute, automatic readout preference, installed voice selection, and speech speed.
- Added five saved themes: Night, Daylight, Ocean, Mint, and Rose, with immediate previews and Cancel restoration.
- Added Settings tabs for Models & keys, Appearance, Voice, and Updates.
- Added explicit GitHub update checks, release notes, SHA-256 verification, approved installation, and restart into a separate release folder.
- The launcher follows installed updates while keeping local chats and keys separate.
- Gemini and Groq Merge mode, saved conversations, and permission-gated file tools remain available.

Voice uses turn-based push-to-talk rather than a continuous live call. Groq audio quotas apply. Audio capture is local until upload is approved; speech output uses Windows voices. A working microphone and speaker are needed. Real microphone capture and live API transcription require verification on the user's device.

This is a Python desktop application, not a standalone EXE. Python 3.11+ and the listed dependencies are required; the launcher can set up dependencies on first run. Optional code execution requires Docker. Browser tools currently open approved links only.

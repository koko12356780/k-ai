# Kareem AI 0.3.0

- Removed Windows voice choices, Windows speech engine calls, local-voice discovery, and local-only speed/tone controls. All spoken replies now use Groq cloud voices.
- Added twelve fictional characters, one for each cloud voice. Each has a distinct description, conversational style, and in-character voice preview.
- Added a character picker in the chat header, linked to Settings → Voice and Voice mode.
- The selected character shapes Gemini drafts, Groq drafts, and the final Merge reply, as well as single-provider chat. Arabic characters default to Arabic while honoring explicit language requests.
- Assistant messages and contribution records keep the character used for that reply. Switching characters preserves conversation history and changes the style of subsequent replies.
- Old Windows voice selections migrate to Troy while preserving model choices, other preferences, and conversations. Existing valid cloud voice selections keep their matching character.
- Character style never changes tool permission gates, honesty, or accuracy requirements.

## Previous release: 0.2.4

- Fixed real Groq speech responses being rejected as unsupported audio.
- Groq returns streaming WAV headers with `0xffffffff` for RIFF/data sizes. The reader now resolves those markers from the bounded bytes received, instead of interpreting them as a recording billions of frames long.
- WAV metadata and padding are handled before reading audio. Finite truncated downloads, incomplete sample frames, invalid formats, oversized payloads, and genuinely excessive durations remain rejected.
- Added regression coverage for the real streaming header layout, metadata, synthesis integration, finite truncation, partial frames, and genuine long recordings.

Verified with a real Austin speech request: 111,356 frames at 24 kHz (4.64 seconds), successfully decoded and played through the native audio backend with volume set to zero before playback. No microphone was recorded, no audible speech was played, and no audio file was saved.

## Previous release: 0.2.3

- Fixed the opaque HTTP 400 error for Groq speech models that require terms acceptance.
- The app now recognizes `model_terms_required` and explains the necessary account setup without exposing raw error bodies or echoed keys/input.
- Added Groq voice setup links in Settings → Voice and Voice mode. Each link opens the selected model's official Groq playground.
- Users review and accept model terms themselves; the app never accepts legal agreements on their behalf.
- English and Arabic speech models may each require their own acceptance by the Groq organization administrator.

Diagnosis on this PC: one short live English speech request returned HTTP 400 with error code `model_terms_required`. No audio was recorded, played, or saved. Successful live speech generation remains pending the owner's decision about those terms.

## Previous release: 0.2.2

- Added 12 Groq Orpheus cloud voices, independent of Windows' installed voices.
- English: Troy, Autumn, Diana, Hannah, Austin, and Daniel.
- Arabic Saudi: Abdullah, Fahad, Sultan, Lulwa, Noura, and Aisha.
- Both Settings → Voice and Voice mode offer the cloud voice picker, previews, saved choices, and read-aloud support.
- Cloud speech asks for session consent before sending spoken text to Groq. It uses the saved Groq key and the account's quota/billing; no paid billing is enabled by the app.
- Cloud speech uses at most five requests per readout, up to 200 characters per request, and shortens long readouts to protect quota. Full answers remain visible in chat.
- Mute cancels pending speech generation and stops playback. Downloaded WAV audio stays in memory. Failed cloud speech does not silently switch to Windows voices.
- Cloud audio uses direct PCM playback without scanning media codecs. Speed and tone controls apply only to Windows voices.

Groq's preview speech models require account access and available quota. Free availability is not guaranteed for every account, and paid accounts may incur charges. No live speech API call was made during development; network and audio tests used simulated data. Install/update first, save your Groq key, select a Groq voice, and choose Try this voice to check your account's access.

## Previous release: 0.2.1

- Merge now answers the actual message naturally; it is instructed to avoid narrating draft comparisons unless asked. Model contributions remain inspectable separately.
- Added a reply-voice picker inside Voice mode, with Try this voice and Save voice controls.
- Settings → Voice automatically loads installed voices across all Windows languages, rather than showing only the current language.
- Added local voice previews and a deeper/brighter tone slider alongside speech speed.
- Returning to the default voice resets the previously selected voice. Existing saved voice names remain supported.
- Voice previews do not send data to an AI API or start the microphone. No additional speech service or subscription is required.

Voice choices depend on which voices are installed in Windows. Add more through Windows speech/language settings, then reload the list. AI reply style remains model-dependent; the updated instructions do not guarantee identical wording on every response.

## Previous release: 0.2.0

- Added push-to-talk voice input: choose a microphone, approve recording, stop, transcribe with Groq, review, then send.
- Added Windows spoken replies, Read aloud, Mute, automatic readout preference, installed voice selection, and speech speed.
- Added five saved themes: Night, Daylight, Ocean, Mint, and Rose, with immediate previews and Cancel restoration.
- Added Settings tabs for Models & keys, Appearance, Voice, and Updates.
- Added explicit GitHub update checks, release notes, SHA-256 verification, approved installation, and restart into a separate release folder.
- The launcher follows installed updates while keeping local chats and keys separate.
- Gemini and Groq Merge mode, saved conversations, and permission-gated file tools remain available.

Voice uses turn-based push-to-talk rather than a continuous live call. Groq audio quotas apply. Audio capture is local until upload is approved; speech output uses Windows voices. A working microphone and speaker are needed. Real microphone capture and live API transcription require verification on the user's device.

This is a Python desktop application, not a standalone EXE. Python 3.11+ and the listed dependencies are required; the launcher can set up dependencies on first run. Optional code execution requires Docker. Browser tools currently open approved links only.

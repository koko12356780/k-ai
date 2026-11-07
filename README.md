# Kareem AI

A Windows desktop workspace with **Gemini + Groq Merge mode**. The models run in the cloud; your PC runs the interface and any explicitly approved local tools. No local model or GPU is required.

## Start here

1. Double-click **Launch Kareem AI.bat**. Python 3.11 or later is required. First launch downloads the libraries if needed.
2. Open **Settings → Models & keys**.
3. Create keys at [Google AI Studio](https://aistudio.google.com/apikey) and [Groq Console](https://console.groq.com/keys). Paste them **inside the app**, never into a chat.
4. Click **Load models** for each provider. Select a text/chat model that your account offers on its free tier. Model lists include models that may not be appropriate for chat or free usage; discovery is not a free-tier guarantee.
5. Save, choose **Merge**, and send a message. Choose **Gemini** or **Groq** for a single-provider reply.

**Free accounts still have limits.** The app does not enroll you in subscriptions, enable billing, retry quota failures, or silently choose a different model. It cannot inspect your account's billing tier. If you enable paid billing at either provider, API requests may incur charges. Keep provider billing disabled to stay on free access. Free-tier eligibility, availability, and data policies are controlled by the providers.

## How Merge works

- One request goes to Gemini and one to Groq, concurrently, with the same conversation.
- A third request sends both drafts and the conversation to Gemini for synthesis.
- You see one combined answer and can inspect both drafts using **View model contributions**.
- If only one draft succeeds, it is clearly labelled as a single draft. If synthesis fails, the Gemini draft is shown with the same warning. No hidden retry or extra fallback request is made.
- Combining answers does not combine model weights, guarantee correctness, or bypass provider limits.

The first use of each mode asks for consent to send conversation content to its providers. Merge also shares Groq's draft with Gemini. Keys are sent only in authorization headers to the fixed official provider endpoints.

## Voice mode

Click **Voice**, choose your microphone, then **Record**. Recording starts only after approval. Click **Stop recording**, then **Transcribe with Groq** and approve the audio upload. Review/edit the transcript and click **Use transcript in message box**. Click **Send** when ready. This is push-to-talk, not a continuous live call.

Recordings stay in memory and are discarded when Voice closes. They are capped at 60 seconds and 12 MB. Groq's speech-to-text quota and data policies apply. Speech input uses `whisper-large-v3-turbo` by default; Settings → Voice also offers `whisper-large-v3`.

Click **Read aloud** for the latest reply or enable automatic spoken replies in **Settings → Voice**. Choose a **Groq** voice for cloud-generated speech, independent of Windows voices. English choices: Troy, Autumn, Diana, Hannah, Austin, Daniel. Arabic Saudi choices: Abdullah, Fahad, Sultan, Lulwa, Noura, Aisha. **Try this voice** previews the selection; Save keeps it. Voice mode has the same voice picker and Save voice controls.

Cloud voices use your saved Groq key and require Groq model access and quota. The first use each session asks for consent to send spoken text to Groq, including previews and automatic readout if enabled. The app does not enable paid billing or bypass quotas; accounts with paid billing may be charged. Check your provider dashboard for actual access, quota, and pricing. Requests stop on errors without automatic retries or an automatic Windows voice fallback. No model terms are automatically accepted on your behalf.

If Groq reports that model terms must be accepted, use **Settings → Voice → Groq voice setup**. This opens the selected model's official Groq playground. Review the terms and decide whether to accept them in your own account (the organization administrator may be needed), then retry **Try this voice**. English and Arabic models can require separate acceptance. The app does not make that decision for you.

Groq documents a 200-character request limit. Each readout is limited to five requests and roughly 1,000 characters; longer replies are shortened for speech and labelled in Activity, while the full chat reply stays visible. **Mute** cancels pending generation and stops playback. Already accepted requests may still count toward quota. Generated WAV audio remains in memory, with a 12 MB size limit, and is discarded when stopped or closed. Cloud audio plays directly as PCM without media codec scanning. Speed and tone adjustment apply only to Windows voices; cloud voices use their generated cadence.

**Windows** voice choices remain optional for local, offline output without a speech API call. The app discovers all installed Windows voice languages. Add more in Windows speech/language settings and reload. Microphone/speaker support depends on Windows devices and permissions. Automated tests simulate recording and cloud responses; real Groq speech still needs a check with your account.

Version 0.2.4 handles Groq's unknown-length streaming WAV headers using the actual received audio bytes, while retaining size, format, truncation, and duration checks. A real Austin response has been verified through generation, decoding, and muted native playback. Account access/quota still determines whether a particular request can be fulfilled.

## Themes

**Settings → Appearance** offers **Night, Daylight, Ocean, Mint, and Rose**. Changes preview immediately. Save persists the theme; Cancel restores the previous theme.

## Updates from GitHub

The public update home is [koko12356780/k-ai](https://github.com/koko12356780/k-ai/releases). Open **Settings → Updates → Check for updates**. If a newer stable release is available, review its notes, approve **Download & install update**, then choose **Restart into update**.

Downloads must come from that repository's release assets and match GitHub's SHA-256 asset digest and declared size. Archives are checked for path traversal, duplicate paths, links, unexpected version/format, and size limits before extraction. A checksum verifies download integrity; it does not protect against a compromised repository owner. Only install releases you trust from this repository.

New code is installed alongside previous code at `%LOCALAPPDATA%\KareemAI\releases\VERSION`, with `current.json` selecting the active release. The stable launcher follows this selection on future launches. Chat history, preferences, and Credential Manager keys are kept outside release packages. Checks/installations happen only when requested. There is no background update service. Version 0.1 had no updater, so use this version's launcher once to get the Updates screen.

The source updater reuses the existing Python environment. It does not silently install new dependencies. Future releases requiring a different environment must provide separate setup guidance. To return to the original source app, close the app and rename `current.json`; `previous.json` keeps the previous selection when available.

### Publishing a future update

Change the version in both `kareem_ai/__init__.py` and `bundle.json`, update `RELEASE-NOTES.md`, and publish the changes to the repository's main branch. The included GitHub Actions workflow tests on Windows, builds a curated ZIP, and publishes a new version's release. Existing releases are never silently overwritten. Failed tests prevent publication. The updater detects the new release when you next check.

For a local package: `python build_release.py`. Release assets use the name `Kareem-AI-vVERSION.zip` and include a SHA-256 sidecar. User histories, keys, virtual environments, and unrelated project files are excluded.

## Tools and permissions

Ask the AI to propose a file/tool action. Supported proposals appear as **Review action** buttons. A model cannot execute them directly.

| Tool | Behavior |
| --- | --- |
| List files | Lists up to 250 entries in the selected folder, after approval |
| Read text | Reads UTF-8 text up to 200 KB; result preview limited to 16,000 characters |
| Write/edit text | Shows a full diff; applies only after approval; refuses changed files and paths outside the approved folder |
| Run Python | Requires Docker Desktop and an already available `python:3.12-alpine` image; never falls back to running generated code on the host |
| Open link | Asks before opening an HTTPS URL in your default browser |

Tool results remain in a local preview. You can put a result in the message box, review it for secrets, and explicitly send it to the cloud. Choosing a folder does not upload its contents. `sources`, `.git`, `.codex`, `.agents`, and `.aws` paths are protected from model writes. Linked folders/junctions are rejected by file tools. Do not use file tools against folders being concurrently manipulated by another program; preview checks are not an OS security boundary against a malicious local process.

Python uses an offline, read-only container with no project files, environment secrets, or Docker socket mounted; capabilities are dropped, execution is limited to 15 seconds, 128 MB RAM, half a CPU, and 32 processes. Output retained by the app is capped at 16 KB. Docker is an additional local dependency, not cloud execution. Install Docker and obtain the image yourself only if you want this feature:

```powershell
docker pull python:3.12-alpine
```

Container isolation reduces risk but is not a guarantee against Docker/kernel vulnerabilities. Keep Docker updated. The app never automatically installs Docker or pulls the image.

## Current MVP boundaries

- Browser support opens approved links. Autonomous page reading, clicking, form submission, and browser sessions are **not implemented**.
- Code execution is optional and local inside Docker. A remote execution service is **not included**.
- Chat, model selection, two-draft merging, streamed final answers, Stop, local history, Markdown export, activity logs, approval previews, file tools, and optional container execution are implemented.
- Stop cancels in-flight client tasks, but a provider may already have accepted and counted a request. Approved file writes are not interrupted midway. Closing is blocked while work is active.
- No price guesses: streaming token usage is shown only when the API supplies it. Account quota/billing dashboards remain authoritative.
- Context is bounded at 42,000 characters per API request; very long chats need a new conversation. Model context and rate limits may be lower. Model output is capped at 2,048 tokens per request.
- Keys and live provider access are needed before real AI conversations work. Offline tests use simulated responses, not real models.

## Your data

Default location: `%LOCALAPPDATA%\KareemAI`.

- `settings.json`: model names only.
- `chats/`: locally saved messages and model contributions, unencrypted.
- `activity.jsonl`: timestamps, statuses, approvals, errors; no keys or file contents intentionally logged.
- API keys: Windows Credential Manager through `keyring`, or session-only if Remember is unchecked. Environment variables `GEMINI_API_KEY` and `GROQ_API_KEY` are also supported. Unchecking Remember removes previously saved keys for this app.

An optional `KAREEM_AI_DATA_DIR` environment variable changes the history/settings folder. API keys are not included in chat export. Messages you type or file contents you choose to send can contain secrets; review before sending.

## Developer setup and checks

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m kareem_ai
.\.venv\Scripts\python -m unittest discover -s tests -v
```

Tests cover request orchestration, synthesis, single-provider mode, quota/error handling, cancellation, discovery, context bounds, file previews and changed-file checks, path restrictions, denial, storage, and the desktop chat flow. UI tests use hidden Windows widgets and simulate APIs. Docker execution needs separate verification on a machine with Docker installed. Windows link tests may skip without symlink privileges.

## Provider references

- [Gemini OpenAI-compatible API](https://ai.google.dev/gemini-api/docs/openai)
- [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing) and [rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)
- [Groq OpenAI compatibility](https://console.groq.com/docs/openai) and [rate limits](https://console.groq.com/docs/rate-limits)
- [Groq speech-to-text](https://console.groq.com/docs/speech-to-text)
- [Groq Orpheus cloud voices](https://console.groq.com/docs/text-to-speech/orpheus)
- [GitHub release API](https://docs.github.com/en/rest/releases/releases)

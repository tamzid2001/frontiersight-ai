# Deep code review + execution prompt — Muse Voice Transcribe in Create Lab

## Part A — Deep code review (of the exact surface this touches)

Scope re-read: Create Lab generate flow (`apps/web/app.js` generate handlers,
`integrations/meta/spark.py:generate_scene/validate_scene/scene_quality`,
`services/api/server.py` `/api/meta/scene`, `.env.example`, rate limiting).

1. **Input contract is now sound.** Prompt limit is 4,000 chars enforced
   client-side (counter + pre-flight message) and server-side (HTTP 400 with
   the real reason, not a fake "model failed"). Generated scenes are
   schema-validated and engine-scored with one feedback retry. Voice input
   must enter through this same contract — a transcript is just text that
   lands in the existing textarea and obeys the same limits.
2. **The model boundary is honest today and must stay that way.** Offline =
   `OFFLINE_HEURISTIC`, live = `MODEL_DERIVED`, blocked = named error.
   Voice adds three new provenance labels that must never blur:
   `META_TRANSCRIBED` (Muse Voice Transcribe), `BROWSER_ASR` (Web Speech
   API fallback), `TYPED` (keyboard). A transcript is a *draft*: it fills
   the textarea for editing and is never auto-submitted to scene generation.
3. **Format reality (from Meta's docs, verified 2026-10-27):** the file
   endpoint `POST /v1/asr/transcribe` accepts **only RIFF/WAVE, mono,
   16-bit PCM at 16/24 kHz**, multipart (`request` JSON part + `audio`
   part), ≤32 MB, ≤10 min; response `{sessionId, transcript,
   audioDurationMs, turns[]}`. Browsers record WebM/Opus or MP4 — both are
   rejected by Meta as-is. Therefore audio must be decoded with Web Audio
   (`decodeAudioData`), down-mixed, resampled to 24 kHz and re-encoded as
   WAV **in the browser** before upload. Any design that posts MediaRecorder
   output directly is wrong.
4. **Realtime (WSS) is explicitly out of scope for v1.** It needs real-time
   pacing, handshake auth and a stateful proxy our stateless serverless API
   shouldn't pretend to be. The file endpoint with push-to-talk UX gives
   the same user outcome honestly. Documented as the future path.
5. **Privacy & consent gaps to close:** microphone use needs a pre-flight
   explanation (Mobbin pattern: expectations before a permission prompt),
   recording must be visibly indicated with elapsed time, audio is
   transmitted to Meta only on Stop (never streamed, never stored server
   -side), and the UI must say so in one sentence next to the mic button.
6. **Server seams already exist:** `/api/meta/*` carries a 30/min/client
   quota (paid-endpoint protection), the 12 MB JSON ingest cap bounds a
   base64 WAV to ~2 minutes at 24 kHz mono (plenty for a scene prompt),
   `MODEL_API_KEY` stays server-side, and error taxonomy (400 client /
   502 model / 202 blocked) is established. Voice slots into all of it.
7. **Cost truth:** $0.18/hour of audio (Meta docs) — a 10-second dictation
   costs fractions of a cent; show recorded seconds, never invent a bill.

## Part B — Execution prompt (what was built)

> **Role:** senior media/ML integration engineer. Add voice dictation to
> FrontierSight's Create Lab prompt box using **Muse Voice Transcribe
> (`muse-voice-transcribe-1.0`)** through Meta Model API, correctly and
> honestly, without disturbing the typed flow.
>
> **Flow:** user taps 🎙 → permission priming line appears → recording
> state (pulsing indicator, elapsed timer, 120 s cap) → Stop →
> browser decodes the recording (Web Audio), down-mixes to mono,
> resamples to 24 kHz, encodes 16-bit PCM WAV → `POST /api/meta/transcribe`
> (server proxies multipart to Meta with the server-side key) →
> transcript + turns + duration return → text lands **in the existing
> prompt textarea for editing**, counter updated, source chip shows
> “Heard via Muse Voice Transcribe · N s of audio”. Generate scene
> then works exactly as typed, including quality scoring and retry.
>
> **Accuracy rules:** Meta's documented constraints are enforced, not
> approximated (WAV-only validated by RIFF header server-side; mode
> `PUSH_TO_TALK`; optional `languageBias` from a small language select;
> domain keywords biased: forklift, pedestrian, robot, shelf, aisle,
> counterfactual). Meta 400/429/5xx map to precise user messages with the
> session id for support. If Meta is unconfigured or fails, offer the
> browser's Web Speech API as a **separately labelled** fallback
> (`BROWSER_ASR`) where available — never present it as Meta output.
> Denied microphone permission produces instructions, not a dead button.
>
> **Anti-goals:** no realtime WebSocket proxy, no audio storage, no
> auto-submit, no word-level timestamps (Meta doesn't provide them),
> no claiming diarization we don't request.

## What shipped (0.31.0)

- `integrations/meta/voice.py` — multipart client for
  `POST /v1/asr/transcribe`, WAV validation, timeout/retry bounds,
  precise error mapping.
- `POST /api/meta/transcribe` — base64 WAV in (12 MB cap applies),
  Meta transcript out, inherits the 30/min model quota.
- Create Lab: mic button with priming, recording timer, browser-side
  Web Audio decode → 24 kHz mono WAV encode, transcript-to-textarea
  with provenance chip, language select, Web Speech fallback labelled
  `BROWSER_ASR`, 120 s recording cap.
- Verified live 2026-10-27: macOS `say` synthesized *"A forklift crosses the warehouse aisle while a pedestrian walks the other way"* to 24 kHz WAV; the real model returned *"a forklift crosses the warehouse aisle while a pedestrian walks the other way.!"* — 4,320 ms of audio transcribed in 1,199 ms, session `fs-5849d94d…`.

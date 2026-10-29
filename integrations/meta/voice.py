"""Muse Voice Transcribe via Meta Model API — file transcription.

Verified against dev.meta.ai/docs/speech-to-text (2026-10-27):
POST https://api.meta.ai/v1/asr/transcribe, multipart/form-data with a
`request` JSON part and an `audio` part. The endpoint accepts ONLY
RIFF/WAVE, mono, 16-bit integer PCM at 16 kHz or 24 kHz (browsers record
WebM/MP4, so clients must decode + resample + re-encode — the Create Lab
does exactly that with Web Audio before anything reaches this module).
Limits: 32 MB body, 10 minutes of audio. $0.18 per audio hour.
Response: {sessionId, transcript, audioDurationMs, turns[]} — turns only
carry data in ENDPOINTING/DIARIZATION modes; we use PUSH_TO_TALK.
"""
from __future__ import annotations
from .credentials import api_key
import json, os, struct, time, urllib.request, urllib.error, uuid
from .spark import BlockedCredentials, ModelError, BASE

MODEL = os.environ.get("META_VOICE_MODEL", "muse-voice-transcribe-1.0")
DOMAIN_KEYWORDS = ["forklift", "pedestrian", "robot", "cyclist", "vehicle",
                   "shelf", "aisle", "warehouse", "counterfactual", "near miss"]

def validate_wav(data: bytes) -> dict:
    """RIFF/WAVE mono 16-bit PCM check. Returns stream facts; raises ValueError
    with the precise reason (never a vague 'bad audio')."""
    if len(data) < 44 or data[0:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("audio must be a WAV file (RIFF/WAVE) — decode and re-encode in the browser first")
    audio_format, channels, rate, _, _, bits = struct.unpack_from("<HHIIHH", data, 20)
    if audio_format != 1: raise ValueError("WAV must be integer PCM (format 1)")
    if channels != 1: raise ValueError("WAV must be mono")
    if bits != 16: raise ValueError("WAV must be 16-bit")
    if rate not in (16000, 24000): raise ValueError("WAV sample rate must be 16000 or 24000 Hz")
    if len(data) > 30 * 1024 * 1024: raise ValueError("audio exceeds the 30 MB transcription bound")
    return {"sample_rate": rate, "channels": channels, "bits": bits, "bytes": len(data)}

def transcribe_wav(wav: bytes, mode: str = "PUSH_TO_TALK", language_bias: list | None = None,
                   keywords: list | None = None, timeout: int = 120) -> dict:
    key = api_key()
    if not key: raise BlockedCredentials("BLOCKED_CREDENTIALS: MODEL_API_KEY not set (server-side only)")
    facts = validate_wav(wav)
    if mode not in ("PUSH_TO_TALK", "ENDPOINTING", "DIARIZATION"):
        raise ValueError(f"unknown mode: {mode}")
    session_id = f"fs-{uuid.uuid4()}"
    settings = {"mode": mode, "model": MODEL, "audioEncoding": "WAV",
                "keywords": (keywords or []) + [k for k in DOMAIN_KEYWORDS if k not in (keywords or [])]}
    if language_bias: settings["languageBias"] = language_bias
    boundary = "----frontiersight" + uuid.uuid4().hex[:16]
    body = b""
    body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"request\"\r\nContent-Type: application/json\r\n\r\n".encode()
    body += json.dumps(settings).encode() + b"\r\n"
    body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"audio\"; filename=\"dictation.wav\"\r\nContent-Type: audio/wav\r\n\r\n".encode()
    body += wav + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(f"{BASE}/asr/transcribe?sessionId={session_id}", data=body, method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": f"multipart/form-data; boundary={boundary}"})
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:300]
        if e.code == 429: raise ModelError(f"Meta transcription rate limit (429) — wait a few seconds and retry. session {session_id}") from e
        if e.code == 400: raise ValueError(f"Meta rejected the audio (400): {detail}") from e
        raise ModelError(f"Meta transcription HTTP {e.code} (session {session_id}): {detail}") from e
    return {"transcript": out.get("transcript", ""), "turns": out.get("turns", []),
            "audio_duration_ms": out.get("audioDurationMs"),
            "session_id": out.get("sessionId", session_id), "model": MODEL,
            "source": "META:muse-voice-transcribe-1.0",
            "latency_ms": round((time.time() - started) * 1000), "wav": facts}

#!/usr/bin/env python3
"""A bounded OpenAI-shaped HTTP adapter for the hosted Brainiall TTS API.

This is deliberately a partial compatibility layer: it accepts the common
``POST /v1/audio/speech`` JSON shape, but it returns WAV only, does not stream,
does not implement OpenAI model semantics, and never retries a metered call.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import wave
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


DEFAULT_UPSTREAM_URL = "https://api.brainiall.com/v1/tts/synthesize"
DEFAULT_VOICE = "pf_dora"
MAX_REQUEST_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 50 * 1024 * 1024
MAX_TEXT_CHARACTERS = 5_000
UPSTREAM_TIMEOUT_SECONDS = 120


class AdapterError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = int(status)
        self.message = str(message)


@dataclass(frozen=True)
class WavMetadata:
    channels: int
    sample_rate_hz: int
    bits_per_sample: int
    frames: int


def parse_wav_metadata(audio: bytes) -> WavMetadata:
    if len(audio) < 44 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        raise AdapterError(HTTPStatus.BAD_GATEWAY, "upstream did not return a WAV file")
    try:
        with wave.open(io.BytesIO(audio), "rb") as reader:
            if reader.getcomptype() != "NONE":
                raise AdapterError(
                    HTTPStatus.BAD_GATEWAY,
                    "upstream WAV compression is not supported by this adapter",
                )
            metadata = WavMetadata(
                channels=reader.getnchannels(),
                sample_rate_hz=reader.getframerate(),
                bits_per_sample=reader.getsampwidth() * 8,
                frames=reader.getnframes(),
            )
    except (EOFError, wave.Error) as exc:
        raise AdapterError(HTTPStatus.BAD_GATEWAY, "upstream returned an invalid WAV file") from exc
    if metadata.channels < 1 or metadata.sample_rate_hz < 1 or metadata.bits_per_sample < 1:
        raise AdapterError(HTTPStatus.BAD_GATEWAY, "upstream returned invalid WAV metadata")
    return metadata


def normalize_request(value: object, default_voice: str = DEFAULT_VOICE) -> dict[str, object]:
    if not isinstance(value, dict):
        raise AdapterError(HTTPStatus.BAD_REQUEST, "request body must be a JSON object")

    text = value.get("input")
    if not isinstance(text, str) or not text.strip():
        raise AdapterError(HTTPStatus.UNPROCESSABLE_ENTITY, "input must be a non-empty string")
    if len(text) > MAX_TEXT_CHARACTERS:
        raise AdapterError(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            f"input must contain at most {MAX_TEXT_CHARACTERS} characters",
        )

    requested_format = str(value.get("response_format", "wav") or "wav").lower()
    if requested_format != "wav":
        raise AdapterError(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "this partial adapter supports response_format=wav only",
        )

    voice = value.get("voice", default_voice)
    if not isinstance(voice, str) or not voice.strip() or len(voice) > 128:
        raise AdapterError(HTTPStatus.UNPROCESSABLE_ENTITY, "voice must be a non-empty string")
    if any(character in voice for character in "\r\n"):
        raise AdapterError(HTTPStatus.UNPROCESSABLE_ENTITY, "voice must be single-line")

    speed = value.get("speed", 1.0)
    if isinstance(speed, bool) or not isinstance(speed, (int, float)):
        raise AdapterError(HTTPStatus.UNPROCESSABLE_ENTITY, "speed must be a number")
    speed = float(speed)
    if not 0.5 <= speed <= 2.0:
        raise AdapterError(HTTPStatus.UNPROCESSABLE_ENTITY, "speed must be between 0.5 and 2.0")

    return {"text": text, "voice": voice.strip(), "speed": speed}


def validate_upstream_url(value: str) -> str:
    parsed = urlparse(str(value or ""))
    if value == DEFAULT_UPSTREAM_URL:
        return value
    if (
        parsed.scheme == "http"
        and parsed.hostname in {"127.0.0.1", "localhost"}
        and parsed.port is not None
        and parsed.path
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
    ):
        return value
    raise AdapterError(
        HTTPStatus.INTERNAL_SERVER_ERROR,
        "BRAINIALL_TTS_UPSTREAM_URL must be the production endpoint or an explicit loopback fixture",
    )


def resolve_api_key(headers: Mapping[str, str]) -> str:
    configured = os.environ.get("BRAINIALL_API_KEY", "").strip()
    if configured:
        return configured
    authorization = str(headers.get("Authorization", ""))
    if authorization.lower().startswith("bearer "):
        forwarded = authorization[7:].strip()
        if forwarded:
            return forwarded
    raise AdapterError(
        HTTPStatus.UNAUTHORIZED,
        "set BRAINIALL_API_KEY or send a Brainiall API key as a Bearer token",
    )


def call_upstream(payload: dict[str, object], api_key: str, upstream_url: str) -> tuple[bytes, WavMetadata]:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = Request(
        upstream_url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "audio/wav",
            "User-Agent": "brainiall-openai-tts-adapter/1.0",
        },
    )
    try:
        with urlopen(request, timeout=UPSTREAM_TIMEOUT_SECONDS) as response:
            declared_size = response.headers.get("Content-Length")
            if declared_size and int(declared_size) > MAX_RESPONSE_BYTES:
                raise AdapterError(HTTPStatus.BAD_GATEWAY, "upstream WAV exceeds the response limit")
            audio = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        if exc.code in {401, 403}:
            message = "Brainiall authentication failed"
        elif exc.code == 402:
            message = "Brainiall credits are insufficient"
        elif 400 <= exc.code < 500:
            message = "Brainiall rejected the synthesis request"
        else:
            message = "Brainiall TTS is temporarily unavailable"
        raise AdapterError(exc.code if 400 <= exc.code <= 599 else 502, message) from exc
    except (OSError, URLError, TimeoutError, ValueError) as exc:
        raise AdapterError(HTTPStatus.BAD_GATEWAY, "Brainiall TTS is temporarily unavailable") from exc

    if len(audio) > MAX_RESPONSE_BYTES:
        raise AdapterError(HTTPStatus.BAD_GATEWAY, "upstream WAV exceeds the response limit")
    return audio, parse_wav_metadata(audio)


class AdapterHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "BrainiallOpenAITTSAdapter/1.0"

    def log_message(self, _format: str, *_args: object) -> None:
        # Request text and credentials must never be copied into default logs.
        return

    def _send_json(self, status: int, body: dict[str, object]) -> None:
        encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path.rstrip("/") != "/health":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        self._send_json(
            HTTPStatus.OK,
            {
                "status": "ok",
                "upstream": "not_called",
                "compatibility": "partial-openai-audio",
                "output_format": "wav",
                "streaming": False,
                "retries": 0,
            },
        )

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path.rstrip("/") != "/v1/audio/speech":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        try:
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                raise AdapterError(HTTPStatus.LENGTH_REQUIRED, "Content-Length is required")
            content_length = int(raw_length)
            if content_length < 1 or content_length > MAX_REQUEST_BYTES:
                raise AdapterError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request body is too large")
            raw_body = self.rfile.read(content_length)
            try:
                value = json.loads(raw_body)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise AdapterError(HTTPStatus.BAD_REQUEST, "request body must be valid JSON") from exc

            default_voice = os.environ.get("BRAINIALL_DEFAULT_VOICE", DEFAULT_VOICE).strip() or DEFAULT_VOICE
            payload = normalize_request(value, default_voice=default_voice)
            api_key = resolve_api_key(self.headers)
            upstream_url = validate_upstream_url(
                os.environ.get("BRAINIALL_TTS_UPSTREAM_URL", DEFAULT_UPSTREAM_URL)
            )
            audio, metadata = call_upstream(payload, api_key, upstream_url)
        except AdapterError as exc:
            self._send_json(exc.status, {"error": exc.message})
            return
        except (OverflowError, ValueError):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid Content-Length"})
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(audio)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Audio-Sample-Rate", str(metadata.sample_rate_hz))
        self.send_header("X-Audio-Channels", str(metadata.channels))
        self.send_header("X-Audio-Bits-Per-Sample", str(metadata.bits_per_sample))
        self.send_header("X-Brainiall-Voice", str(payload["voice"]))
        self.send_header("X-Brainiall-Compatibility", "partial-openai-audio")
        self.end_headers()
        self.wfile.write(audio)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv if argv is not None else sys.argv[1:]))
    if not 1 <= args.port <= 65_535:
        raise SystemExit("--port must be between 1 and 65535")
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        print(
            "warning: binding this metered adapter beyond loopback requires your own TLS, auth, and rate limits",
            file=sys.stderr,
        )
    server = ThreadingHTTPServer((args.host, args.port), AdapterHandler)
    print(f"Brainiall partial OpenAI TTS adapter listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

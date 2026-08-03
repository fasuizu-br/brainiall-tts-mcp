from __future__ import annotations

import importlib.util
import io
import json
import os
import pathlib
import sys
import threading
import unittest
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from unittest.mock import patch


MODULE_PATH = pathlib.Path(__file__).with_name("adapter.py")
SPEC = importlib.util.spec_from_file_location("brainiall_openai_tts_adapter", MODULE_PATH)
assert SPEC and SPEC.loader
adapter = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = adapter
SPEC.loader.exec_module(adapter)


def wav_fixture(sample_rate: int, channels: int = 1, sample_width: int = 2) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(sample_width)
        writer.setframerate(sample_rate)
        writer.writeframes(b"\x00" * sample_width * channels * 16)
    return output.getvalue()


class WavMetadataTests(unittest.TestCase):
    def test_reads_rate_channels_and_bits_from_wav_header(self) -> None:
        metadata = adapter.parse_wav_metadata(wav_fixture(44_100, channels=2))
        self.assertEqual(metadata.sample_rate_hz, 44_100)
        self.assertEqual(metadata.channels, 2)
        self.assertEqual(metadata.bits_per_sample, 16)

    def test_rejects_non_wav_bytes(self) -> None:
        with self.assertRaises(adapter.AdapterError) as context:
            adapter.parse_wav_metadata(b"not a wav")
        self.assertEqual(context.exception.status, 502)


class RequestContractTests(unittest.TestCase):
    def test_maps_openai_shaped_request_to_brainiall(self) -> None:
        result = adapter.normalize_request(
            {
                "model": "tts-1",
                "input": "Uma frase curta.",
                "voice": "pf_dora",
                "response_format": "wav",
                "speed": 1.25,
            }
        )
        self.assertEqual(
            result,
            {"text": "Uma frase curta.", "voice": "pf_dora", "speed": 1.25},
        )

    def test_defaults_voice_but_not_output_format_beyond_wav(self) -> None:
        self.assertEqual(adapter.normalize_request({"input": "hello"})["voice"], "pf_dora")
        with self.assertRaises(adapter.AdapterError) as context:
            adapter.normalize_request({"input": "hello", "response_format": "mp3"})
        self.assertEqual(context.exception.status, 422)

    def test_rejects_oversized_text_and_invalid_speed(self) -> None:
        with self.assertRaises(adapter.AdapterError):
            adapter.normalize_request({"input": "x" * 5_001})
        with self.assertRaises(adapter.AdapterError):
            adapter.normalize_request({"input": "hello", "speed": 4})


class UpstreamBoundaryTests(unittest.TestCase):
    def test_accepts_production_and_loopback_only(self) -> None:
        self.assertEqual(
            adapter.validate_upstream_url(adapter.DEFAULT_UPSTREAM_URL),
            adapter.DEFAULT_UPSTREAM_URL,
        )
        self.assertEqual(
            adapter.validate_upstream_url("http://127.0.0.1:9080/tts"),
            "http://127.0.0.1:9080/tts",
        )
        with self.assertRaises(adapter.AdapterError):
            adapter.validate_upstream_url("https://example.com/collect")


class _FixtureUpstreamHandler(BaseHTTPRequestHandler):
    calls = 0
    last_payload = None
    last_authorization = None

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802
        type(self).calls += 1
        length = int(self.headers["Content-Length"])
        type(self).last_payload = json.loads(self.rfile.read(length))
        type(self).last_authorization = self.headers.get("Authorization")
        audio = wav_fixture(44_100)
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(audio)))
        self.end_headers()
        self.wfile.write(audio)


class HttpBoundaryTests(unittest.TestCase):
    def test_one_request_makes_exactly_one_upstream_call_and_reports_observed_rate(self) -> None:
        _FixtureUpstreamHandler.calls = 0
        _FixtureUpstreamHandler.last_payload = None
        _FixtureUpstreamHandler.last_authorization = None
        upstream = ThreadingHTTPServer(("127.0.0.1", 0), _FixtureUpstreamHandler)
        adapter_server = ThreadingHTTPServer(("127.0.0.1", 0), adapter.AdapterHandler)
        upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        adapter_thread = threading.Thread(target=adapter_server.serve_forever, daemon=True)
        upstream_thread.start()
        adapter_thread.start()
        upstream_url = f"http://127.0.0.1:{upstream.server_port}/tts"
        adapter_url = f"http://127.0.0.1:{adapter_server.server_port}/v1/audio/speech"
        request = Request(
            adapter_url,
            data=json.dumps(
                {
                    "model": "tts-1",
                    "input": "fixture text",
                    "voice": "pf_dora",
                    "response_format": "wav",
                }
            ).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with patch.dict(
                os.environ,
                {
                    "BRAINIALL_API_KEY": "fixture-key-not-real",
                    "BRAINIALL_TTS_UPSTREAM_URL": upstream_url,
                },
                clear=False,
            ):
                with urlopen(request, timeout=5) as response:
                    audio = response.read()
                    self.assertEqual(response.headers["X-Audio-Sample-Rate"], "44100")
                    self.assertEqual(response.headers["X-Brainiall-Compatibility"], "partial-openai-audio")
            self.assertEqual(adapter.parse_wav_metadata(audio).sample_rate_hz, 44_100)
            self.assertEqual(_FixtureUpstreamHandler.calls, 1)
            self.assertEqual(_FixtureUpstreamHandler.last_payload["text"], "fixture text")
            self.assertEqual(_FixtureUpstreamHandler.last_authorization, "Bearer fixture-key-not-real")
        finally:
            adapter_server.shutdown()
            upstream.shutdown()
            adapter_server.server_close()
            upstream.server_close()
            adapter_thread.join(timeout=2)
            upstream_thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()

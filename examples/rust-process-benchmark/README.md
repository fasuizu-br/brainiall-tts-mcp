# Rust-owned TTS process benchmark

This is a narrow, reproducible vertical slice from Rust text input to a
validated WAV file through the hosted Brainiall TTS API. It is intentionally a
process-boundary experiment, not a proposed generic speech engine.

The binary owns the request lifecycle and starts `curl` as a disposable child
process. The API key is sent to `curl` over stdin, never as a command-line
argument or inherited child environment. Automatic `.curlrc` loading is
disabled. The parent bounds endpoint/key input and response size, applies a
hard process timeout, kills and reaps the child on timeout, validates RIFF/WAVE
metadata, records time to first byte and total latency, then removes temporary
request and audio files unless `--keep-audio` is set. Retained outputs are
created exclusively and never overwrite an existing file.

## Run

Requirements: Rust 1.87 or newer, `curl` 8.x, and a Brainiall API key in the
environment.

```bash
cd examples/rust-process-benchmark
export BRAINIALL_API_KEY='replace-with-your-key'
cargo run --release -- \
  --repeat 2 \
  --voice pf_dora \
  --text 'Esta frase curta verifica a saída de áudio em português.'
```

The command prints one JSON object. A successful two-run result includes first
and repeat child-process HTTP/latency observations, WAV sample format, byte
count, approximate characters per second, executable size, and the local
model-download size (`0`, because the candidate is hosted). These are not
backend cold-start/warm-start measurements. It does not print the API key or
response audio.

Use `--keep-audio --output-dir results` only with non-sensitive text. The
default removes audio and request files after validation.

## Offline verification

```bash
cargo test
cargo clippy --all-targets -- -D warnings
cargo build --release
```

Unit tests cover JSON escaping and positive/negative WAV parsing without
network access or a key. They also reject lookalike loopback/production hosts
and verify secret redaction from returned curl diagnostics.

## Evidence boundary

This slice proves only a buffered HTTPS request, deterministic child-process
lifecycle, hard cancellation, and 16-bit PCM WAV validation for the observed
run. It does **not** prove backend cold/warm latency, streaming audio,
chunk-level backpressure, Rust library integration, all voices/languages,
production p95 latency, provider idempotency, offline operation, or suitability
for a third-party application.

Hosted synthesis sends the supplied text to Brainiall and is metered against
the caller's account. Do not submit confidential, personal, medical, or
copyrighted text without authorization. The default phrase is synthetic.

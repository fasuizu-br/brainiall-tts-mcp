# Partial OpenAI-shaped TTS adapter

This zero-dependency reference adapter accepts the common
`POST /v1/audio/speech` request shape and makes exactly one metered call to the
hosted Brainiall TTS API. It exists for clients that can configure an
OpenAI-shaped speech endpoint but cannot call Brainiall's native
`/v1/tts/synthesize` route directly.

This is **not native or complete OpenAI API compatibility**:

- WAV output only; `mp3`, `opus`, `aac`, `flac` and raw PCM are rejected.
- Buffered responses only; streaming and cancellation are not implemented.
- `model` is accepted for client-schema convenience but has no Brainiall model
  semantics.
- `voice` must be a Brainiall voice ID such as `pf_dora`; OpenAI voice names are
  not silently remapped.
- A request is never retried because synthesis is metered.

The adapter reads the returned WAV header and declares the observed values in
`X-Audio-Sample-Rate`, `X-Audio-Channels` and
`X-Audio-Bits-Per-Sample`. It does not hard-code those response headers.

## Start on loopback

Create a Brainiall API key at
[app.brainiall.com](https://app.brainiall.com?utm_source=github&utm_medium=oss&utm_campaign=openai_tts_adapter)
($10 welcome credits, no card required), then run:

```bash
export BRAINIALL_API_KEY='replace-with-your-key'
python3 examples/openai-compatible-tts-adapter/adapter.py
```

The default base URL is `http://127.0.0.1:8787/v1`. The adapter keeps the key
in the server process. If `BRAINIALL_API_KEY` is absent, it forwards the
incoming Bearer token as the Brainiall key instead.

## Verify one short request

```bash
curl --fail-with-body \
  --output speech.wav \
  --dump-header - \
  http://127.0.0.1:8787/v1/audio/speech \
  -H 'Content-Type: application/json' \
  --data '{"model":"tts-1","input":"Olá do adaptador.","voice":"pf_dora","response_format":"wav"}'
```

The request sends the text to Brainiall's hosted service and consumes account
credits. Use synthetic or authorized text for the first check. Inspect the
whole WAV before connecting automated traffic.

## Safety and operating boundary

- The process binds to loopback by default. Internet exposure requires your
  own TLS, authentication, rate limits and abuse controls.
- Request text and credentials are excluded from the adapter's default logs.
- The upstream host is fixed to Brainiall; a loopback override exists only for
  offline fixtures.
- Request and response sizes are bounded, the upstream call has a timeout, and
  there are zero automatic retries.
- A successful request proves one adapter call and a valid WAV, not client-wide
  compatibility, external adoption, a buyer or settled revenue.

## Offline tests

```bash
python3 -m unittest discover \
  -s examples/openai-compatible-tts-adapter \
  -p 'test_*.py'
```

The suite exercises 24 kHz/44.1 kHz WAV metadata parsing, request boundaries,
format rejection and the fixed-upstream rule without a key or network call.

# Brainiall TTS MCP Server

Hosted text-to-speech for AI agents via the [Model Context Protocol](https://modelcontextprotocol.io).

**54 neural voices, 9 languages** — including native **Brazilian Portuguese** (`pf_dora`, `pm_alex`, `pm_santa`) — served from a hosted, pay-per-use API. No GPU, no model downloads, no ElevenLabs subscription: bring one API key and pay **$0.008 per 1,000 characters** ($10 free credits on signup).

## Why this server

Every other TTS MCP server either runs models locally (heavy, slow to set up) or wraps a third-party key you already pay a subscription for. This one is a hosted, metered API:

- **Zero setup** — remote server, nothing to install
- **Pay per use** — $0.008/1K characters, billed against your Brainiall balance
- **$10 free credits** — sign up at [app.brainiall.com](https://app.brainiall.com)
- **WAV out** — 16-bit PCM, 24 kHz mono, returned as playable MCP audio content or base64 JSON

## Quick start

Get an API key at [app.brainiall.com](https://app.brainiall.com?utm_source=github&utm_medium=oss&utm_campaign=tts_mcp) ($10 welcome credits, no card required).

### Remote server (recommended — nothing to install)

**Claude Code**

```bash
claude mcp add --transport http brainiall-tts https://api.brainiall.com/mcp/tts/mcp \
  --header "Authorization: Bearer YOUR_BRAINIALL_API_KEY"
```

**Claude Desktop / any client with `.mcp.json`-style config**

```json
{
  "mcpServers": {
    "brainiall-tts": {
      "type": "http",
      "url": "https://api.brainiall.com/mcp/tts/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_BRAINIALL_API_KEY"
      }
    }
  }
}
```

**Cursor** (`~/.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "brainiall-tts": {
      "url": "https://api.brainiall.com/mcp/tts/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_BRAINIALL_API_KEY"
      }
    }
  }
}
```

### Run locally (stdio-free, still calls the hosted API)

The server itself is a thin wrapper — you can self-host it and it will proxy to `api.brainiall.com` with your key:

```bash
docker build -t brainiall-tts-mcp .
docker run -p 8080:8080 -e APIM_KEY=YOUR_BRAINIALL_API_KEY brainiall-tts-mcp
# MCP endpoint: http://localhost:8080/mcp
```

## Tools

| Tool | Description | Cost |
|------|-------------|------|
| `synthesize_speech` | Convert text (≤5000 chars) to WAV speech. Params: `text`, `language` (default `pt`), `voice`, `speed` (0.5–2.0), `output_format` (`audio` \| `base64_json`) | $0.008/1K chars |
| `list_voices` | Full voice catalog with language, gender, accent, quality grade. Optional `language` filter | free |
| `check_tts_service` | Backend health status | free |

### Voices

| Language | Voices |
|----------|--------|
| Portuguese (BR) | `pf_dora`, `pm_alex`, `pm_santa` |
| English (US) | `af_heart`, `af_bella`, `af_nova`, `am_adam`, `am_michael` + 14 more |
| English (GB) | `bf_alice`, `bf_emma`, `bm_daniel`, `bm_george` + 4 more |
| Spanish | `ef_dora`, `em_alex`, `em_santa` |
| French | `ff_siwis`, `fm_gilles` |
| Italian | `if_sara`, `im_nicola` |
| Hindi | `hf_alpha`, `hf_beta`, `hm_omega`, `hm_psi` |
| Japanese | `jf_alpha`, `jf_gongitsune`, `jm_kumo` + 2 more |
| Mandarin | `zf_xiaoxiao`, `zm_yunxi` + 6 more |

### Example

Ask your agent:

> "Read this paragraph out loud in Brazilian Portuguese with a female voice"

The agent calls `synthesize_speech(text=..., language="pt", voice="pf_dora")` and receives playable WAV audio.

For copy-ready prompts and smoke tests for narration, accessibility, language practice, and agent alerts, see [Agent workflow recipes](examples/agent-workflows.md).

## Authentication & billing

Pass your Brainiall API key as a Bearer token (see configs above). Usage is metered per character against your account balance — the same key works across all Brainiall APIs (STT, OCR, NLP, image and more at [brainiall.com](https://brainiall.com)).

## Endpoints

- MCP (Streamable HTTP): `https://api.brainiall.com/mcp/tts/mcp`
- Health: `https://api.brainiall.com/mcp/tts/health`
- Underlying REST API: `POST https://api.brainiall.com/v1/tts/synthesize`

## License

MIT

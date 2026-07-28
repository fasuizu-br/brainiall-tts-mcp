# Install Brainiall TTS in Cline

Brainiall TTS is a hosted Streamable HTTP MCP server. Nothing needs to be cloned or built.

## 1. Create an API key

Create a Brainiall API key at [app.brainiall.com](https://app.brainiall.com?utm_source=cline&utm_medium=marketplace&utm_campaign=tts_mcp). New accounts receive $10 in welcome credits and do not need a card to start.

Keep the key private. Do not commit it to a repository.

## 2. Add the remote server

Open Cline's MCP settings and add this entry to `mcpServers`:

```json
{
  "mcpServers": {
    "brainiall-tts": {
      "type": "streamableHttp",
      "url": "https://api.brainiall.com/mcp/tts/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_BRAINIALL_API_KEY"
      },
      "disabled": false
    }
  }
}
```

Replace `YOUR_BRAINIALL_API_KEY` locally. Do not paste a live key into chat or source control.

Cline CLI users can also start the interactive installer:

```bash
cline mcp install brainiall-tts --transport http https://api.brainiall.com/mcp/tts/mcp
```

When the wizard asks for authentication, add the `Authorization` header with the value `Bearer YOUR_BRAINIALL_API_KEY`.

## 3. Verify the connection

Ask Cline:

> Use Brainiall TTS to list the Brazilian Portuguese voices.

A successful connection exposes these three tools:

- `list_voices` — list or filter 54 neural voices across 9 languages
- `synthesize_speech` — generate WAV speech
- `check_tts_service` — check service health

Then run a minimal synthesis:

> Use Brainiall TTS to say “Olá” in Brazilian Portuguese with voice `pf_dora`.

The remote endpoint is `https://api.brainiall.com/mcp/tts/mcp`. Requests without a valid Bearer key fail closed with HTTP 401.

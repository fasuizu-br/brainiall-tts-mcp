# Brainiall TTS in OpenCode v2

OpenCode v2 supports remote MCP servers under `mcp.servers`. This example keeps the Brainiall key in an environment variable and sends only text explicitly approved for synthesis.

1. Create a key at [app.brainiall.com](https://app.brainiall.com/?utm_source=opencode&utm_medium=mcp&utm_campaign=tts_mcp_c20).
2. Export it in the shell that starts OpenCode:

   ```bash
   export BRAINIALL_API_KEY="your-key-here"
   ```

3. Merge [`opencode.json`](opencode.json) into the relevant OpenCode configuration.
4. Start OpenCode and ask it to list the Portuguese voices before synthesizing a two-character smoke test or your approved text.

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "brainiall-tts": {
        "type": "remote",
        "url": "https://api.brainiall.com/mcp/tts/mcp",
        "oauth": false,
        "headers": {
          "Authorization": "Bearer {env:BRAINIALL_API_KEY}"
        }
      }
    }
  }
}
```

The `{env:BRAINIALL_API_KEY}` form follows the current OpenCode v2 configuration contract. Do not replace it with a literal secret in a committed file. The server is hosted and metered; text authorized for `synthesize_speech` leaves your machine. Listing voices and checking health do not synthesize audio.

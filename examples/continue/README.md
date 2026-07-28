# Continue

This directory contains a standalone Continue MCP block for the hosted
Brainiall TTS server.

## Install

Copy `brainiall-tts.yaml` to the MCP block directory in your workspace:

```bash
mkdir -p .continue/mcpServers
cp examples/continue/brainiall-tts.yaml .continue/mcpServers/
```

Store the API key outside version control in `.continue/.env`:

```dotenv
BRAINIALL_API_KEY=your-key
```

Add `.continue/.env` to the workspace's `.gitignore`. Get a key from
[app.brainiall.com](https://app.brainiall.com?utm_source=github&utm_medium=oss&utm_campaign=continue_mcp);
signup includes free credits and does not require a card.

Reload Continue, switch to **Agent** mode, and try:

> Use Brainiall TTS to list the Brazilian Portuguese voices, then read
> “Olá do Continue” with `pf_dora`.

The block uses Continue's `streamable-http` transport and
`${{ secrets.BRAINIALL_API_KEY }}` placeholder. It never stores a key in the
committed YAML.

References:

- [Continue MCP configuration](https://docs.continue.dev/customize/deep-dives/mcp)
- [Continue secrets](https://docs.continue.dev/guides/configuring-models-rules-tools)

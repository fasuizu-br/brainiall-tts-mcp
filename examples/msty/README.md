# Brainiall TTS in Msty Studio

This is a manual field guide for connecting Msty Studio to the hosted
Brainiall TTS MCP server. It is maintained by Brainiall; it is not an official
Msty integration or an importable Msty preset.

## Configure the tool

1. [Sign in to Brainiall](https://app.brainiall.com/pt-br/login?utm_source=github&utm_medium=oss&utm_campaign=msty_tts_mcp),
   then create a dedicated, revocable key in your account.
2. In Msty Studio Desktop, open **Toolbox**, choose **Add New Tool**, and select
   **HTTP**.
3. Enter these values manually:

   | Field | Value |
   | --- | --- |
   | Name | `Brainiall TTS` |
   | MCP Server URL | `https://api.brainiall.com/mcp/tts/mcp` |
   | Header name | `Authorization` |
   | Header value | `Bearer <YOUR_BRAINIALL_API_KEY>` |

4. Add the tool, then ask Msty to call `check_tts_service` and
   `list_voices` with `language="pt"` before running a metered synthesis.

[`field-reference.json`](field-reference.json) contains the same values for
copying. Its keys describe the fields above; the file is deliberately not
presented as an Msty import schema.

The endpoint uses Streamable HTTP. Msty's current documentation says remote
SSE is not supported. Msty Studio Web also requires a connection to Msty
Studio Desktop through Remote Connections or Sidecar before it can use Toolbox
tools.

## Security, privacy, and cost boundary

Keep the key out of prompts, screenshots, exported chats, and repositories.
Text passed to `synthesize_speech` leaves Msty and is processed by the hosted
Brainiall API. Voice listing and health checks are free; synthesis is metered
at the price shown in the [main README](../../README.md).

Reference: [Msty Studio Toolbox documentation](https://docs.msty.ai/studio/toolbox/tools).

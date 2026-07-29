# Brainiall TTS for GitHub Copilot cloud agent

This configuration connects GitHub Copilot cloud agent or Copilot code review to the hosted Brainiall TTS MCP server. It uses GitHub's supported repository MCP schema and an Agents secret, so the Brainiall key is not committed.

## Configure

1. Create a dedicated key at [app.brainiall.com](https://app.brainiall.com?utm_source=github&utm_medium=oss&utm_campaign=copilot_cloud_mcp). New accounts currently receive $10 in welcome credits; no card is required.
2. In the target repository, open **Settings → Copilot → MCP servers**.
3. Paste the contents of [`mcp.json`](mcp.json) into **MCP configuration** and save it.
4. Add an Agents secret named exactly `COPILOT_MCP_BRAINIALL_API_KEY` with the dedicated Brainiall key as its value.
5. Ask Copilot to call `check_tts_service`, then `list_voices` with `language="pt"`. Run `synthesize_speech` only with text you are authorized to send.

The allowlist exposes only:

- `check_tts_service` — free health check;
- `list_voices` — free voice discovery;
- `synthesize_speech` — metered at the current Brainiall API rate.

## Security and cost boundary

Copilot cloud agent can use configured MCP tools autonomously. Text passed to `synthesize_speech` is sent to Brainiall for processing, and synthesis consumes the Brainiall balance. Configure this server only in a trusted repository, use a dedicated revocable key, and do not send secrets, personal data, or copyrighted text you are not authorized to process.

This configuration does not grant repository access to Brainiall. It sends only the arguments of the MCP calls that Copilot chooses to make.

## Verify or remove

- Verify JSON syntax locally with `python3 -m json.tool examples/github-copilot-cloud/mcp.json`.
- In GitHub, re-open **Settings → Copilot → MCP servers** to review or remove the configuration.
- Delete the Agents secret and revoke the dedicated Brainiall key when the integration is no longer needed.

Official references: [GitHub repository MCP configuration](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/configure-mcp-servers) and [Copilot MCP security guidance](https://docs.github.com/en/copilot/customizing-copilot/extending-copilot-chat-with-mcp).

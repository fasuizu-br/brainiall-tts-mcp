# Brainiall TTS for Claude Code

Claude Code expands environment variables inside project-scoped `.mcp.json` headers. This setup keeps the Brainiall key out of the repository while connecting directly to the hosted Streamable HTTP server.

## Configure

1. Create a dedicated key at [app.brainiall.com](https://app.brainiall.com?utm_source=github&utm_medium=oss&utm_campaign=claude_code_mcp). New accounts currently receive $10 in welcome credits; no card is required.
2. Export the key through your shell or secret manager. To avoid putting the value in shell history:

   ```bash
   read -s "BRAINIALL_API_KEY?Brainiall API key: "
   export BRAINIALL_API_KEY
   printf '\n'
   ```

3. Copy [`.mcp.json`](.mcp.json) to the root of the project where you want to use the server.
4. Start Claude Code in that project, review the workspace trust prompt, and approve only the `brainiall-tts` server.
5. Run `/mcp`, then ask Claude to call `check_tts_service` and `list_voices` with `language="pt"`. Use `synthesize_speech` only for text you are authorized to process.

## Security and cost boundary

The checked-in JSON contains only `${BRAINIALL_API_KEY}`; the value is resolved from the Claude Code process environment. Text sent to `synthesize_speech` leaves the local project for Brainiall processing, and synthesis consumes the Brainiall balance at the current API rate. Do not send secrets, personal data, or copyrighted text you are not authorized to process.

Claude Code requires workspace approval before loading a project-scoped MCP server. Remove the copied `.mcp.json`, unset `BRAINIALL_API_KEY`, and revoke the dedicated key to disconnect completely.

## Validate the example

```bash
python3 -m json.tool examples/claude-code/.mcp.json >/dev/null
BRAINIALL_API_KEY=not-a-real-key claude mcp get brainiall-tts
```

The second command is a configuration check only when run from a project containing the example as `.mcp.json`; a dummy key must fail authentication and must never synthesize billable audio.

Official reference: [Claude Code MCP configuration and environment expansion](https://code.claude.com/docs/en/mcp#environment-variable-expansion-in-mcpjson).

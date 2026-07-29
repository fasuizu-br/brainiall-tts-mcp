# Brainiall TTS in Codex

This project-scoped configuration connects Codex CLI, the Codex IDE extension,
and the ChatGPT desktop app to the hosted Brainiall TTS MCP server. It reads a
dedicated key from the environment, allowlists only three documented tools, and
asks before each tool call.

## Configure a trusted project

1. Create a dedicated key at
   [app.brainiall.com](https://app.brainiall.com/?utm_source=codex&utm_medium=mcp&utm_campaign=tts_mcp_c22).
   New accounts currently receive welcome credits without a card.
2. Export the key in the shell that starts Codex. Avoid putting the value in
   shell history:

   ```bash
   read -s "BRAINIALL_API_KEY?Brainiall API key: "
   export BRAINIALL_API_KEY
   printf '\n'
   ```

3. Copy [`.codex/config.toml`](.codex/config.toml) into the root of a project
   you trust. If the project already has that file, merge only the
   `[mcp_servers.brainiall_tts]` table instead of overwriting other settings.
4. Restart Codex in that project and run `codex mcp list` or type `/mcp` in the
   terminal UI. Confirm that `brainiall_tts` points to the expected HTTPS URL.
5. Ask Codex to call `check_tts_service`, then `list_voices` with
   `language="pt"`. Approve `synthesize_speech` only after reviewing the exact
   text and metered cost.

Try this bounded prompt:

> Check the Brainiall TTS service, list the Brazilian Portuguese voices, and
> ask me before synthesizing only: “Olá do Codex.” with `pf_dora`.

## Security, privacy, and cost boundary

- The committed TOML contains only the name `BRAINIALL_API_KEY`; it never
  contains the secret value.
- Text passed to `synthesize_speech` leaves the project and is processed by the
  hosted Brainiall API. Do not send secrets, personal data, or text you are not
  authorized to process.
- Health and voice discovery are free. Synthesis is metered at the current rate
  in the [main README](../../README.md).
- Remove the MCP table, unset `BRAINIALL_API_KEY`, and revoke the dedicated key
  to disconnect the integration.

The configuration follows OpenAI's official
[Codex MCP guide](https://developers.openai.com/codex/mcp/) and
[configuration reference](https://developers.openai.com/codex/config-reference/):
project `.codex/config.toml` files apply only to trusted projects;
`bearer_token_env_var` keeps the token out of source; `enabled_tools` limits the
surface; and `default_tools_approval_mode = "prompt"` preserves human approval.

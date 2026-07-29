# Brainiall TTS in Hugging Face Chat UI

This example is for an administrator of a self-hosted Hugging Face Chat UI
deployment. It does not install Brainiall TTS into the public HuggingChat
service.

## Configure the base MCP server

1. [Sign in to Brainiall](https://app.brainiall.com/pt-br/login?utm_source=github&utm_medium=oss&utm_campaign=hf_chat_ui_tts_mcp),
   then create a dedicated, revocable key in your account.
2. Set the Chat UI administrator environment variable `MCP_SERVERS` to a JSON
   array containing the contents of [`mcp-servers.json`](mcp-servers.json).
   For example, in a shell-managed deployment:

   ```bash
   export MCP_SERVERS='[{"name":"Brainiall TTS","url":"https://api.brainiall.com/mcp/tts/mcp","headers":{"Authorization":"Bearer <YOUR_BRAINIALL_API_KEY>"}}]'
   ```

3. Restart or redeploy Chat UI, enable **Brainiall TTS** in the MCP Servers
   panel, and run the health check.
4. Use a model configured for tool calling. When overriding `MODELS`, Chat UI
   requires `"supportsTools": true` on models that should invoke MCP tools.
5. Call `check_tts_service` and `list_voices` with `language="pt"` before a
   metered synthesis.

`MCP_SERVERS` is an administrator-level setting. Base servers appear for every
user and can be disabled per user but not removed by them. A key placed in the
server's headers can therefore fund calls from enabled users of that Chat UI
deployment. Use a dedicated key, restrict access to trusted users, monitor its
balance, and rotate or revoke it when necessary. Do not commit a populated
environment file.

Text passed to `synthesize_speech` leaves Chat UI and is processed by the
hosted Brainiall API. Voice listing and health checks are free; synthesis is
metered at the price shown in the [main README](../../README.md).

Reference: [Hugging Face Chat UI MCP configuration](https://huggingface.co/docs/chat-ui/en/configuration/mcp-tools).

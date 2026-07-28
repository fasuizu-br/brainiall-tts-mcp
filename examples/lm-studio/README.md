# Brainiall TTS in LM Studio

Add the hosted Brainiall TTS MCP server to LM Studio, then let a local model turn only the text you explicitly select into a WAV file.

[![Add Brainiall TTS to LM Studio](https://img.shields.io/badge/LM_Studio-Add_Brainiall_TTS-111827?style=flat-square)](lmstudio://add_mcp?name=brainiall-tts&config=eyJ1cmwiOiJodHRwczovL2FwaS5icmFpbmlhbGwuY29tL21jcC90dHMvbWNwIiwiaGVhZGVycyI6eyJBdXRob3JpemF0aW9uIjoiQmVhcmVyIDxZT1VSX0JSQUlOSUFMTF9BUElfS0VZPiJ9fQ%3D%3D)

The deeplink follows LM Studio's official `lmstudio://add_mcp` format. It installs this remote endpoint:

```text
https://api.brainiall.com/mcp/tts/mcp
```

Before connecting, replace `<YOUR_BRAINIALL_API_KEY>` in LM Studio with a key created at [app.brainiall.com](https://app.brainiall.com/?utm_source=lm_studio&utm_medium=mcp&utm_campaign=tts_mcp_c20). Keep the key out of prompts, exported chats, screenshots, and repositories.

Try this bounded prompt after the server connects:

> List the Brazilian Portuguese voices. Then synthesize only this sentence with `pf_dora`: “Olá do LM Studio.”

Important privacy boundary: your main language model can remain local, but text sent to `synthesize_speech` leaves the device and is processed by the hosted Brainiall API. Review the selected text before approving the tool call. Voice listing and health checks are free; synthesis is metered at the price shown in the [main README](../../README.md).

The copy-ready source entry is in [`mcp-entry.json`](mcp-entry.json). The button carries a placeholder, never a real key.

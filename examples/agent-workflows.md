# Agent workflow recipes

These recipes use the hosted `com.brainiall/tts` MCP server. Configure the server from the repository [quick start](../README.md#quick-start), then paste one prompt into your MCP client.

## 30-second smoke test

> Use `check_tts_service`, then list the Brazilian Portuguese voices. If the service is healthy, synthesize: "O teste de voz da Brainiall está funcionando." with `pf_dora` at normal speed.

Expected result: the client reports a healthy service, returns the Portuguese voice catalog, and produces a playable WAV file.

## Turn a release note into audio

> Read the release note below in Brazilian Portuguese with `pm_alex`. Keep the original wording and use speed 1.05. Save the result as WAV. RELEASE NOTE: [paste text]

Use this for changelogs, internal announcements, and product demos. Each synthesis request accepts up to 5,000 characters.

## Create a bilingual pronunciation pair

> Synthesize the sentence below twice: first in English with `af_heart`, then in Brazilian Portuguese with `pf_dora`. Use speed 0.85 for both. SENTENCE: [paste text]

The server supports Portuguese, English, Spanish, French, Italian, Hindi, Japanese, and Mandarin voices.

## Produce an accessible audio summary

> Summarize the text below in at most 500 words. Ask me to approve the summary before audio generation. After approval, synthesize it in Brazilian Portuguese with `pf_dora` and return playable WAV audio. TEXT: [paste text]

The approval step lets a person review the wording before usage is metered.

## Voice an agent alert

> Convert this operational alert to speech with `pm_santa`, speed 1.1, and `output_format` set to `base64_json`: "A fila de processamento ultrapassou o limite definido."

`base64_json` is useful when the next workflow step stores or forwards the WAV programmatically.

## Billing and privacy notes

- Speech synthesis costs **$0.008 per 1,000 characters**; voice listing and health checks are free.
- Text is sent to the hosted Brainiall API for synthesis. Do not submit secrets or text you are not authorized to process.
- Create a key with welcome credits at [app.brainiall.com](https://app.brainiall.com?utm_source=github&utm_medium=oss&utm_campaign=tts_mcp_recipes).

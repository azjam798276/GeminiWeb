# OpenAI Compatibility Targets

## Milestone 1 (M1): Minimal Chat Completions

Supported:

- Endpoint: `POST /v1/chat/completions`
- Non-streaming (`stream=false`)
- Streaming (`stream=true`) when `ENABLE_STREAMING=true`
- `messages[]` roles: `system`, `user`, `assistant`
- Generation fields:
  - `temperature` → Gemini `generationConfig.temperature`
  - `top_p` → Gemini `generationConfig.topP`
  - `max_tokens` / `max_completion_tokens` → Gemini `generationConfig.maxOutputTokens`
  - `stop` (string or list) → Gemini `generationConfig.stopSequences`
  - `presence_penalty` → Gemini `generationConfig.presencePenalty`
  - `frequency_penalty` → Gemini `generationConfig.frequencyPenalty`

Not supported (returns 400 or ignored):

- `stream=true` when `ENABLE_STREAMING=false`
- `tool` messages / tool calling
- non-text content payloads (images/audio)
- advanced OpenAI parameters not listed above

Message mapping:

- System messages are concatenated into Gemini `systemInstruction`.
- `user` → Gemini content role `user`
- `assistant` → Gemini content role `model`

## Milestone 2 (M2): Expanded Parity (Planned)

Candidates:

- Tool/function calling (if/when mapped safely to official APIs)
- Better multi-turn formatting fidelity (including tool call transcripts)
- Usage/token accounting (if available from upstream)
- Additional OpenAI request fields (seed, `logit_bias`, etc. where applicable)

Current status:

- Streaming is implemented behind `ENABLE_STREAMING=true` and uses OpenAI-compatible SSE frames.

# Using a Local LLM

ScanBox supports any OpenAI-compatible LLM server (Ollama, MLX-LM, vLLM, etc.).

## Quick Setup

Set these environment variables:

```
LLM_PROVIDER=openai
OPENAI_API_BASE=http://your-server:11434/v1
OPENAI_API_KEY=any-non-empty-string
LLM_MODEL=openai/your-model-name
```

## Tested Configurations

| Server | Model | Performance |
|--------|-------|-------------|
| MLX-LM | Qwen3.5-35B-A3B-4bit | ~85 tok/s on Mac Mini M4 Pro |

## Tips

- Set `LLM_MODEL=openai/<model-name>` (the `openai/` prefix tells litellm to use the OpenAI API format)
- `OPENAI_API_KEY` can be any non-empty string if your server doesn't validate tokens
- The splitter uses `max_tokens=4096` -- ensure your server supports this
- For development, use the test fixture import to bypass the scanner:
  `curl -X POST -F fronts=@tests/fixtures/test_suite/06-minimal-quick/fronts.pdf http://localhost:8090/api/batches/import`

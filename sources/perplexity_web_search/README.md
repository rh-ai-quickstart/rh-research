# Perplexity Web Search

NAT-based web search tool for the [Perplexity Search API](https://docs.perplexity.ai/api-reference/search-post).
It sends `POST https://api.perplexity.ai/search` with `httpx` and returns each result as a `<Document href="...">`
block, the same format as the Tavily and Exa sources.

Requires a `PERPLEXITY_API_KEY` environment variable or `api_key` config. Without a key, the tool still registers and
returns an "unavailable" message when called.

## Configuration

```yaml
functions:
  perplexity_web_search_tool:
    _type: perplexity_web_search
    max_results: 5
    search_type: web
    max_content_length: 1000
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `api_key` | `None` | Perplexity API key. Falls back to `PERPLEXITY_API_KEY`. |
| `max_results` | `5` | Results per query, 1 to 20. |
| `max_content_length` | `10000` | Max characters per result snippet. `None` disables truncation. |
| `search_type` | `web` | `web` or `fast`. `fast` trades some quality for lower latency and cost. |
| `search_domain_filter` | `None` | Up to 20 domains. Plain entries form an allowlist, entries starting with `-` form a denylist. Do not mix them. |
| `timeout` | `30` | Request timeout in seconds. |
| `max_retries` | `3` | Attempts for timeouts, connection errors, and HTTP 5xx. HTTP 429 and other 4xx are not retried. |

## Tests

```bash
uv run pytest sources/perplexity_web_search/tests -q
```

The tests mock HTTP with `httpx.MockTransport` and need no API key.

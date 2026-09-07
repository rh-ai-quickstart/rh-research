<!--
SPDX-FileCopyrightText: Copyright (c) 2025-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# vLLM Migration: Decision Log

This document captures the design decisions, trade-offs, and lessons learned during the vLLM migration work. It is intended as source material for blog posts and internal knowledge sharing.

## Context

AI-Q Blueprint v2.0 was originally built exclusively for NVIDIA NIM endpoints (`_type: nim`, `ChatNVIDIA` client). The vLLM migration adds support for any OpenAI-compatible inference server, enabling open model deployment on arbitrary hardware.

## Decision 1: `_type: openai` Instead of a New `_type: vllm`

**Decision:** Use LangChain's existing `ChatOpenAI` client (`_type: openai`) rather than creating a vLLM-specific client type.

**Why:**
- vLLM, LiteLLM, TGI, and other servers all implement the OpenAI API specification
- `ChatOpenAI` is battle-tested with tool calling, streaming, and async support
- A `_type: vllm` would have been a near-identical wrapper with no additional value
- Users can point `_type: openai` at any compatible server without code changes

**Trade-off:** We lose the ability to use NIM-specific features (like `chat_template_kwargs`) through the OpenAI client. This is handled by the model-aware thinking prefix system (Decision 3).


## Decision 2: Environment Variable-Driven Configuration

**Decision:** All vLLM config values (base URL, API key, model names, max tokens) are parameterized via `${VAR:-default}` syntax in the YAML config.

**Why:**
- Same config file works for local vLLM (defaults) and MaaS/gateway endpoints (env overrides)
- Operators can deploy without editing YAML — just set env vars in `.env` or Kubernetes secrets
- The existing NIM config hardcoded model names, making model swaps require config file edits

**Env vars added:**
| Variable | Default | Purpose |
|----------|---------|---------|
| `VLLM_BASE_URL` | `http://localhost:8000` | Inference server URL |
| `VLLM_API_KEY` | `no-key` | Auth token for gateways |
| `VLLM_INTENT_MODEL` | `Llama-3.1-8B-Instruct` | Intent classification |
| `VLLM_RESEARCHER_MODEL` | `Llama-3.1-70B-Instruct` | Shallow/deep research |
| `VLLM_ORCHESTRATOR_MODEL` | `Qwen2.5-72B-Instruct` | Deep research orchestrator |
| `VLLM_SUMMARY_MODEL` | `Llama-3.1-8B-Instruct` | Document summarization |
| `VLLM_ORCHESTRATOR_MAX_TOKENS` | `128000` | Max tokens for orchestrator |


## Decision 3: Reasoning control via NAT's `thinking:` field (superseded)

**Current decision:** Reasoning control is configuration, handled by NAT's `ThinkingMixin` — the `thinking:` field on each LLM role in `config_web_vllm.yml`. There is no local helper.

**Superseded (2026-07-30):** this project previously carried `is_nemotron()` / `get_thinking_prefix()` in `prompt_utils.py`, which prepended `/think` or `/no_think` to system prompts. **Both were removed**, along with their tests and three call sites. Two measurements drove that:

1. **The premise was wrong.** The helper gated directives to NIM endpoints only, documented as *"vLLM serves the same models but does not interpret /think or /no_think directives — they get echoed as literal text."* Not true: vLLM with a reasoning parser consumes the directive cleanly. Sending `/think` to Nemotron-3-Super on vLLM produced ~465 reasoning tokens, and the directive never appeared in the output.
2. **What it gated is a no-op.** Measured against `nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4`, 3 runs each:

   | Condition | completion tokens (median) |
   | :-- | :-- |
   | no directive | 49 |
   | `/no_think` | 49 |
   | `/think` | 465 |

   The model does not emit a reasoning trace by default, so *suppressing* reasoning changes nothing. `/think` **enables** it at ~9.5x the tokens. The long-held theory that unsuppressed reasoning was the latency bomb on self-hosted endpoints is disproven — see [vLLM results](vllm-results.md).

Keeping the helper would have meant carrying ~390 lines of fork deviation, plus duplicating a mechanism the framework already provides.

**What to use instead:** set `thinking:` per role. The config ships `thinking: ${VLLM_THINKING:-null}`; `null` means no directive and is safe on any model.

**Footgun:** `ThinkingMixin` is gated to Nemotron model names and **raises at config load** on anything else. `VLLM_THINKING=false` against a non-Nemotron model (including this config's default `Qwen/Qwen2.5-72B-Instruct` orchestrator) fails startup rather than degrading quietly. Leave it `null` unless every role is Nemotron — and note that per the table above, setting it buys nothing measurable.

**Retained from the old approach:** the fallback prompts in `clarifier/agent.py` and `intent_classifier.py` no longer hardcode `/no_think`. Upstream's versions do, which sends a literal Nemotron directive to whatever model is configured. Keeping those prompts model-agnostic is still correct.


## Decision 4: Startup Endpoint Validation

**Decision:** Add an async endpoint probe at startup that checks reachability, model availability, and context window limits — logging warnings but not blocking startup.

**Why (the incident that drove this):**
During live testing with a Red Hat MaaS endpoint (`qwen3-14b`, 40k context window), deep research failed silently with `400 Bad Request` errors. The orchestrator config had `max_tokens: 128000`, which exceeded the model's context window. The failure only manifested after minutes of research when the report generation phase accumulated enough context to trigger the limit.

**What the validator checks:**
1. **Endpoint reachability** — `GET /v1/models` to verify the server responds
2. **Model availability** — configured model names must exist on the endpoint
3. **Context window limits** — for deep research roles, probes the model's actual limit and warns if:
   - Context window < 32,768 tokens (minimum recommended)
   - `max_tokens` in config exceeds the context window (guaranteed runtime failure)

**Why warn, not block:**
- The probe might fail due to transient network issues — shouldn't prevent startup
- Context window estimates are heuristic (not all endpoints report them)
- Operators may intentionally run with undersized models for testing
- Existing API key validation already blocks on hard errors

**Implementation:** `validate_llm_endpoints()` in `config_validation.py`, called from `chat_deepresearcher_agent` registration. NIM endpoints are skipped since they don't support `/v1/models` in the same way.


## Decision 5: MaaS / API Gateway Support

**Decision:** The vLLM config supports authenticated API gateways (LiteLLM, Azure OpenAI, Red Hat MaaS) without any code changes — just set `VLLM_API_KEY` to the real key.

**Why:**
The original config validation assumed local endpoints don't need API keys (based on IP address heuristics). This is wrong for gateway-fronted deployments where a public URL requires authentication.

**Fix:** The `_extract_env_var` function was updated to properly parse `${VAR:-default}` syntax. When the api_key field has a non-empty default (like `no-key`), the env var is optional. When there's no default, the env var is required.

**Bug found:** The original `_extract_env_var` regex matched the full `VAR:-default` string as the variable name, causing `os.getenv("VLLM_API_KEY:-no-key")` which always returned None. Fixed by splitting the regex into name and default capture groups.


## Decision 6: Configurable max_tokens per LLM role

**Decision:** Keep the committed `max_tokens` defaults at **NIM scale**, and make every role overridable by environment variable — `VLLM_INTENT_MAX_TOKENS`, `VLLM_RESEARCHER_MAX_TOKENS`, `VLLM_ORCHESTRATOR_MAX_TOKENS`, `VLLM_WRITER_MAX_TOKENS`.

**Default:** orchestrator `128000`, researcher `16384`, writer `16384`, intent `1024`. These match the NIM configuration deliberately — see the sizing note below before lowering them.

**Why match NIM scale rather than pick a "safe" small default:**

vLLM-hosted is **not** a synonym for small. On Red Hat AI (OpenShift AI / KServe), we deploy Nemotron-3-scale models — Super `120b-a12b`, Ultra `550b-a55b` — through vLLM just as readily as through NIM. The serving stack is an operational choice, not a capability tier. A default tuned for a 16k MaaS endpoint would silently truncate deep-research synthesis on exactly the large-context deployments this configuration is built for.

So the committed defaults assume a capable endpoint, and operators scale *down* for constrained ones.

### The hard constraint: `max_tokens` must be ≤ the served `--max-model-len`

This is a coupling between this configuration and how the endpoint is launched, and vLLM enforces it with an **HTTP 400**. It is not model-dependent — it depends entirely on what `--max-model-len` the server was started with.

Two real incidents:

1. **Red Hat MaaS, `qwen3-14b`, 40k context.** Deep research failed with `400 Bad Request`. The failure surfaced only after minutes of research, once report generation had accumulated enough context to cross the limit.
2. **DGX Spark, Nemotron-3-Super.** A KV-cache fix reduced `--max-model-len` from 262144 to 32768 to buy concurrency (KV cache 7.62 → 23.29 GiB, concurrency 1.25x → 30.54x). The *model* was large, but the *served window* was now 32k — so `max_tokens: 128000` was rejected. Resolved with `VLLM_ORCHESTRATOR_MAX_TOKENS=8192`.

The second case is the important one: **a large model does not guarantee a large served window.** Serving-side tuning for throughput routinely shrinks `--max-model-len` well below what the model supports.

### Sizing guidance for vLLM-hosted setups

1. Read the server's actual window — `curl $VLLM_BASE_URL/v1/models` reports `max_model_len`, and it is logged at vLLM startup.
2. Keep every role's `max_tokens` **strictly below** it, leaving headroom for the prompt. The value is an *output* budget, but the server rejects requests where prompt + `max_tokens` exceeds the window.
3. On reasoning models (Nemotron, Qwen3.5, Kimi K2.5), hidden reasoning tokens count toward the budget — allow 2-3x the expected content length.
4. Override per role via env; do not edit the committed YAML.

Startup validation catches this before any user query: `validate_llm_endpoints` probes each configured endpoint and warns when `max_tokens` exceeds the reported context window (see Decision 5). That check exists precisely because the runtime symptom — a silent retry loop, then failure minutes later — is so hard to diagnose.

### Implementation note

`max_tokens` is **not a declared field** on NAT's `OpenAIModelConfig`. It reaches the client through Pydantic's `extra="allow"`, landing in `model_extra`. Verified identical on nvidia-nat-core 1.7.0 and 1.8.0. If a future NAT release tightens that class to `extra="forbid"`, every role here fails config-load at once — so re-run this check on each NAT upgrade:

```bash
python -c "from nat.llm.openai_llm import OpenAIModelConfig as C; print(C.model_config, sorted(C.model_fields))"
```


## Decision 7: Tavily Search Error Logging

**Decision:** Add explicit logging at WARNING and ERROR level for Tavily search failures, while keeping the user-facing error messages unchanged.

**Why (the incident that drove this):**
During e2e testing, the UI showed "Research failed: no sources were captured during deep research" with no indication of the root cause. The backend logs only showed `[Tool Result] content='Search error: Error 432: '` — a tool result string, not a log message. The Tavily API key had hit its usage limit, but this was invisible to operators monitoring logs.

**What changed in `sources/tavily_web_search/src/register.py`:**
- **Retry attempts** now log at WARNING: `"Tavily search attempt 1/3 failed: Error 432"`
- **Final failure** logs at ERROR: `"Tavily search failed after 3 attempts: Error 432"`
- **User-facing response** remains the same sanitized error string

**Principle:** Operational errors (API rate limits, auth failures, timeouts) must be visible in logs even when the user-facing error is intentionally generic. The tool result string is consumed by the LLM agent, not by operators.


## Decision 8: Frontend allowedDevOrigins for Remote Access

**Decision:** Add `allowedDevOrigins: ['dgxspark']` to `next.config.ts` to fix broken UI when accessing from a non-localhost hostname.

**Why:**
Next.js 16 blocks cross-origin requests to dev resources (HMR WebSocket, `/_next/webpack-hmr`) by default. When accessing the UI via hostname (e.g., `http://dgxspark:3000`) instead of `localhost`, the JavaScript bundle fails to hydrate and the UI becomes completely unresponsive to clicks.

**Trade-off:** This is a dev-mode-only setting. Production builds use `npm start` which doesn't have this restriction. The hostname `dgxspark` is specific to the DGX Spark development environment.


## Lessons Learned

### 1. Context Windows Are the Real Bottleneck
Model size (parameter count) gets all the attention, but context window is what determines whether deep research works. A 14B model with 128k context would fare better than a 70B model with 16k context for orchestration tasks.

### 2. Silent Failures from API Mismatches
The `400 Bad Request` from exceeding `max_tokens` was only visible in httpx retry logs — the agent framework retried silently for minutes before failing. Startup validation catches this class of error before any user query is processed.

### 3. Env Var Defaults Need Care
`${VLLM_API_KEY:-no-key}` is a good pattern for local development but requires documentation to explain why `no-key` works (vLLM ignores auth by default). The same default causes silent authentication failures on gateways that require real keys.

### 4. Tavily Error Logging Gap
During testing, Tavily API rate limit errors (`Error 432`) were caught and returned as tool results but never logged. This made it appear that the search tool was working when it was consistently failing. Added explicit logging at WARNING (retries) and ERROR (final failure) levels.

### 5. Test Against Real Endpoints Early
Unit tests with mocked responses caught the config validation bugs, but the context window and rate limiting issues only surfaced during live testing against the Red Hat MaaS endpoint. The endpoint probe was designed specifically to catch these issues at startup rather than at query time.


## Files Changed

| File | Change |
|------|--------|
| `configs/config_web_vllm.yml` | New vLLM config with env-var-driven model/endpoint selection |
| `src/aiq_agent/common/config_validation.py` | Fixed `_extract_env_var`, added `validate_llm_endpoints()` |
| `src/aiq_agent/common/prompt_utils.py` | Model-aware thinking prefix system |
| `src/aiq_agent/agents/chat_researcher/register.py` | Endpoint validation integration |
| `src/aiq_agent/agents/clarifier/agent.py` | Thinking prefix integration |
| `src/aiq_agent/agents/chat_researcher/nodes/intent_classifier.py` | Thinking prefix integration |
| `sources/tavily_web_search/src/register.py` | Added error logging for search failures |
| `frontends/ui/next.config.ts` | Added `allowedDevOrigins` for remote dev access |
| `deploy/.env` | MaaS endpoint config (VLLM_BASE_URL, VLLM_API_KEY, model mappings) |
| `tests/aiq_agent/common/test_config_validation.py` | 50 tests covering all validation paths |
| `tests/aiq_agent/common/test_prompt_utils.py` | 38 tests for thinking prefix system |
| `docs/source/customization/vllm-migration.md` | Updated migration guide with MaaS, validation, and deep research guidance |

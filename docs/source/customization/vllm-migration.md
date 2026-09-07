<!--
SPDX-FileCopyrightText: Copyright (c) 2025-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# Migrating to vLLM (or Any OpenAI-Compatible Endpoint)

## Overview

This guide covers running AI-Q against vLLM, TGI, or any OpenAI-compatible inference server instead of NVIDIA NIM. This lets you:

- **Use open models** — Llama, Qwen, Mistral, DeepSeek, Gemma, or any model vLLM can serve
- **Run on any hardware** — not limited to NVIDIA NIM-supported GPUs
- **Deploy air-gapped** — no external API calls; everything runs on your infrastructure
- **Avoid API key dependencies** — local vLLM doesn't require `NVIDIA_API_KEY`

This guide complements [Swapping Models](./swapping-models.md), which covers NIM-to-NIM model swaps within the NVIDIA ecosystem. This page covers leaving the NIM ecosystem entirely.

**Prerequisites:** A running vLLM instance serving at least one model with OpenAI-compatible API enabled.


## Quick Start

1. **Start vLLM** with your chosen model:

   ```bash
   vllm serve meta-llama/Llama-3.1-70B-Instruct \
     --port 8000 \
     --enable-auto-tool-choice \
     --tool-call-parser hermes
   ```

2. **Set environment variables:**

   ```bash
   export VLLM_BASE_URL=http://localhost:8000
   # Optional: override model names per role
   export VLLM_INTENT_MODEL=meta-llama/Llama-3.1-8B-Instruct
   export VLLM_RESEARCHER_MODEL=meta-llama/Llama-3.1-70B-Instruct
   export VLLM_ORCHESTRATOR_MODEL=Qwen/Qwen2.5-72B-Instruct
   ```

3. **Launch with the vLLM config:**

   ```bash
   CONFIG_FILE=configs/config_web_vllm.yml nat serve
   ```

4. **Verify** by opening the Web UI or running a CLI query.


## Understanding the Config File

The file `configs/config_web_vllm.yml` is a drop-in replacement for the default NIM config. The key difference is `_type: openai` instead of `_type: nim`.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VLLM_BASE_URL` | `http://localhost:8000` | Base URL of your vLLM server |
| `VLLM_API_KEY` | `no-key` | API key (vLLM accepts any string when auth is disabled) |
| `VLLM_INTENT_MODEL` | `meta-llama/Llama-3.1-8B-Instruct` | Model for intent classification |
| `VLLM_RESEARCHER_MODEL` | `meta-llama/Llama-3.1-70B-Instruct` | Model for shallow research and agent work |
| `VLLM_ORCHESTRATOR_MODEL` | `Qwen/Qwen2.5-72B-Instruct` | Model for deep research orchestration and planning |
| `VLLM_SUMMARY_MODEL` | `meta-llama/Llama-3.1-8B-Instruct` | Model for document summarization |

### `_type: openai` vs `_type: nim`

Both create LangChain chat model clients:

| | `_type: nim` | `_type: openai` |
|---|---|---|
| **Client class** | `ChatNVIDIA` | `ChatOpenAI` |
| **Protocol** | OpenAI-compatible (NVIDIA NIM) | OpenAI-compatible (any server) |
| **`chat_template_kwargs`** | Supported (controls model thinking mode) | Not supported — omit from config |
| **API key** | Requires `NVIDIA_API_KEY` | Optional for local endpoints |

### Why `chat_template_kwargs` is omitted

The NIM config includes `chat_template_kwargs: enable_thinking: true` to activate Nemotron's extended chain-of-thought mode. This is a NIM-specific API parameter that vLLM does not support. The vLLM config omits it entirely — vLLM reasoning models (e.g., Qwen QwQ, DeepSeek-R1) handle thinking natively without this parameter.


## Model Role Mapping

Each LLM in the config is assigned to specific agent roles:

| Role | Config Key | Default Model | Recommended Size | Why |
|------|-----------|---------------|-----------------|-----|
| Intent classifier | `intent_llm` | Llama-3.1-8B-Instruct | 7-8B | Fast structured JSON output; low latency critical |
| Shallow researcher | `researcher_llm` | Llama-3.1-70B-Instruct | 70B+ | Reliable tool calling and synthesis |
| Deep research orchestrator | `orchestrator_llm` | Qwen2.5-72B-Instruct | 70B+ | Large context window for multi-step planning |
| Deep research planner | `orchestrator_llm` | (same as orchestrator) | 70B+ | Shared with orchestrator by default |
| Document summarization | `summary_llm` | Llama-3.1-8B-Instruct | 7-8B | Short summaries; speed over quality |

```{note}
Tool-calling capability is critical for the researcher and orchestrator roles. Ensure your vLLM model supports function calling and that vLLM is started with `--enable-auto-tool-choice`.
```


## Model-as-a-Service (MaaS) and API Gateways

The vLLM config works with any OpenAI-compatible endpoint, including managed services behind API gateways such as:

- **Red Hat Model-as-a-Service** (LiteLLM on OpenShift)
- **LiteLLM Proxy** — multi-model gateway with auth and rate limiting
- **Azure OpenAI** — Microsoft's hosted OpenAI-compatible service
- **Any LLM gateway** that exposes `/v1/chat/completions`

### Example: Red Hat MaaS

```bash
# deploy/.env
VLLM_BASE_URL=https://litellm-prod.apps.maas.redhatworkshops.io
VLLM_API_KEY=sk-your-api-key
VLLM_INTENT_MODEL=granite-3-2-8b-instruct
VLLM_RESEARCHER_MODEL=qwen3-14b
VLLM_ORCHESTRATOR_MODEL=qwen3-14b
VLLM_SUMMARY_MODEL=granite-3-2-8b-instruct
VLLM_ORCHESTRATOR_MAX_TOKENS=16384
```

Then start with the vLLM config:

```bash
nat serve --config_file configs/config_web_vllm.yml
```

### Key Difference from Local vLLM

Local vLLM typically does not require an API key, so the default `api_key: ${VLLM_API_KEY:-no-key}` works without setting anything. MaaS endpoints require a real key — set `VLLM_API_KEY` in your `.env` file or environment.

The config validator handles both cases: if the `api_key` field has a non-empty default (like `no-key`), the env var is treated as optional. If no default is provided (e.g., `${VLLM_API_KEY}`), the validator requires it to be set.


## Config Validation and API Keys

The config validator (`src/aiq_agent/common/config_validation.py`) performs two stages of validation at startup:

### Stage 1: API Key Validation (Synchronous)

Checks that required API keys are present in the environment.

**Rules:**
- `_type: nim` → requires `NVIDIA_API_KEY`
- `_type: openai` with cloud `base_url` → requires `OPENAI_API_KEY`
- `_type: openai` with local/private `base_url` → no key required
- Explicit `api_key: ${VAR:-default}` with a non-empty default → no env var required
- Explicit `api_key: ${VAR}` without default → `VAR` must be set

**Private endpoint heuristic:** If `base_url` resolves to any of these hosts, the API key check is skipped:
- `localhost`, `127.0.0.1`, `0.0.0.0`
- `10.x.x.x`, `192.168.x.x`, `172.x.x.x` (RFC 1918 private ranges)

### Stage 2: Endpoint Probing (Async, Non-blocking)

After API key validation, the system probes each configured OpenAI-compatible endpoint. This runs during startup and logs warnings but does not block the application.

**Checks performed:**
1. **Endpoint reachability** — `GET /v1/models` to verify the server is accessible
2. **Model availability** — configured `model_name` values are cross-checked against the endpoint's reported model list
3. **Context window validation** — for LLMs assigned to deep research roles (orchestrator, planner, researcher), the validator probes the model's context window and warns if:
   - The context window is below 32,768 tokens (minimum recommended for deep research)
   - The configured `max_tokens` exceeds the model's actual context window (which causes `400 Bad Request` at runtime)

**Example startup warnings:**
```
WARNING - Endpoint validation: Model 'qwen3-14b' (configured as 'orchestrator_llm')
  not found on https://maas.example.com. Available models: granite-3-2-8b-instruct

WARNING - Endpoint validation: Config error: 'orchestrator_llm' has max_tokens=128,000
  but model 'qwen3-14b' only supports 40,960 tokens. Requests will fail with 400 Bad
  Request. Reduce max_tokens or use VLLM_ORCHESTRATOR_MAX_TOKENS.

WARNING - Endpoint validation: Deep research may be unreliable: 'orchestrator_llm' uses
  model 'qwen3-14b' with a 16,384-token context window (minimum recommended: 32,768).
```

```{note}
NIM endpoints (`https://integrate.api.nvidia.com`) are skipped during probing since they do not support the standard `/v1/models` listing in the same way.
```


## Reasoning Control (`thinking:`)

### How it works

Reasoning control is **configuration**, not agent code. NAT's `ThinkingMixin` supplies a `thinking:` field on each LLM role, and injects the corresponding directive into every model call:

```yaml
llms:
  orchestrator_llm:
    _type: openai
    model_name: ${VLLM_ORCHESTRATOR_MODEL:-Qwen/Qwen2.5-72B-Instruct}
    thinking: ${VLLM_THINKING:-null}   # null = no directive (safe on any model)
```

| Value | Effect |
| :-- | :-- |
| `null` (default) | No directive. Safe on every model. |
| `false` | Injects `/no_think`. **Nemotron model names only** — raises at config load otherwise. |
| `true` | Injects `/think`, enabling reasoning. |

### Setting it rarely helps — measure before you do

Measured against `nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4` on vLLM, 3 runs each:

| Condition | completion tokens (median) |
| :-- | :-- |
| no directive | 49 |
| `/no_think` | 49 |
| `/think` | 465 |

This build emits **no reasoning trace by default**, so `/no_think` suppresses nothing and costs exactly the same. `/think` turns reasoning on at roughly 9.5x the tokens.

If you are chasing slow deep-research runs on a self-hosted endpoint, reasoning suppression is not the lever. Look instead at KV-cache sizing (`--max-model-len` vs `--gpu-memory-utilization`) and at `max_tokens` — see [vLLM results](vllm-results.md).

### Correction: vLLM does *not* echo directives

Earlier versions of this guide, and a since-removed `get_thinking_prefix()` helper, stated that vLLM passes `/think` through as literal text and that only NIM interprets it. **That is wrong.** vLLM with a reasoning parser consumes the directive cleanly — sending `/think` produced 465 tokens of actual reasoning, and neither `/think` nor `/no_think` ever appeared in the output.

The helper and its NIM-only gate were removed in favour of `thinking:`. See [vLLM decisions](vllm-decisions.md) (Decision 3).

### Do not copy `chat_template_kwargs` into a vLLM config

`chat_template_kwargs` is a NIM field. On a vLLM (`_type: openai`) endpoint it is ignored or warns — use `thinking:` instead.

```yaml
# WRONG - chat_template_kwargs on a vLLM endpoint
llms:
  my_llm:
    _type: openai
    model_name: nvidia/nemotron-3-nano-30b-a3b
    base_url: http://localhost:8080/v1
    chat_template_kwargs:
      enable_thinking: true
```

```yaml
# CORRECT - vLLM
llms:
  my_llm:
    _type: openai
    model_name: nvidia/nemotron-3-nano-30b-a3b
    base_url: http://localhost:8080/v1
    temperature: 0.5
    max_tokens: 4096
    thinking: null
```

```yaml
# CORRECT - NIM, where chat_template_kwargs is expected
llms:
  my_llm:
    _type: nim
    model_name: nvidia/nemotron-3-nano-30b-a3b
    base_url: "https://integrate.api.nvidia.com/v1"
    chat_template_kwargs:
      enable_thinking: true
```


## Choosing Models for Each Role

### Intent Classifier
- Needs: structured JSON output, low latency
- Good choices: `meta-llama/Llama-3.1-8B-Instruct`, `Qwen/Qwen2.5-7B-Instruct`
- Avoid: models that don't reliably produce JSON

### Researcher
- Needs: reliable tool calling, synthesis, citation generation
- Good choices: `meta-llama/Llama-3.1-70B-Instruct`, `Qwen/Qwen2.5-72B-Instruct`
- Critical: must support function-call format; start vLLM with `--enable-auto-tool-choice`

### Orchestrator / Planner
- Needs: large context window (128k+ recommended), strong planning and decomposition
- Good choices: `Qwen/Qwen2.5-72B-Instruct` (128k context), `meta-llama/Llama-3.1-70B-Instruct` (128k context)

### Summary
- Needs: fast, concise output
- Good choices: any 7-8B instruct model; speed matters more than quality here


## Mixing Providers

You can use NIM for some roles and vLLM for others in the same config:

```yaml
llms:
  # Fast intent classification via hosted NIM (low latency)
  intent_llm:
    _type: nim
    model_name: nvidia/nemotron-3-nano-30b-a3b
    base_url: "https://integrate.api.nvidia.com/v1"
    api_key: ${NVIDIA_API_KEY}
    temperature: 0.5
    max_tokens: 4096

  # Research via local vLLM (data privacy)
  researcher_llm:
    _type: openai
    model_name: meta-llama/Llama-3.1-70B-Instruct
    base_url: http://localhost:8000/v1
    api_key: no-key
    temperature: 0.1
    max_tokens: 16384
```

This is useful when you want hosted NIM for latency-sensitive paths (intent classification) but local vLLM for research tasks where data stays on-premise.


## Deep Research: Model Requirements and Limitations

Deep research is the most demanding agent path. It involves multi-loop orchestration, parallel tool calling, source aggregation, and long-form report generation. The orchestrator and planner LLMs carry the heaviest load.

### Minimum Requirements for Deep Research

| Requirement | Minimum | Recommended | Why |
|-------------|---------|-------------|-----|
| Context window | 32k tokens | 128k+ tokens | Multi-source aggregation and report writing |
| Model size | 14B+ | 70B+ | Reliable multi-step planning and tool use |
| Tool calling | Required | Required | Orchestrator must dispatch sub-tasks |
| Inference speed | Moderate | Fast | Multi-loop = many sequential LLM calls |

### What Happens When Models Are Too Small

During testing with `qwen3-14b` (40k context) on a Red Hat MaaS endpoint:

- **Shallow research worked perfectly** — single-loop, limited context, fast responses
- **Deep research failed** — the orchestrator hit context window limits during report generation, causing `400 Bad Request` errors from the endpoint

The startup validator now detects this mismatch and logs a warning. If you see these warnings, consider:

1. **Using a larger model** for the orchestrator/planner roles (70B+ with 128k context)
2. **Reducing `max_tokens`** via `VLLM_ORCHESTRATOR_MAX_TOKENS` to fit within the model's context window
3. **Disabling deep research** and using only shallow research for smaller deployments

### Configuring max_tokens per Role

The `max_tokens` for the orchestrator is configurable via environment variable:

```yaml
# In config_web_vllm.yml
orchestrator_llm:
  max_tokens: ${VLLM_ORCHESTRATOR_MAX_TOKENS:-128000}
```

```bash
# In deploy/.env — cap for smaller models
VLLM_ORCHESTRATOR_MAX_TOKENS=16384
```


## Troubleshooting

**Model returns empty responses**
- Check that `--served-model-name` in your vLLM command matches the `model_name` in the config
- Verify the model is fully loaded: `curl http://localhost:8000/v1/models`

**Tool calls not working**
- Ensure vLLM is started with `--enable-auto-tool-choice --tool-call-parser hermes`
- Verify the model supports function calling (not all models do)

**API key errors on startup**
- Confirm `base_url` resolves to a private IP so validation skips the key check
- Or set `api_key: no-key` explicitly in the config

**400 Bad Request from deep research**
- Check startup logs for context window warnings
- The model's context window may be smaller than `max_tokens` in the config
- Set `VLLM_ORCHESTRATOR_MAX_TOKENS` to a value within the model's context window
- Verify with: `curl -H "Authorization: Bearer $VLLM_API_KEY" $VLLM_BASE_URL/v1/models`

**`/think` or `/no_think` appears as literal text in output**
- Unlikely on vLLM with a reasoning parser configured — it consumes these directives cleanly (verified). If you do see them, the server is running without a `--reasoning-parser`
- Check whether anything is prepending directives to the prompt itself; `thinking:` is the supported mechanism and is injected by NAT, not by prompt text
- Verify your config uses `_type: openai` (not `_type: nim`) for vLLM endpoints
- Do NOT add `chat_template_kwargs` to vLLM configs

**`<think>...</think>` blocks appear in output**
- The model is producing reasoning tokens (separate from `/think` directives)
- This happens with reasoning-capable models (Nemotron with thinking enabled, DeepSeek-R1, Qwen QwQ)
- For vLLM: use `--reasoning-parser deepseek_r1` flag when starting vLLM to separate reasoning from output
- For NIM: ensure `enable_thinking` is set appropriately in `chat_template_kwargs`

**Timeout or connection errors**
- Check vLLM is running and accessible: `curl http://localhost:8000/v1/models`
- For remote vLLM, verify firewall rules allow the connection

**MaaS API key errors**
- Ensure `VLLM_API_KEY` is set in your environment or `.env` file
- The default `no-key` works for local vLLM but not for authenticated gateways

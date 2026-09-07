<!--
SPDX-FileCopyrightText: Copyright (c) 2025-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# vLLM Model Recipes

Tested configurations for serving open models with vLLM on the AI-Q Blueprint. Each recipe includes the Docker command, `deploy/.env` settings, and observed performance on a specific GPU.

**Contributing:** Add your own recipe by copying a section below and filling in your model, GPU, and observations. We welcome results from any hardware.

---

## How to use a recipe

1. Start vLLM with the Docker command from the recipe
2. Copy the `deploy/.env` block into your `deploy/.env`
3. Start AI-Q: `./scripts/start_e2e.sh --config_file configs/config_web_vllm.yml`

All recipes use `configs/config_web_vllm.yml` which routes all LLMs through OpenAI-compatible endpoints.

---

## Nemotron-3-Nano-30B-A3B (BF16)

| | |
|---|---|
| **Model** | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16` |
| **Architecture** | MoE (30B total, 3B active) — Hybrid Mamba-Transformer |
| **Context window** | 131,072 tokens (256k native, capped for memory) |
| **License** | NVIDIA custom |
| **HuggingFace** | [nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16) |

### GPU: NVIDIA DGX Spark (GB10, 128GB unified)

**Docker command:**

```bash
docker run --privileged --gpus all -d --rm \
  --name vllm-nemotron \
  --network host --ipc=host \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  nvcr.io/nvidia/vllm:26.01-py3 \
  vllm serve nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16 \
  --served-model-name nvidia/nemotron-3-nano-30b-a3b \
  --max-num-seqs 8 \
  --tensor-parallel-size 1 \
  --max-model-len 131072 \
  --port 8080 \
  --trust-remote-code \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder \
  --gpu-memory-utilization 0.7
```

**deploy/.env:**

```bash
VLLM_BASE_URL=http://localhost:8080
VLLM_API_KEY=no-key
VLLM_INTENT_MODEL=nvidia/nemotron-3-nano-30b-a3b
VLLM_RESEARCHER_MODEL=nvidia/nemotron-3-nano-30b-a3b
VLLM_ORCHESTRATOR_MODEL=nvidia/nemotron-3-nano-30b-a3b
VLLM_SUMMARY_MODEL=nvidia/nemotron-3-nano-30b-a3b
VLLM_ORCHESTRATOR_MAX_TOKENS=98000
```

**Performance:**

| Metric | Value |
|--------|-------|
| vLLM image | `nvcr.io/nvidia/vllm:26.01-py3` (v0.13.0) |
| Weight size | ~59 GB (BF16) |
| GPU memory (weights + KV) | ~85 GB of 128 GB |
| KV cache | 22.95 GiB / 800,672 tokens |
| Prompt throughput | 57–335 tok/s |
| Generation throughput | ~29 tok/s (stock NGC image) |
| Attention backend | FLASH_ATTN |
| First token latency | ~2-5s (depends on prompt length) |
| Model load time | ~6 min (weight download) + ~6 min (shard loading) |
| Shallow research | Works |
| Deep research | Works (with max_tokens=98000) |
| Thinking prefixes | `/think` and `/no_think` auto-detected |

**Notes:**
- The NGC image (v0.13.0) ships without native SM121 (Blackwell) kernels. Building from source with `TORCH_CUDA_ARCH_LIST="12.0"` can improve throughput from ~29 to ~49 tok/s (community reports).
- Set `--gpu-memory-utilization 0.7` or lower — unified memory means GPU and CPU share the 128GB pool.
- `/no_think` prefix does not reliably suppress thinking tokens without the `--reasoning-parser` plugin.
- Use `--tool-call-parser qwen3_coder` for tool calling support.

---

## Gemma 4 26B-A4B (BF16)

| | |
|---|---|
| **Model** | `google/gemma-4-26B-A4B-it` |
| **Architecture** | MoE (26B total, 4B active) — 128 experts, top-8 routing |
| **Context window** | Up to 131,072 tokens (limited by GPU memory) |
| **License** | Apache 2.0 |
| **HuggingFace** | [google/gemma-4-26B-A4B-it](https://huggingface.co/google/gemma-4-26B-A4B-it) |

### GPU: NVIDIA DGX Spark (GB10, 128GB unified)

**Docker command:**

```bash
docker run --privileged --gpus all -d --rm \
  --name vllm-gemma4 \
  --network host --ipc=host \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  --entrypoint "" \
  vllm/vllm-openai:latest \
  bash -c "pip install --upgrade transformers 2>&1 | tail -3 && \
  python3 -m vllm.entrypoints.openai.api_server \
  --model google/gemma-4-26B-A4B-it \
  --served-model-name google/gemma-4-26b-a4b-it \
  --max-num-seqs 4 \
  --tensor-parallel-size 1 \
  --max-model-len 8192 \
  --port 8080 \
  --trust-remote-code \
  --enable-auto-tool-choice \
  --tool-call-parser pythonic \
  --gpu-memory-utilization 0.90"
```

**deploy/.env:**

```bash
VLLM_BASE_URL=http://localhost:8080
VLLM_API_KEY=no-key
VLLM_INTENT_MODEL=google/gemma-4-26b-a4b-it
VLLM_RESEARCHER_MODEL=google/gemma-4-26b-a4b-it
VLLM_ORCHESTRATOR_MODEL=google/gemma-4-26b-a4b-it
VLLM_SUMMARY_MODEL=google/gemma-4-26b-a4b-it
VLLM_RESEARCHER_MAX_TOKENS=4096
VLLM_ORCHESTRATOR_MAX_TOKENS=4096
```

**Performance:**

| Metric | Value |
|--------|-------|
| vLLM image | `vllm/vllm-openai:latest` (v0.19.0) + transformers 5.5.0 |
| Weight size | ~49 GB (BF16) |
| GPU memory (weights + KV) | ~68 GB of 128 GB |
| KV cache | 60.17 GiB / 262,880 tokens |
| Prompt throughput | ~62-65 tok/s |
| Generation throughput | ~7 tok/s |
| Attention backend | TRITON_ATTN |
| Model load time | ~5 min (shard loading) + ~1 min (CUDA graph compile) |
| Shallow research | **Fails** (tool calling incompatible — see notes) |
| Deep research | Limited (8k context constrains report length) |
| Thinking prefixes | Not applicable (not a Nemotron model) |
| Tool calling | **Not working** — `gemma4` parser not available in vLLM 0.19.0 |

**Notes:**
- Gemma 4 is very new — the NGC vLLM image (v0.13.0) does not support the `gemma4` architecture. Use the upstream `vllm/vllm-openai:latest` image with `pip install --upgrade transformers` at container startup.
- **Tool calling does not work.** Gemma 4 uses a custom format (`call:func{args}`) that requires the `gemma4` tool call parser, which is not yet available in vLLM 0.19.0. The `pythonic` and `hermes` parsers do not recognize this format. Without tool calling, the shallow researcher cannot invoke web search, and citation verification rejects all responses. This will be resolved when vLLM ships with native `gemma4` parser support.
- The upstream vLLM image uses significantly more GPU memory for CUDA graphs and profiling than the NGC image. Context window is limited to 8192 to leave room for KV cache. At 32k context, `num_gpu_blocks=0` (no KV cache).
- No MoE config file exists for the GB10 yet (`E=128,N=704,device_name=NVIDIA_GB10.json`). Performance may improve when one is available.
- Gemma 4 produces clean responses with no thinking token leakage.
- Apache 2.0 license — no HuggingFace token or license agreement required.

---

## Qwen3.5-35B-A3B (BF16)

| | |
|---|---|
| **Model** | `Qwen/Qwen3.5-35B-A3B` |
| **Architecture** | MoE (36B total, 3B active) — 256 experts, Mamba-Transformer hybrid |
| **Context window** | 262k native (32k recommended on DGX Spark) |
| **License** | Apache 2.0 |
| **HuggingFace** | [Qwen/Qwen3.5-35B-A3B](https://huggingface.co/Qwen/Qwen3.5-35B-A3B) |

### GPU: NVIDIA DGX Spark (GB10, 128GB unified)

**Docker command:**

```bash
docker run --privileged --gpus all -d --rm \
  --name vllm-qwen \
  --network host --ipc=host \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  --entrypoint "" \
  vllm/vllm-openai:latest \
  bash -c "pip install --upgrade transformers 2>&1 | tail -3 && \
  python3 -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen3.5-35B-A3B \
  --served-model-name qwen/qwen3.5-35b-a3b \
  --max-num-seqs 4 \
  --tensor-parallel-size 1 \
  --max-model-len 32768 \
  --port 8080 \
  --trust-remote-code \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder \
  --reasoning-parser deepseek_r1 \
  --enforce-eager \
  --gpu-memory-utilization 0.90"
```

**deploy/.env:**

```bash
VLLM_BASE_URL=http://localhost:8080
VLLM_API_KEY=no-key
VLLM_INTENT_MODEL=qwen/qwen3.5-35b-a3b
VLLM_RESEARCHER_MODEL=qwen/qwen3.5-35b-a3b
VLLM_ORCHESTRATOR_MODEL=qwen/qwen3.5-35b-a3b
VLLM_SUMMARY_MODEL=qwen/qwen3.5-35b-a3b
VLLM_RESEARCHER_MAX_TOKENS=8192
VLLM_ORCHESTRATOR_MAX_TOKENS=16000
```

**Performance:**

| Metric | Value |
|--------|-------|
| vLLM image | `vllm/vllm-openai:latest` (v0.19.0) + transformers 5.5.0 |
| Weight size | ~67 GB (BF16) |
| GPU memory (weights + KV) | ~90 GB of 128 GB |
| KV cache | 39 GiB / 514,272 tokens |
| Generation throughput | ~28-30 tok/s |
| Tool call latency | ~14s (warm), ~51s (cold) |
| Attention backend | TRITON_ATTN |
| Model load time | ~20 min (first download) + ~1.5 min (shard loading) |
| Shallow research | Works |
| Deep research | Works at 32k (short reports) |
| Tool calling | Works (`qwen3_coder` + `deepseek_r1` reasoning parser) |

**Notes:**
- Requires `--enforce-eager` to unlock context beyond 8k. Without it, CUDA graph compilation consumes all remaining GPU memory, forcing `num_gpu_blocks=0` at 32k+.
- **Both parsers are required:** `--tool-call-parser qwen3_coder` for tool calls AND `--reasoning-parser deepseek_r1` for thinking token separation. Without the reasoning parser, `<think>` tags appear before `<tool_call>` tags and break tool call parsing.
- Qwen3.5-35B-A3B is a Feb 2026 model and requires `pip install --upgrade transformers` inside the container (not recognized by the bundled transformers).
- `--enforce-eager` increases first-token latency significantly but generation throughput is similar (~28-30 tok/s).
- For 64k context, change `--max-model-len 65536` — tool call latency increases to ~51s but deep research can generate longer reports.
- Apache 2.0 license — no restrictions.

---

## Mistral-Small-24B-Instruct (BF16)

| | |
|---|---|
| **Model** | `mistralai/Mistral-Small-24B-Instruct-2501` |
| **Architecture** | Dense (24B, all active) |
| **Context window** | 32,768 tokens |
| **License** | Apache 2.0 |
| **HuggingFace** | [mistralai/Mistral-Small-24B-Instruct-2501](https://huggingface.co/mistralai/Mistral-Small-24B-Instruct-2501) |

### GPU: NVIDIA DGX Spark (GB10, 128GB unified)

**Docker command:**

```bash
docker run --privileged --gpus all -d --rm \
  --name vllm-mistral \
  --network host --ipc=host \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  nvcr.io/nvidia/vllm:26.01-py3 \
  vllm serve mistralai/Mistral-Small-24B-Instruct-2501 \
  --served-model-name mistral-small-24b \
  --max-num-seqs 8 \
  --tensor-parallel-size 1 \
  --max-model-len 32768 \
  --port 8080 \
  --trust-remote-code \
  --enable-auto-tool-choice \
  --tool-call-parser mistral \
  --gpu-memory-utilization 0.80
```

**deploy/.env:**

```bash
VLLM_BASE_URL=http://localhost:8080
VLLM_API_KEY=no-key
VLLM_INTENT_MODEL=mistral-small-24b
VLLM_RESEARCHER_MODEL=mistral-small-24b
VLLM_ORCHESTRATOR_MODEL=mistral-small-24b
VLLM_SUMMARY_MODEL=mistral-small-24b
VLLM_RESEARCHER_MAX_TOKENS=8192
VLLM_ORCHESTRATOR_MAX_TOKENS=16000
```

**Performance:**

| Metric | Value |
|--------|-------|
| vLLM image | `nvcr.io/nvidia/vllm:26.01-py3` (v0.13.0) |
| Weight size | ~44 GB (BF16) |
| GPU memory (weights + KV) | ~79 GB of 128 GB |
| KV cache | 49.20 GiB / 322,400 tokens |
| Generation throughput | **~5 tok/s** |
| Tool call latency | ~4.5s |
| Attention backend | FLASH_ATTN |
| Model load time | ~14 min download + ~4 min shard loading |
| Shallow research | Works |
| Deep research | Limited (slow generation) |
| Tool calling | Works (`mistral` parser — most mature in vLLM) |

**Notes:**
- **Tool calling is excellent.** The `mistral` parser is the most mature and reliable in vLLM. Clean structured `tool_calls` on first attempt, no reasoning parser needed.
- **Generation is slow (~5 tok/s).** This is a 24B dense model — all parameters are active on every token, unlike MoE models where only 3-4B are active. The DGX Spark's GB10 compute is not sufficient for fast dense inference at this size.
- Works on the NGC image (v0.13.0) without transformers upgrades — no compatibility issues.
- 32k context works out of the box with FLASH_ATTN and CUDA graphs — no `--enforce-eager` needed.
- Best suited as an **intent classifier or tool-calling router** where latency matters more than throughput (4.5s tool calls are fast). Not recommended as the primary researcher model due to slow generation.
- Apache 2.0 license.

---

## Kimi K2.5 — MaaS (Red Hat OpenShift)

| | |
|---|---|
| **Model** | Kimi K2.5 (Moonshot AI) |
| **Architecture** | MoE (~1T total, ~32B active) |
| **Context window** | 262,144 tokens |
| **License** | MIT |
| **Serving** | Red Hat MaaS on OpenShift (remote endpoint, not local) |

### Endpoint: Red Hat MaaS

This is a **remote MaaS endpoint**, not a local Docker container. No GPU required on the client.

**deploy/.env:**

```bash
VLLM_BASE_URL=http://maas.apps.ocp.cloud.rhai-tmm.dev/kimi-k25/kimi-k2-5
VLLM_API_KEY=<your-bearer-token>
VLLM_INTENT_MODEL=kimi-k2-5
VLLM_RESEARCHER_MODEL=kimi-k2-5
VLLM_ORCHESTRATOR_MODEL=kimi-k2-5
VLLM_SUMMARY_MODEL=kimi-k2-5
VLLM_RESEARCHER_MAX_TOKENS=8192
VLLM_ORCHESTRATOR_MAX_TOKENS=98000
```

**Performance:**

| Metric | Value |
|--------|-------|
| Endpoint | Red Hat MaaS (OpenShift, vLLM backend) |
| Generation throughput | ~101 tok/s |
| Tool call latency | ~0.95s |
| Simple chat latency | ~3.75s (incl. reasoning tokens) |
| Long generation (1190 tokens) | ~11.7s |
| Context window | 262,144 tokens |
| Shallow research | Works |
| Deep research | Works (262k context supports full reports) |
| Tool calling | Works (kimi_k2 parser, server-side) |

**Notes:**
- No local GPU needed — inference runs on the MaaS cluster.
- Kimi K2.5 generates reasoning tokens before content. A request for 100 content tokens may produce 200-300 total tokens. Account for this in `max_tokens` settings.
- Auth uses Kubernetes ServiceAccount JWT tokens with expiry. Rotate before `exp` claim.
- 262k context is the largest we've tested — deep research works without token budget constraints.
- For detailed K8s admin info, see [MaaS Kimi K2.5 Guide](./maas-kimi-k25.md).

---

## Template: Add your own recipe

Copy this section, fill in the details, and submit a PR.

### Model Name (Quantization)

| | |
|---|---|
| **Model** | `org/model-name` |
| **Architecture** | Dense / MoE (Xb total, Yb active) |
| **Context window** | X tokens |
| **License** | License name |
| **HuggingFace** | org/model-name |

### GPU: Your GPU (VRAM)

**Docker command:**

```bash
docker run --privileged --gpus all -d --rm \
  --name vllm-model \
  --network host --ipc=host \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  <vllm-image> \
  vllm serve org/model-name \
  --served-model-name org/model-name \
  --max-num-seqs 8 \
  --max-model-len <context> \
  --port 8080 \
  --trust-remote-code \
  --gpu-memory-utilization <0.7-0.9>
```

**deploy/.env:**

```bash
VLLM_BASE_URL=http://localhost:8080
VLLM_API_KEY=no-key
VLLM_INTENT_MODEL=org/model-name
VLLM_RESEARCHER_MODEL=org/model-name
VLLM_ORCHESTRATOR_MODEL=org/model-name
VLLM_SUMMARY_MODEL=org/model-name
VLLM_RESEARCHER_MAX_TOKENS=<value>
VLLM_ORCHESTRATOR_MAX_TOKENS=<value>
```

**Performance:**

| Metric | Value |
|--------|-------|
| vLLM image | image:tag (version) |
| Weight size | X GB |
| GPU memory used | X GB of Y GB |
| KV cache | X GiB / Y tokens |
| Prompt throughput | X tok/s |
| Generation throughput | X tok/s |
| Shallow research | Works / Fails |
| Deep research | Works / Limited / Fails |
| Tool calling | Works (parser) / Not tested |

**Notes:**
- Any gotchas, tips, or observations.

---

## Recommended models by use case

| Use case | Recommended model | Why |
|----------|------------------|-----|
| **Full deep research (MaaS)** | Kimi K2.5 via MaaS | 262k context, ~101 tok/s, native tool calling, no local GPU needed |
| **Full deep research (local)** | Nemotron-3-Nano-30B-A3B | 131k context, native thinking, tool calling |
| **Shallow research (local)** | Nemotron-3-Nano-30B-A3B | Tool calling works reliably with `qwen3_coder` parser |
| **Chat / Q&A (no tools)** | Gemma 4 26B-A4B | Clean output, Apache 2.0 — but tool calling not yet supported in vLLM |
| **Memory-constrained** | Gemma 4 E4B (4B) | Fits easily, good for intent classification and summaries |

## Key constraints by context window

| Context window | Suitable for | `VLLM_ORCHESTRATOR_MAX_TOKENS` | `VLLM_RESEARCHER_MAX_TOKENS` |
|---------------|-------------|-------------------------------|------------------------------|
| 8k | Shallow research only | 4,096 | 4,096 |
| 32k | Shallow + short deep research | 16,000 | 8,192 |
| 64k | Shallow + medium deep research | 40,000 | 16,384 |
| 128k+ | Full deep research reports | 98,000 | 16,384 |

Deep research generates multi-section reports with citations. The orchestrator needs the most context (plan + accumulated research + report generation). If your model has less than 32k context, expect deep research to fail or produce truncated reports.

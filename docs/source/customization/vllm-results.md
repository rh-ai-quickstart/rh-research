<!--
SPDX-FileCopyrightText: Copyright (c) 2025-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# vLLM Model Test Results

Comparative results from testing open models with the AI-Q Blueprint. All local tests performed on NVIDIA DGX Spark (GB10, 128GB unified memory). MaaS tests performed from DGX Spark client against Red Hat OpenShift endpoints.

**Date:** 2026-04-08

---

## Summary Table

| | Nemotron-3-Nano | Gemma 4 26B-A4B | Qwen3.5-35B-A3B | Mistral-Small-24B | Kimi K2.5 (MaaS) |
|---|---|---|---|---|---|
| **Hosting** | Local (DGX Spark) | Local (DGX Spark) | Local (DGX Spark) | Local (DGX Spark) | Remote (Red Hat MaaS) |
| **Params** | 30B / 3B active | 26B / 4B active | 35B / 3B active | 24B / 24B active (dense) | ~1T / ~32B active |
| **vLLM image** | NGC 0.13.0 | Upstream 0.19.0 | Upstream 0.19.0 | NGC 0.13.0 | Server-side |
| **Context** | 131k | 8k | 32k (`--enforce-eager`) | 32k | 262k |
| **Gen throughput** | ~29 tok/s | ~7 tok/s | ~28-30 tok/s | **~5 tok/s** | ~101 tok/s |
| **Tool calling** | Works (`qwen3_coder`) | Broken (no parser) | Works (`qwen3_coder` + `deepseek_r1`) | Works (`mistral`) | Works (native `kimi_k2`) |
| **Tool call latency** | ~2-3s | N/A | ~14s warm, ~51s cold | ~4.5s | ~0.95s |
| **Shallow research** | Works | Fails | Works | Works (slow) | Works |
| **Deep research** | Works | Fails (8k too small) | Short reports (32k) | Limited (slow gen) | Works (262k) |
| **Thinking tokens** | Leak without reasoning parser | None | Separated via `deepseek_r1` | None | Separated natively |
| **GPU memory** | ~85 GB | ~68 GB | ~90 GB | ~79 GB | N/A (remote) |
| **KV cache** | 23 GiB / 800k tokens | 60 GiB / 263k tokens | 39 GiB / 514k tokens | 49 GiB / 322k tokens | N/A |
| **License** | NVIDIA custom | Apache-2.0 | Apache-2.0 | Apache-2.0 | MIT |

---

## Detailed Results

### Nemotron-3-Nano-30B-A3B (Local, NGC vLLM 0.13.0)

| Metric | Value |
|--------|-------|
| vLLM image | `nvcr.io/nvidia/vllm:26.01-py3` (v0.13.0) |
| Weight size | ~59 GB (BF16) |
| GPU memory used | ~85 GB of 128 GB |
| KV cache | 22.95 GiB / 800,672 tokens |
| Prompt throughput | 57-335 tok/s |
| Generation throughput | ~29 tok/s |
| Attention backend | FLASH_ATTN |
| Tool call parser | `qwen3_coder` |
| Context window | 131,072 tokens |
| Model load time | ~6 min download + ~6 min shard loading |

**Strengths:** Largest local context (131k), deep research works, NGC image is memory-efficient.
**Weaknesses:** `/no_think` doesn't suppress thinking tokens without reasoning parser plugin. Stock NGC image lacks native SM121 kernels (~29 tok/s vs potential ~49 tok/s with source build).

### Gemma 4 26B-A4B (Local, upstream vLLM 0.19.0)

| Metric | Value |
|--------|-------|
| vLLM image | `vllm/vllm-openai:latest` (v0.19.0) + transformers 5.5.0 |
| Weight size | ~49 GB (BF16) |
| GPU memory used | ~68 GB of 128 GB |
| KV cache | 60.17 GiB / 262,880 tokens |
| Prompt throughput | ~62-65 tok/s |
| Generation throughput | ~7 tok/s |
| Attention backend | TRITON_ATTN |
| Tool call parser | None working (`gemma4` not available) |
| Context window | 8,192 tokens (limited by CUDA graph memory) |
| Model load time | ~5 min shard loading + ~1 min compile |

**Strengths:** Clean output (no thinking token leakage), Apache-2.0 license, smallest weight footprint.
**Weaknesses:** Tool calling completely broken (no `gemma4` parser in vLLM 0.19.0). Model answers from memory, citation verification rejects all responses. Context limited to 8k due to upstream vLLM memory overhead. Slowest generation (7 tok/s).

### Qwen3.5-35B-A3B (Local, upstream vLLM 0.19.0)

| Metric | Value |
|--------|-------|
| vLLM image | `vllm/vllm-openai:latest` (v0.19.0) + transformers 5.5.0 |
| Weight size | ~67 GB (BF16) |
| GPU memory used | ~90 GB of 128 GB |
| KV cache | 39-42 GiB (depends on `--enforce-eager`) |
| Generation throughput | ~28-30 tok/s |
| Attention backend | TRITON_ATTN |
| Tool call parser | `qwen3_coder` + `deepseek_r1` reasoning parser |
| Model load time | ~20 min download + ~1.5 min shard loading |

#### Context Window vs CUDA Graph Tradeoff

The upstream vLLM 0.19.0 image uses 30-40GB for CUDA graph compilation. Adding `--enforce-eager` disables CUDA graphs, freeing that memory for KV cache but increasing first-token latency.

| Config | Context | KV Cache | Tool call latency | Gen throughput | Deep research |
|--------|---------|----------|-------------------|----------------|---------------|
| CUDA graphs (default) | 8,192 | 38 GiB | ~2-3s | ~30 tok/s | Fails (too small) |
| `--enforce-eager`, 32k | **32,768** | 39 GiB | ~14s (warm) | ~28 tok/s | Short reports |
| `--enforce-eager`, 64k | 65,536 | 42 GiB | ~51s (cold) | ~29 tok/s | Full reports |

**Recommended:** `--enforce-eager` with 32k context — balances usable deep research with acceptable latency.

**Strengths:** Fast generation (~28-30 tok/s), tool calling works with correct parser combo, thinking tokens properly separated. Best local model for research with tool calling. `--enforce-eager` unlocks 32-64k context.
**Weaknesses:** `--enforce-eager` increases first-token latency significantly (~14s warm, ~51s cold). Requires both `--tool-call-parser qwen3_coder` AND `--reasoning-parser deepseek_r1` — without the reasoning parser, `<think>` tags break tool call parsing.

### Kimi K2.5 (Red Hat MaaS, remote)

| Metric | Value |
|--------|-------|
| Endpoint | Red Hat MaaS on OpenShift |
| Generation throughput | ~101 tok/s |
| Tool call latency | ~0.95s |
| Simple chat latency | ~3.75s (incl. reasoning tokens) |
| Long generation (1190 tokens) | ~11.7s |
| Tool call parser | `kimi_k2` (server-side) |
| Context window | 262,144 tokens |
| Auth | Kubernetes ServiceAccount JWT |

**Strengths:** Fastest throughput (3-4x local models), largest context (262k), native tool calling and reasoning separation, no local GPU needed. Best overall model for AI-Q.
**Weaknesses:** Requires network access to MaaS endpoint. JWT tokens expire (need rotation). Reasoning tokens count toward `max_tokens` budget — a request for 100 content tokens may generate 200-300 total.

---

## Key Findings

### 1. vLLM Image Memory Efficiency

The NGC vLLM image (v0.13.0) is significantly more memory-efficient than the upstream image (v0.19.0) on DGX Spark:

| Image | Nemotron (30B MoE) context | Qwen3.5 (35B MoE) context |
|-------|---------------------------|--------------------------|
| NGC 0.13.0 | **131,072** tokens | Not supported (architecture too new) |
| Upstream 0.19.0 | Not tested | **8,192** tokens (CUDA graphs consume remaining memory) |

The upstream image's CUDA graph compilation and profiling consume ~30-40 GB more memory, drastically reducing KV cache capacity.

### 2. Tool Calling Parser Compatibility

Not all models work with all parsers. The correct combination matters:

| Model | Working parser | Reasoning parser needed? |
|-------|---------------|------------------------|
| Nemotron-3-Nano | `qwen3_coder` | No (but `/no_think` leaks) |
| Gemma 4 | None available | N/A |
| Qwen3.5 | `qwen3_coder` | Yes (`deepseek_r1`) |
| **Mistral-Small-24B** | **`mistral`** | **No — cleanest tool calling of all tested models** |
| Kimi K2.5 | `kimi_k2` (server-side) | Built-in |

### Mixed-Model on Single GPU (Not Recommended)

Tested Granite 3.3-8B (intent, :8081) + Nemotron-3-Nano (research, :8080) on the same GB10. Both models loaded but compute contention made the pipeline impractically slow — each model blocks the other during inference. Total memory fit (~75GB) but the sequential GPU access negated any benefit from using a smaller intent model.

**Verdict:** Mixed-model requires multi-GPU or MaaS endpoints. On single GPU, use one model for all roles.

### Dense vs MoE on DGX Spark

Dense models (all parameters active) are significantly slower than MoE models (few parameters active) on the GB10:

| Architecture | Model | Active params | Throughput |
|-------------|-------|---------------|------------|
| MoE | Nemotron-3-Nano | 3B | ~29 tok/s |
| MoE | Qwen3.5-35B-A3B | 3B | ~28-30 tok/s |
| Dense | Mistral-Small-24B | 24B | ~5 tok/s |
| Dense | Gemma 4 26B-A4B | 4B (MoE) | ~7 tok/s |

**Takeaway:** On DGX Spark, prefer MoE models with small active parameter counts (3-4B). Dense models above ~8B are impractically slow for interactive research.

### 3. Reasoning Token Overhead

Models with thinking/reasoning (Kimi K2.5, Qwen3.5, Nemotron) generate hidden reasoning tokens that count toward `max_tokens`. A "100 token" response may consume 200-300 tokens total. Set `max_tokens` 2-3x higher than the expected content length.

### 4. Context Window is the Bottleneck for Deep Research

Deep research generates multi-section reports with accumulated research context. Models need 32k+ context minimum, ideally 128k+:

| Context | Deep research capability |
|---------|------------------------|
| 8k | Fails or produces truncated reports |
| 32k | Short reports, limited iteration |
| 128k | Full reports with multiple research loops |
| 262k | Unconstrained — full deep research with large source material |

---

## Test Environment

| Component | Value |
|-----------|-------|
| Hardware | NVIDIA DGX Spark (GB10 Grace Blackwell) |
| GPU | NVIDIA GB10, sm_121a (Blackwell) |
| Memory | 128 GB unified (CPU+GPU shared) |
| Architecture | aarch64 (ARM64) |
| CUDA | 13.0 |
| Driver | 580.142 |
| AI-Q Blueprint | v2.1.0-redhat (feature/vllm-migration branch) |
| Config | `configs/config_web_vllm.yml` |

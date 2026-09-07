<!--
SPDX-FileCopyrightText: Copyright (c) 2025-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# MaaS Recipe: Kimi K2.5 (Moonshot AI)

Deployment and performance guide for running the AI-Q Blueprint against a Kimi K2.5 model served via Red Hat Model-as-a-Service (MaaS) on OpenShift.

## Model Overview

| | |
|---|---|
| **Model** | Kimi K2.5 (Moonshot AI) |
| **Architecture** | MoE — 1T total parameters, ~32B active per token |
| **Context window** | 262,144 tokens |
| **Tool calling** | Native — `kimi_k2` parser in vLLM |
| **Reasoning** | Built-in thinking/reasoning with separate `reasoning` field |
| **License** | MIT |

## MaaS Endpoint

| | |
|---|---|
| **Base URL** | `http://maas.apps.ocp.cloud.rhai-tmm.dev/kimi-k25/kimi-k2-5` |
| **Model name** | `kimi-k2-5` |
| **Auth** | Bearer token (Kubernetes ServiceAccount JWT) |
| **Protocol** | OpenAI-compatible `/v1/chat/completions` |
| **Max model length** | 262,144 tokens |

## Quick Start

### 1. Configure deploy/.env

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

### 2. Start AI-Q

```bash
source .venv/bin/activate
./scripts/start_e2e.sh --config_file configs/config_web_vllm.yml
```

### 3. Verify

```bash
curl -s $VLLM_BASE_URL/v1/models -H "Authorization: Bearer $VLLM_API_KEY"
```

## Performance Benchmarks

Measured 2026-04-08 from DGX Spark client against MaaS endpoint.

### Latency

| Request type | Latency | Tokens | Notes |
|-------------|---------|--------|-------|
| Simple chat (3 sentences) | 3.75s | 380 (incl. reasoning) | Includes ~230 reasoning tokens |
| Tool call (web_search) | 0.95s | 89 (incl. reasoning) | Clean structured `tool_calls` response |
| Long generation (5 paragraphs) | 11.7s | 1,190 | ~4800 chars output |

### Throughput

| Metric | Value |
|--------|-------|
| **Generation throughput** | ~101 tok/s |
| **Tokens per request (reasoning)** | ~50-250 (model "thinks" before responding) |
| **Effective content throughput** | ~60-80 tok/s (excluding reasoning tokens) |

### Token Budget

| Role | Recommended max_tokens | Reasoning |
|------|----------------------|-----------|
| Intent classifier | 4,096 | Short classification, low reasoning overhead |
| Researcher | 8,192 | Moderate responses with citations |
| Orchestrator/Planner | 98,000 | Deep research reports need large output budget |
| Summary | 100 | Brief document summaries |

The 262k context window means token budgets can be generous without overflow risk.

## Kubernetes / OpenShift Administration

### Endpoint Architecture

```
Client (AI-Q) → OpenShift Route → Gateway Service → vLLM Pod
```

The MaaS endpoint runs on OpenShift with:
- **Namespace:** `maas-default-gateway-tier-free`
- **Route:** `maas.apps.ocp.cloud.rhai-tmm.dev`
- **Path prefix:** `/kimi-k25/kimi-k2-5`
- **Backend:** vLLM serving the Kimi K2.5 model

### Authentication

Authentication uses Kubernetes ServiceAccount tokens (JWT):
- **Audience:** `maas-default-gateway-sa`
- **Issuer:** `https://kubernetes.default.svc`
- **Token expiry:** Time-limited (check `exp` claim in JWT)
- **Namespace scoped:** Token is bound to `maas-default-gateway-tier-free` namespace

To generate a new token:
```bash
# On the OpenShift cluster
oc create token <service-account-name> \
  --namespace maas-default-gateway-tier-free \
  --audience maas-default-gateway-sa \
  --duration 4h
```

### Health Checks

```bash
# Model availability
curl -s $VLLM_BASE_URL/v1/models -H "Authorization: Bearer $TOKEN"

# Simple inference test
curl -s $VLLM_BASE_URL/v1/chat/completions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model":"kimi-k2-5","messages":[{"role":"user","content":"ping"}],"max_tokens":10}'
```

### Monitoring Considerations

| Metric | What to watch | Threshold |
|--------|-------------|-----------|
| **Response latency (p99)** | Inference latency at the route | > 30s may indicate GPU saturation |
| **Token throughput** | Tokens/s across all concurrent users | Baseline ~101 tok/s per request |
| **Error rate** | 400/500 responses from vLLM | > 1% investigate max_tokens or context overflow |
| **Token expiry** | JWT `exp` claim | Rotate before expiry; AI-Q will get 401s |
| **GPU memory** | vLLM pod GPU utilization | KV cache pressure at high concurrency |
| **Queue depth** | vLLM `Running` + `Waiting` requests | Waiting > 0 sustained = capacity issue |

### Capacity Planning

Kimi K2.5 is a 1T parameter MoE model requiring multi-GPU serving:

| Resource | Estimated requirement |
|----------|---------------------|
| GPU memory | ~400+ GB (FP8) across multiple GPUs |
| GPU type | A100 80GB or H100 80GB (minimum 8x for FP8) |
| vCPU | 32+ cores for tokenization and scheduling |
| System RAM | 128+ GB for weight loading and KV cache offload |
| Network | Low-latency between GPU nodes (NVLink/InfiniBand preferred) |
| Storage | ~800 GB for model weights (FP16) or ~400 GB (FP8) |

### Scaling Notes

- **Concurrency:** With 262k context, each concurrent request can consume significant KV cache. Monitor `GPU KV cache usage` in vLLM metrics.
- **Reasoning overhead:** Kimi K2.5 generates reasoning tokens before content. A request for 100 content tokens may generate 200-300 total tokens. Factor this into capacity planning.
- **Rate limiting:** The `tier-free` namespace may have rate limits. For production workloads, request a dedicated tier.
- **Token rotation:** ServiceAccount tokens expire. Implement automated rotation in your deployment pipeline or use a long-lived token with appropriate security review.

### Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| 401 Unauthorized | Token expired | Generate new token with `oc create token` |
| 400 max_tokens too large | max_tokens + input > 262144 | Reduce `VLLM_ORCHESTRATOR_MAX_TOKENS` |
| Slow responses (> 30s) | GPU saturation or cold start | Check vLLM pod metrics; may need warmup request |
| Empty `content` field | All tokens consumed by reasoning | Increase `max_tokens` (reasoning counts toward limit) |
| `tool_calls: []` with tool text in content | Wrong tool-call-parser on server | Server must use `--tool-call-parser kimi_k2` |

## Comparison with Other MaaS Models

| Model | Context | Tool calling | Throughput | Best for |
|-------|---------|-------------|------------|----------|
| **Kimi K2.5** | 262k | Native (kimi_k2) | ~101 tok/s | Deep research, large reports |
| Qwen3-14B | 40k | hermes/qwen3_coder | ~50 tok/s | Shallow research, cost-effective |
| Granite 3.2-8B | 128k | granite | ~80 tok/s | Intent classification, summaries |

## AI-Q Compatibility

| Feature | Status |
|---------|--------|
| Intent classification | Works |
| Shallow research (with web search) | Works (tool calling verified) |
| Deep research | Works (262k context supports full reports) |
| Thinking prefix (`/think`, `/no_think`) | Not applicable (not Nemotron) |
| Reasoning token separation | Built-in (reasoning field in API response) |
| Citation verification | Works (model calls tools, sources registered) |

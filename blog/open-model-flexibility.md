---
title: "From Vendor Lock-In to Open Model Flexibility: Extending NVIDIA's AI-Q Blueprint"
date: 2026-03-30
tags: [vLLM, open-models, deep-research, AI agents, LLM infrastructure]
---

# From Vendor Lock-In to Open Model Flexibility: Extending NVIDIA's AI-Q Blueprint

The best reference architectures for AI agents come from the companies building the hardware they run on. NVIDIA's AI-Q Blueprint — an enterprise deep research agent that holds top positions on the DeepResearch Bench leaderboards — is a case in point. It's thoughtfully designed, battle-tested, and genuinely production-ready.

But adopting a vendor's reference architecture often means adopting their entire inference stack. AI-Q defaults to NVIDIA NIM endpoints, Nemotron models, and API keys tied to NVIDIA's cloud. For teams that need to run open models, deploy on heterogeneous hardware, or keep data on-premise, that's a constraint worth examining.

We set out to keep everything that makes AI-Q excellent — the two-tier research architecture, the role-based LLM abstraction, the human-in-the-loop clarifier — while making the inference layer genuinely pluggable. Here's what we found.


## Why Model Flexibility Matters

The open model landscape moves fast. In the past year alone, we've seen Llama 3.1, Qwen 2.5, Mistral Large, DeepSeek-R1, and Gemma 2 — each competitive with proprietary alternatives for different workloads. Enterprises evaluating these models face real constraints that don't reduce to "pick the best benchmark score":

- **Cost:** Running a 70B model on your own GPUs is dramatically cheaper than per-token API pricing at scale.
- **Latency:** Self-hosted inference eliminates network round-trips and rate limits.
- **Data residency:** Regulated industries can't send queries to external APIs. Air-gapped deployments are a hard requirement, not a nice-to-have.
- **License terms:** Some models have restrictive commercial licenses. Others don't. The choice should be yours.
- **GPU availability:** Not every deployment has access to the specific hardware a vendor's inference stack requires.

The cost of vendor lock-in isn't switching configs today — it's the prompt engineering, validation logic, and model-specific behaviours that accumulate over time and quietly make switching painful later.


## The Architecture That Makes This Possible

AI-Q's LLM integration is cleaner than most agent frameworks. At its core:

1. **YAML configuration** maps named LLMs to agent roles. Each config entry specifies a `_type` (the provider), a `model_name`, and standard parameters like `temperature` and `max_tokens`.

2. **The `_type` discriminator** in NVIDIA's NeMo Agent Toolkit (NAT) already supports multiple backends: `nim`, `openai`, `dynamo`, `litellm`, `azure_openai`, `aws_bedrock`, and `huggingface`.

3. **A role-based LLM provider** (`LLMProvider`) distributes different models to different agent roles — intent classifier, researcher, orchestrator, planner, summarizer — each with independent model selection.

The critical insight: `_type: openai` creates a LangChain `ChatOpenAI` client, which speaks the OpenAI API protocol. This is the same protocol that vLLM, TGI, Ollama, and dozens of other inference servers implement. The infrastructure for model flexibility was already there — it just wasn't the default path.


## Three Changes That Broke the Lock

### Change 1: A New Config File (Zero Code Changes)

The most impactful change was the simplest. We created `configs/config_web_vllm.yml` — a drop-in replacement that swaps every `_type: nim` to `_type: openai` and points `base_url` to a vLLM server:

```yaml
llms:
  researcher_llm:
    _type: openai
    model_name: ${VLLM_RESEARCHER_MODEL:-meta-llama/Llama-3.1-70B-Instruct}
    base_url: ${VLLM_BASE_URL:-http://localhost:8000}/v1
    api_key: ${VLLM_API_KEY:-no-key}
    temperature: 0.1
    max_tokens: 16384
```

Every model is configurable via environment variables. Switch from Llama to Qwen by changing one env var — no config file editing, no redeployment.

We also omitted `chat_template_kwargs: enable_thinking: true` from the vLLM config. This is a NIM-specific parameter that controls Nemotron's extended chain-of-thought mode. vLLM doesn't support it, and reasoning models served by vLLM handle thinking natively.

### Change 2: Smart Config Validation

AI-Q's config validator maps each provider type to required API keys — `nim` needs `NVIDIA_API_KEY`, `openai` needs `OPENAI_API_KEY`. For a local vLLM server, neither makes sense.

We added private-endpoint detection: if `base_url` resolves to `localhost`, `127.0.0.1`, or any RFC 1918 private address (`10.x`, `192.168.x`, `172.x`), the API key check is skipped. Cloud endpoints still require their keys. The heuristic is simple and covers the vast majority of self-hosted deployments.

### Change 3: Model-Aware Thinking Prefixes

This was the subtlest problem. Nemotron models use `/no_think` and `/think` directives prepended to system prompts to control their reasoning mode. These directives were **hardcoded into prompt templates** — the intent classifier, clarifier agent, and plan generation prompts all started with `/no_think` to disable extended thinking on latency-sensitive paths.

For Nemotron, this is a meaningful performance optimization. For Llama or Qwen, it's literal noise that the model might echo back or misinterpret.

The solution: a `get_thinking_prefix(llm, enable)` function that inspects the LLM's model name at runtime. Nemotron models get their directive; all other models get an empty string. Agent code simply prepends the result:

```python
thinking_prefix = get_thinking_prefix(self.llm, enable=False)
system_content = thinking_prefix + render_prompt_template(self.prompt, **kwargs)
```

One function, checked in one place, extending cleanly to future model families.


## The Rebranding Story

As proof that the frontend is equally customizable, we rebranded the entire UI from NVIDIA to Red Hat — logo, colour palette, fonts, app name, favicon. The approach was deliberately non-invasive: CSS custom property overrides in a single file (`globals.css`) rather than editing the KUI design system source.

The KUI design system uses semantic tokens (`--background-color-interaction-primary-base`, `--text-color-brand`) that reference a colour palette (`--color-green-300`, etc.). Override the palette at the root level, and every button, banner, toggle, and accent colour updates automatically. The entire colour change was 40 lines of CSS.


## What We Learned

**The coupling was shallow.** We expected deep integration with the NIM inference stack. What we found was a config file, a validation function, and a handful of hardcoded prompt tokens. NAT's plugin architecture and LangChain's provider abstraction meant the hard decoupling work was already done.

**The deepest coupling was in prompts, not infrastructure.** The `/no_think` directives embedded in Jinja2 templates were more problematic than any API integration. This is a general pattern in AI systems: you couple to models through prompt engineering more than through code.

**Model-specific optimisations can coexist with model flexibility.** The thinking prefix pattern shows you don't have to choose between "one prompt fits all" and "maintain N prompt variants." Runtime model detection lets you optimise where it matters and stay clean everywhere else.


## What Comes Next

This work opens several paths forward:

- **Runtime model selector:** A UI dropdown to switch model configurations without restarting the server (Phase 4 in our roadmap).
- **Systematic benchmarking:** Evaluating model families against FreshQA and DeepResearch benchmarks to build a tested compatibility matrix.
- **Model-specific prompt optimisation:** The `get_thinking_prefix()` pattern extends naturally to per-model prompt tuning — DeepSeek-R1's `<think>` tokens, Qwen's reasoning format, and whatever comes next.

The code is available in our fork. The [vLLM Migration Guide](../docs/source/customization/vllm-migration.md) has everything you need to point AI-Q at your own inference server in under five minutes.

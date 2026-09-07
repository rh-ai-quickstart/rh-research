# SPDX-FileCopyrightText: Copyright (c) 2025-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""End-to-end tests for vLLM integration.

These tests require a live vLLM server and a running AI-Q backend
configured with configs/config_web_vllm.yml. They are skipped
automatically when the services are not reachable.

Run with:
    pytest tests/aiq_agent/e2e/test_vllm_e2e.py -v

Environment:
    VLLM_BASE_URL  - vLLM server URL (default: http://localhost:8080)
    AIQ_BASE_URL   - AI-Q backend URL (default: http://localhost:8000)
"""

import os
import time

import httpx
import pytest

VLLM_BASE_URL = os.environ.get("VLLM_BASE_URL", "http://localhost:8080")
AIQ_BASE_URL = os.environ.get("AIQ_BASE_URL", "http://localhost:8000")

# ---------------------------------------------------------------------------
# Skip helpers
# ---------------------------------------------------------------------------


def _vllm_reachable() -> bool:
    try:
        r = httpx.get(f"{VLLM_BASE_URL}/v1/models", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def _aiq_reachable() -> bool:
    try:
        r = httpx.get(f"{AIQ_BASE_URL}/health", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


requires_vllm = pytest.mark.skipif(not _vllm_reachable(), reason="vLLM not reachable")
requires_aiq = pytest.mark.skipif(not _aiq_reachable(), reason="AI-Q backend not reachable")
requires_both = pytest.mark.skipif(
    not (_vllm_reachable() and _aiq_reachable()),
    reason="vLLM and/or AI-Q backend not reachable",
)


# ===========================================================================
# 1. vLLM endpoint validation
# ===========================================================================


@requires_vllm
class TestVLLMEndpoint:
    """Verify the vLLM server is healthy and serving the expected model."""

    def test_models_endpoint(self):
        """GET /v1/models returns at least one model."""
        r = httpx.get(f"{VLLM_BASE_URL}/v1/models", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["object"] == "list"
        assert len(data["data"]) >= 1

    def test_served_model_name(self):
        """At least one model is being served."""
        r = httpx.get(f"{VLLM_BASE_URL}/v1/models", timeout=10)
        model_ids = [m["id"] for m in r.json()["data"]]
        assert len(model_ids) >= 1, "No models served"

    def test_health_endpoint(self):
        """vLLM health endpoint responds."""
        r = httpx.get(f"{VLLM_BASE_URL}/health", timeout=10)
        assert r.status_code == 200


# ===========================================================================
# 2. Basic chat completion
# ===========================================================================


@requires_vllm
class TestVLLMChatCompletion:
    """Direct chat completion against vLLM without AI-Q."""

    def _get_model_name(self) -> str:
        r = httpx.get(f"{VLLM_BASE_URL}/v1/models", timeout=10)
        return r.json()["data"][0]["id"]

    # NOTE on max_tokens in this class: vLLM returns ``content: None`` with
    # ``finish_reason: "length"`` when generation is truncated -- no error, just a
    # silent null. Every request below therefore budgets well above the measured
    # need, and asserts on finish_reason so a truncation fails loudly instead of
    # blowing up on ``len(None)``. Measured against
    # nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4 (2026-07-30, 3 runs each):
    # no directive ~49 completion tokens, /no_think ~49, /think ~465.

    @staticmethod
    def _content(response: httpx.Response) -> str:
        """Return message content, failing clearly on truncation rather than on None."""
        choice = response.json()["choices"][0]
        assert choice["finish_reason"] != "length", (
            f"response truncated (finish_reason=length); raise max_tokens. "
            f"completion_tokens={response.json()['usage']['completion_tokens']}"
        )
        content = choice["message"]["content"]
        assert content is not None, f"content was None with finish_reason={choice['finish_reason']}"
        return content

    def test_simple_completion(self):
        """A basic chat completion returns a non-empty response."""
        model = self._get_model_name()
        r = httpx.post(
            f"{VLLM_BASE_URL}/v1/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Say hello in exactly three words."}],
                # ~49 tokens measured; 512 leaves generous headroom.
                "max_tokens": 512,
                "temperature": 0.1,
            },
            timeout=120,
        )
        assert r.status_code == 200
        assert len(self._content(r)) > 0
        assert r.json()["usage"]["completion_tokens"] > 0

    def test_no_think_prefix_suppresses_thinking(self):
        """/no_think is accepted cleanly and does not increase token usage."""
        model = self._get_model_name()
        r = httpx.post(
            f"{VLLM_BASE_URL}/v1/chat/completions",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "/no_think"},
                    {"role": "user", "content": "What is 2+2? One word answer."},
                ],
                "max_tokens": 512,
                "temperature": 0.1,
            },
            timeout=120,
        )
        assert r.status_code == 200
        content = self._content(r)
        # vLLM with a reasoning parser CONSUMES the directive -- it is not echoed
        # as literal text (an earlier assumption in prompt_utils.is_nemotron).
        assert "/no_think" not in content, "directive echoed into content"
        # Measured: /no_think costs the same as no directive (~49 tokens both), because
        # this build does not emit a reasoning trace by default. Suppression is a no-op
        # here, NOT a latency fix -- see docs/source/customization/vllm-results.md.
        assert len(content) > 0, "Empty response with /no_think prefix"

    def test_think_prefix_enables_reasoning(self):
        """/think enables reasoning and materially increases token usage."""
        model = self._get_model_name()
        r = httpx.post(
            f"{VLLM_BASE_URL}/v1/chat/completions",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "/think"},
                    {"role": "user", "content": "What is the square root of 144?"},
                ],
                # ~465 tokens measured with /think (~9.5x the ~49 without it).
                # The previous value of 200 truncated every run.
                "max_tokens": 1024,
                "temperature": 0.1,
            },
            timeout=300,
        )
        assert r.status_code == 200
        content = self._content(r)
        assert "/think" not in content, "directive echoed into content"
        assert len(content) > 10

    def test_max_tokens_respected(self):
        """Setting max_tokens caps the response length."""
        model = self._get_model_name()
        r = httpx.post(
            f"{VLLM_BASE_URL}/v1/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Write a long essay about AI."}],
                "max_tokens": 20,
                "temperature": 0.5,
            },
            timeout=60,
        )
        assert r.status_code == 200
        assert r.json()["usage"]["completion_tokens"] <= 25  # small buffer

    def test_context_window_error(self):
        """Requesting more than context window returns 400."""
        model = self._get_model_name()
        r = httpx.post(
            f"{VLLM_BASE_URL}/v1/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 999_999,
            },
            timeout=30,
        )
        assert r.status_code == 400
        error_text = r.text.lower()
        assert any(
            phrase in error_text
            for phrase in [
                "maximum context length",
                "too large",
                "max_model_len",
                "fewer output tokens",
            ]
        ), f"Unexpected error format: {r.text[:200]}"


# ===========================================================================
# 3. AI-Q backend health and config
# ===========================================================================


@requires_aiq
class TestAIQBackend:
    """Verify the AI-Q backend is running with vLLM config."""

    def test_health(self):
        r = httpx.get(f"{AIQ_BASE_URL}/health", timeout=10)
        assert r.status_code == 200

    def test_data_sources(self):
        """Data sources endpoint lists at least web search."""
        r = httpx.get(f"{AIQ_BASE_URL}/v1/data_sources", timeout=10)
        assert r.status_code == 200
        data = r.json()
        # Response may be a list or a dict with a nested list
        sources = data if isinstance(data, list) else data.get("data_sources", data.get("data", []))
        assert len(sources) > 0


# ===========================================================================
# 4. AI-Q shallow research via async jobs API
# ===========================================================================


@requires_both
class TestShallowResearchE2E:
    """End-to-end shallow research through AI-Q -> vLLM pipeline."""

    def test_shallow_research_completes(self):
        """Submit a shallow research query and verify it reaches a terminal state."""
        # Submit job
        r = httpx.post(
            f"{AIQ_BASE_URL}/v1/jobs/async/submit",
            json={
                "agent_type": "shallow_researcher",
                "input": "What is CUDA?",
            },
            timeout=30,
        )
        assert r.status_code == 200, f"Submit failed: {r.text}"
        job_id = r.json()["job_id"]

        # Poll for completion (timeout 120s for slow inference).
        # These MUST match nat.front_ends.fastapi.async_jobs.job_store.JobStatus:
        # submitted / running / success / failure / interrupted / not_found.
        # A previous version used {"completed", "failed", "cancelled"}, none of which
        # the API ever returns -- so a successful job polled until timeout and the
        # report assertion below was unreachable.
        terminal_states = {"success", "failure", "interrupted", "not_found"}
        deadline = time.time() + 120
        status = None
        while time.time() < deadline:
            r = httpx.get(f"{AIQ_BASE_URL}/v1/jobs/async/job/{job_id}", timeout=10)
            status = r.json()["status"].lower()
            if status in terminal_states:
                break
            time.sleep(3)

        assert status in terminal_states, f"Job {job_id} stuck in {status} after 120s"

        if status == "success":
            # Verify report has content
            r = httpx.get(f"{AIQ_BASE_URL}/v1/jobs/async/job/{job_id}/report", timeout=10)
            if r.status_code == 200:
                report = r.json()
                assert report.get("report") or report.get("output"), f"Empty report for successful job {job_id}"


# ===========================================================================
# 5. AI-Q deep research via async jobs API
# ===========================================================================


@requires_both
class TestDeepResearchE2E:
    """End-to-end deep research — verifies the orchestrator/planner/researcher
    pipeline works against vLLM without max_tokens overflow."""

    def test_deep_research_starts(self):
        """Submit a deep research query and verify it progresses past SUBMITTED."""
        r = httpx.post(
            f"{AIQ_BASE_URL}/v1/jobs/async/submit",
            json={
                "agent_type": "deep_researcher",
                "input": "Explain the DGX Spark architecture in 2-3 paragraphs.",
            },
            timeout=30,
        )
        assert r.status_code == 200, f"Submit failed: {r.text}"
        job_id = r.json()["job_id"]

        # Wait for it to progress past submitted (30s is enough to see it start)
        deadline = time.time() + 60
        status = "submitted"
        while time.time() < deadline:
            r = httpx.get(f"{AIQ_BASE_URL}/v1/jobs/async/job/{job_id}", timeout=10)
            job = r.json()
            status = job["status"].lower()
            error = job.get("error")
            if status != "submitted":
                break
            time.sleep(3)

        assert status != "submitted", f"Job {job_id} never left submitted state"
        # Should be running or completed, not failed with max_tokens error
        if status == "failed":
            assert "max_tokens" not in (error or ""), f"Deep research failed with max_tokens overflow: {error}"


# ===========================================================================
# 6. Endpoint probing integration
# ===========================================================================


@requires_vllm
class TestEndpointProbing:
    """Integration tests for config_validation probing against live vLLM."""

    @pytest.mark.asyncio
    async def test_probe_endpoint_returns_models(self):
        """_probe_endpoint returns reachable=True and the served model."""
        from aiq_agent.common.config_validation import _probe_endpoint

        result = await _probe_endpoint(VLLM_BASE_URL, None)
        assert result["reachable"] is True
        assert len(result["models"]) >= 1
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_probe_context_window(self):
        """_probe_context_window detects the model's context limit."""
        from aiq_agent.common.config_validation import _probe_context_window

        r = httpx.get(f"{VLLM_BASE_URL}/v1/models", timeout=10)
        model_name = r.json()["data"][0]["id"]

        ctx = await _probe_context_window(VLLM_BASE_URL, None, model_name)
        # Context window detection depends on vLLM version error message format.
        # Some versions return None (unrecognized format) — that's acceptable.
        if ctx is not None:
            assert ctx >= 4_096, f"Context window suspiciously small: {ctx}"

    @pytest.mark.asyncio
    async def test_probe_unreachable_endpoint(self):
        """_probe_endpoint handles unreachable servers gracefully."""
        from aiq_agent.common.config_validation import _probe_endpoint

        result = await _probe_endpoint("http://localhost:19999", None, timeout=3.0)
        assert result["reachable"] is False
        assert result["error"] is not None


# ===========================================================================
# 7. LLM config contract (NAT OpenAIModelConfig)
# ===========================================================================


class TestOpenAIModelConfigContract:
    """Guard the two NAT config behaviours the vLLM path depends on.

    Reasoning control is handled by NAT's ``ThinkingMixin`` (the ``thinking:``
    field in configs/config_web_vllm.yml), not by a local helper. The former RH
    ``is_nemotron``/``get_thinking_prefix`` pair was removed because it gated the
    directive on NIM-only endpoints, on the premise that vLLM echoes ``/think``
    as literal text. That premise is false -- vLLM with a reasoning parser
    consumes the directive cleanly (see TestVLLMChatCompletion) -- and what it
    gated is a no-op anyway: measured 2026-07-30, ``/no_think`` costs the same
    ~49 completion tokens as no directive at all.
    """

    def test_max_tokens_passes_through_as_extra(self):
        """max_tokens is UNDECLARED on OpenAIModelConfig and survives only on extra='allow'.

        Every LLM role in config_web_vllm.yml sets max_tokens. If a future NAT
        release tightens this class to extra='forbid', all of them fail config
        load at once -- upstream did exactly that to DeepResearchAgentConfig in
        AI-Q 2.2. See docs/source/customization/vllm-decisions.md (Decision 6).
        """
        from nat.llm.openai_llm import OpenAIModelConfig

        assert OpenAIModelConfig.model_config.get("extra") == "allow", (
            "OpenAIModelConfig is no longer extra='allow'; max_tokens will no longer "
            "pass through and every role in config_web_vllm.yml breaks."
        )
        assert "max_tokens" not in OpenAIModelConfig.model_fields, (
            "max_tokens became a declared field -- update the sizing docs."
        )
        cfg = OpenAIModelConfig(model_name="nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4", max_tokens=8192)
        assert (cfg.model_extra or {}).get("max_tokens") == 8192

    def test_thinking_field_is_available_and_nemotron_gated(self):
        """ThinkingMixin supplies `thinking`, gated to Nemotron model names."""
        from nat.llm.openai_llm import OpenAIModelConfig

        assert "thinking" in OpenAIModelConfig.model_fields

        # Default (unset) is safe on any model -- this is why the config ships
        # `thinking: ${VLLM_THINKING:-null}`.
        assert OpenAIModelConfig(model_name="Qwen/Qwen2.5-72B-Instruct").thinking is None

        # Setting it on a non-Nemotron model is a hard config-load error, so
        # VLLM_THINKING=false against a non-Nemotron default is a footgun.
        with pytest.raises(Exception, match="thinking"):
            OpenAIModelConfig(model_name="Qwen/Qwen2.5-72B-Instruct", thinking=False)

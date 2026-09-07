# SPDX-FileCopyrightText: Copyright (c) 2025-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for config_validation, focusing on local endpoint detection and API key requirements."""

import os
from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest

from aiq_agent.common.config_validation import _extract_env_var
from aiq_agent.common.config_validation import _get_llm_api_key_requirements
from aiq_agent.common.config_validation import _is_local_or_private_endpoint
from aiq_agent.common.config_validation import validate_llm_configs
from aiq_agent.common.config_validation import validate_llm_endpoints


class TestIsLocalOrPrivateEndpoint:
    """Tests for _is_local_or_private_endpoint()."""

    @pytest.mark.parametrize(
        "base_url",
        [
            "http://localhost:8000/v1",
            "http://127.0.0.1:8000/v1",
            "http://0.0.0.0:8000/v1",
            "http://localhost/v1",
        ],
    )
    def test_localhost_variants(self, base_url):
        assert _is_local_or_private_endpoint({"base_url": base_url}) is True

    @pytest.mark.parametrize(
        "base_url",
        [
            "http://10.0.0.5:8000/v1",
            "http://10.255.255.255:8000/v1",
            "http://192.168.1.100:8000/v1",
            "http://192.168.0.1/v1",
            "http://172.16.0.1:8000/v1",
            "http://172.31.255.255:8000/v1",
        ],
    )
    def test_private_ip_ranges(self, base_url):
        assert _is_local_or_private_endpoint({"base_url": base_url}) is True

    @pytest.mark.parametrize(
        "base_url",
        [
            "https://api.openai.com/v1",
            "https://integrate.api.nvidia.com/v1",
            "https://my-company.example.com/v1",
            "https://vllm.cloud-provider.io:8000/v1",
        ],
    )
    def test_public_endpoints(self, base_url):
        assert _is_local_or_private_endpoint({"base_url": base_url}) is False

    def test_env_var_with_local_default(self):
        config = {"base_url": "${VLLM_BASE_URL:-http://localhost:8000}/v1"}
        assert _is_local_or_private_endpoint(config) is True

    def test_env_var_with_private_ip_default(self):
        config = {"base_url": "${VLLM_BASE_URL:-http://192.168.1.50:8000}/v1"}
        assert _is_local_or_private_endpoint(config) is True

    def test_env_var_with_public_default(self):
        config = {"base_url": "${VLLM_BASE_URL:-https://api.openai.com}/v1"}
        assert _is_local_or_private_endpoint(config) is False

    def test_env_var_without_default(self):
        config = {"base_url": "${VLLM_BASE_URL}"}
        assert _is_local_or_private_endpoint(config) is False

    def test_missing_base_url(self):
        assert _is_local_or_private_endpoint({}) is False

    def test_empty_base_url(self):
        assert _is_local_or_private_endpoint({"base_url": ""}) is False

    def test_non_string_base_url(self):
        assert _is_local_or_private_endpoint({"base_url": 12345}) is False


class TestGetLlmApiKeyRequirements:
    """Tests for _get_llm_api_key_requirements()."""

    def test_nim_requires_nvidia_key(self):
        config = {"_type": "nim", "model_name": "nvidia/nemotron"}
        assert _get_llm_api_key_requirements(config) == ["NVIDIA_API_KEY"]

    def test_openai_requires_openai_key(self):
        config = {"_type": "openai", "model_name": "gpt-4", "base_url": "https://api.openai.com/v1"}
        assert _get_llm_api_key_requirements(config) == ["OPENAI_API_KEY"]

    def test_openai_local_endpoint_no_key_required(self):
        config = {"_type": "openai", "model_name": "llama", "base_url": "http://localhost:8000/v1"}
        assert _get_llm_api_key_requirements(config) == []

    def test_explicit_env_var_api_key(self):
        config = {"_type": "nim", "api_key": "${MY_CUSTOM_KEY}"}
        assert _get_llm_api_key_requirements(config) == ["MY_CUSTOM_KEY"]

    def test_literal_api_key_no_env_required(self):
        config = {"_type": "openai", "api_key": "sk-literal-key-value"}  # pragma: allowlist secret
        assert _get_llm_api_key_requirements(config) == []

    def test_unknown_type_no_key_required(self):
        config = {"_type": "custom_provider"}
        assert _get_llm_api_key_requirements(config) == []


class TestValidateLlmConfigs:
    """Tests for validate_llm_configs()."""

    def test_empty_config(self):
        valid, missing = validate_llm_configs({})
        assert valid is True
        assert missing == []

    def test_vllm_local_config_valid_without_env(self):
        config = {
            "llms": {
                "intent_llm": {
                    "_type": "openai",
                    "model_name": "meta-llama/Llama-3.1-8B",
                    "base_url": "http://localhost:8000/v1",
                    "api_key": "no-key",  # pragma: allowlist secret
                },
            }
        }
        valid, missing = validate_llm_configs(config)
        assert valid is True
        assert missing == []

    @patch.dict(os.environ, {}, clear=True)
    def test_nim_config_missing_key(self):
        config = {
            "llms": {
                "test_llm": {
                    "_type": "nim",
                    "model_name": "nvidia/nemotron",
                },
            }
        }
        valid, missing = validate_llm_configs(config)
        assert valid is False
        assert "NVIDIA_API_KEY" in missing

    @patch.dict(os.environ, {"NVIDIA_API_KEY": "test-key"})  # pragma: allowlist secret
    def test_nim_config_with_key(self):
        config = {
            "llms": {
                "test_llm": {
                    "_type": "nim",
                    "model_name": "nvidia/nemotron",
                },
            }
        }
        valid, missing = validate_llm_configs(config)
        assert valid is True
        assert missing == []

    @patch.dict(os.environ, {}, clear=True)
    def test_openai_cloud_missing_key(self):
        config = {
            "llms": {
                "test_llm": {
                    "_type": "openai",
                    "model_name": "gpt-4",
                    "base_url": "https://api.openai.com/v1",
                },
            }
        }
        valid, missing = validate_llm_configs(config)
        assert valid is False
        assert "OPENAI_API_KEY" in missing

    def test_mixed_providers_local_vllm_valid(self):
        """vLLM on local endpoint should not require any API key."""
        config = {
            "llms": {
                "vllm_llm": {
                    "_type": "openai",
                    "model_name": "llama",
                    "base_url": "http://192.168.1.50:8000/v1",
                },
            }
        }
        valid, missing = validate_llm_configs(config)
        assert valid is True
        assert missing == []

    def test_maas_endpoint_with_api_key_default(self):
        """MaaS endpoint with ${VLLM_API_KEY:-no-key} should not require any env var."""
        config = {
            "llms": {
                "researcher_llm": {
                    "_type": "openai",
                    "model_name": "qwen3-14b",
                    "base_url": "https://litellm-prod.apps.maas.example.com/v1",
                    "api_key": "${VLLM_API_KEY:-no-key}",  # pragma: allowlist secret
                },
            }
        }
        valid, missing = validate_llm_configs(config)
        assert valid is True
        assert missing == []

    @patch.dict(os.environ, {}, clear=True)
    def test_maas_endpoint_env_var_no_default_missing(self):
        """MaaS endpoint with ${VLLM_API_KEY} (no default) should require the env var."""
        config = {
            "llms": {
                "researcher_llm": {
                    "_type": "openai",
                    "model_name": "qwen3-14b",
                    "base_url": "https://litellm-prod.apps.maas.example.com/v1",
                    "api_key": "${VLLM_API_KEY}",
                },
            }
        }
        valid, missing = validate_llm_configs(config)
        assert valid is False
        assert "VLLM_API_KEY" in missing

    @patch.dict(os.environ, {"VLLM_API_KEY": "sk-test-key"})  # pragma: allowlist secret
    def test_maas_endpoint_env_var_no_default_present(self):
        """MaaS endpoint with ${VLLM_API_KEY} set in env should pass."""
        config = {
            "llms": {
                "researcher_llm": {
                    "_type": "openai",
                    "model_name": "qwen3-14b",
                    "base_url": "https://litellm-prod.apps.maas.example.com/v1",
                    "api_key": "${VLLM_API_KEY}",
                },
            }
        }
        valid, missing = validate_llm_configs(config)
        assert valid is True
        assert missing == []


class TestExtractEnvVar:
    """Tests for _extract_env_var()."""

    def test_simple_env_var(self):
        name, default = _extract_env_var("${MY_KEY}")
        assert name == "MY_KEY"
        assert default is None

    def test_env_var_with_default(self):
        name, default = _extract_env_var("${VLLM_API_KEY:-no-key}")
        assert name == "VLLM_API_KEY"
        assert default == "no-key"

    def test_env_var_with_empty_default(self):
        name, default = _extract_env_var("${VLLM_API_KEY:-}")
        assert name == "VLLM_API_KEY"
        assert default == ""

    def test_env_var_with_url_default(self):
        name, default = _extract_env_var("${VLLM_BASE_URL:-http://localhost:8000}")
        assert name == "VLLM_BASE_URL"
        assert default == "http://localhost:8000"

    def test_literal_value(self):
        name, default = _extract_env_var("sk-literal-key")
        assert name is None
        assert default is None

    def test_empty_string(self):
        name, default = _extract_env_var("")
        assert name is None
        assert default is None

    def test_non_string(self):
        name, default = _extract_env_var(12345)
        assert name is None
        assert default is None


class TestValidateLlmEndpoints:
    """Tests for validate_llm_endpoints() with mocked HTTP responses."""

    @pytest.fixture
    def vllm_config(self):
        """A vLLM-style config with deep research agent."""
        return {
            "llms": {
                "intent_llm": {
                    "_type": "openai",
                    "model_name": "granite-3-2-8b-instruct",
                    "base_url": "http://localhost:9999/v1",
                    "api_key": "test-key",  # pragma: allowlist secret
                },
                "orchestrator_llm": {
                    "_type": "openai",
                    "model_name": "qwen3-14b",
                    "base_url": "http://localhost:9999/v1",
                    "api_key": "test-key",  # pragma: allowlist secret
                    "max_tokens": 128000,
                },
            },
            "functions": {
                "deep_research_agent": {
                    "_type": "deep_research_agent",
                    "orchestrator_llm": "orchestrator_llm",
                    "researcher_llm": "intent_llm",
                    "planner_llm": "orchestrator_llm",
                }
            },
        }

    @pytest.mark.asyncio
    async def test_unreachable_endpoint(self, vllm_config):
        """Unreachable endpoint produces a warning."""
        mock_probe = AsyncMock(return_value={"reachable": False, "models": {}, "error": "Connection refused"})
        with patch("aiq_agent.common.config_validation._probe_endpoint", mock_probe):
            warnings = await validate_llm_endpoints(vllm_config)
        assert len(warnings) == 1
        assert "unreachable" in warnings[0].lower()

    @pytest.mark.asyncio
    async def test_reachable_with_missing_model(self, vllm_config):
        """Reachable endpoint but model not found."""
        mock_probe = AsyncMock(return_value={"reachable": True, "models": {"some-other-model": {}}, "error": None})
        with patch("aiq_agent.common.config_validation._probe_endpoint", mock_probe):
            warnings = await validate_llm_endpoints(vllm_config)
        model_warnings = [w for w in warnings if "not found" in w]
        assert len(model_warnings) == 2
        missing_models = " ".join(model_warnings)
        assert "granite-3-2-8b-instruct" in missing_models
        assert "qwen3-14b" in missing_models

    @pytest.mark.asyncio
    async def test_reachable_with_small_context_window(self, vllm_config):
        """Model exists but has a small context window for deep research."""
        mock_probe = AsyncMock(
            return_value={
                "reachable": True,
                "models": {"granite-3-2-8b-instruct": {}, "qwen3-14b": {}},
                "error": None,
            }
        )
        mock_ctx = AsyncMock(return_value=16384)
        with (
            patch("aiq_agent.common.config_validation._probe_endpoint", mock_probe),
            patch("aiq_agent.common.config_validation._probe_context_window", mock_ctx),
        ):
            warnings = await validate_llm_endpoints(vllm_config)
        context_warnings = [w for w in warnings if "context window" in w.lower() or "max_tokens" in w.lower()]
        assert len(context_warnings) >= 1

    @pytest.mark.asyncio
    async def test_max_tokens_exceeds_context_window(self, vllm_config):
        """Config max_tokens > context window produces a specific error warning."""
        mock_probe = AsyncMock(
            return_value={
                "reachable": True,
                "models": {"granite-3-2-8b-instruct": {}, "qwen3-14b": {}},
                "error": None,
            }
        )
        # Context window is 40960 but config has max_tokens=128000
        mock_ctx = AsyncMock(return_value=40960)
        with (
            patch("aiq_agent.common.config_validation._probe_endpoint", mock_probe),
            patch("aiq_agent.common.config_validation._probe_context_window", mock_ctx),
        ):
            warnings = await validate_llm_endpoints(vllm_config)
        max_token_warnings = [w for w in warnings if "max_tokens=128,000" in w]
        assert len(max_token_warnings) == 1
        assert "400 Bad Request" in max_token_warnings[0]

    @pytest.mark.asyncio
    async def test_nim_endpoints_skipped(self):
        """NIM (integrate.api.nvidia.com) endpoints are skipped."""
        config = {
            "llms": {
                "nim_llm": {
                    "_type": "nim",
                    "model_name": "nvidia/nemotron",
                    "base_url": "https://integrate.api.nvidia.com/v1",
                }
            },
            "functions": {},
        }
        warnings = await validate_llm_endpoints(config)
        assert warnings == []

    @pytest.mark.asyncio
    async def test_all_checks_pass(self, vllm_config):
        """All checks pass when endpoint is reachable and models exist with large context."""
        mock_probe = AsyncMock(
            return_value={
                "reachable": True,
                "models": {"granite-3-2-8b-instruct": {}, "qwen3-14b": {}},
                "error": None,
            }
        )
        # Return None = context window is large enough (no error from probe)
        mock_ctx = AsyncMock(return_value=None)
        with (
            patch("aiq_agent.common.config_validation._probe_endpoint", mock_probe),
            patch("aiq_agent.common.config_validation._probe_context_window", mock_ctx),
        ):
            warnings = await validate_llm_endpoints(vllm_config)
        assert warnings == []

    @pytest.mark.asyncio
    async def test_empty_config(self):
        """Empty config produces no warnings."""
        warnings = await validate_llm_endpoints({})
        assert warnings == []

    @pytest.mark.asyncio
    async def test_accepts_model_key_from_preprocessed_config(self):
        """NAT preprocesses openai LLMs and renames `model_name` → `model`; both keys must validate."""
        config = {
            "llms": {
                "intent_llm": {
                    "_type": "openai",
                    "model": "granite-3-2-8b-instruct",
                    "base_url": "http://localhost:9999/v1",
                    "api_key": "test-key",  # pragma: allowlist secret
                },
            },
            "functions": {},
        }
        mock_probe = AsyncMock(
            return_value={
                "reachable": True,
                "models": {"granite-3-2-8b-instruct": {}},
                "error": None,
            }
        )
        with patch("aiq_agent.common.config_validation._probe_endpoint", mock_probe):
            warnings = await validate_llm_endpoints(config)
        assert not any("not found" in w for w in warnings), warnings

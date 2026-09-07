# SPDX-FileCopyrightText: Copyright (c) 2025-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Configuration validation utilities for checking required API keys and endpoint capabilities."""

import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

# Mapping of LLM _type to required API key environment variable names
# This can be extended as new providers are added
LLM_API_KEY_MAP = {
    "nim": ["NVIDIA_API_KEY"],
    "openai": ["OPENAI_API_KEY"],
    "anthropic": ["ANTHROPIC_API_KEY"],
    "google": ["GOOGLE_API_KEY"],
    "gemini": ["GOOGLE_API_KEY"],
    # Add more providers as needed
}


def _extract_env_var(value: str) -> tuple[str | None, str | None]:
    """Extract environment variable name and default from ${VAR_NAME:-default} syntax.

    Returns:
        Tuple of (env_var_name, default_value). Both may be None.
    """
    if isinstance(value, str):
        match = re.match(r"\$\{([^:}]+)(?::-(.*))?\}", value)
        if match:
            return match.group(1), match.group(2)
    return None, None


def _is_local_or_private_endpoint(llm_config: dict[str, Any]) -> bool:
    """Check if the LLM is configured to use a local or private endpoint (e.g. vLLM)."""
    base_url = llm_config.get("base_url", "")
    if isinstance(base_url, str):
        # Resolve env var references like ${VLLM_BASE_URL:-http://localhost:8000}
        default_match = re.match(r"\$\{[^:}]+(:-([^}]+))?\}", base_url)
        url_to_check = default_match.group(2) if default_match else base_url
        if url_to_check:
            return any(
                host in url_to_check for host in ("localhost", "127.0.0.1", "0.0.0.0", "10.", "192.168.", "172.")
            )
    return False


def _get_llm_api_key_requirements(llm_config: dict[str, Any]) -> list[str]:
    """
    Determine required API keys for an LLM configuration.

    Args:
        llm_config: LLM configuration dictionary with _type and optional api_key

    Returns:
        List of required API key environment variable names
    """
    llm_type = llm_config.get("_type", "").lower()
    required_keys = LLM_API_KEY_MAP.get(llm_type, [])

    # If api_key is explicitly set in config, check if it references an env var
    api_key_config = llm_config.get("api_key")
    if api_key_config:
        env_var, default_value = _extract_env_var(str(api_key_config))
        if env_var:
            # If there's a non-empty default value, the env var is optional
            if default_value:
                return []
            # No default — env var is required
            return [env_var]
        # If api_key is a literal value, no env var needed
        return []

    # Local/private endpoints (vLLM, TGI, etc.) typically don't require API keys
    if _is_local_or_private_endpoint(llm_config):
        return []

    return required_keys


def validate_llm_configs(config: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Validate that all required API keys are set for LLMs in the configuration.

    Args:
        config: Full workflow configuration dictionary

    Returns:
        Tuple of (is_valid, missing_keys) where:
        - is_valid: True if all required keys are present
        - missing_keys: List of missing API key names
    """
    llms_config = config.get("llms", {})
    if not llms_config:
        return True, []

    missing_keys = []
    checked_keys = set()  # Track which keys we've already checked

    for llm_name, llm_config in llms_config.items():
        if not isinstance(llm_config, dict):
            continue

        required_keys = _get_llm_api_key_requirements(llm_config)

        for key in required_keys:
            if key not in checked_keys:
                checked_keys.add(key)
                if not os.getenv(key):
                    missing_keys.append(key)

    return len(missing_keys) == 0, missing_keys


def get_llm_provider_info(llm_config: dict[str, Any]) -> str:
    """
    Get human-readable information about an LLM provider.

    Args:
        llm_config: LLM configuration dictionary

    Returns:
        Provider name and API key source information
    """
    llm_type = llm_config.get("_type", "unknown")
    api_key_config = llm_config.get("api_key")

    if api_key_config:
        env_var, default_value = _extract_env_var(str(api_key_config))
        if env_var:
            if default_value:
                return f"{llm_type} (uses {env_var}, default: {default_value})"
            return f"{llm_type} (requires {env_var})"
        return f"{llm_type} (api_key set in config)"

    required_keys = LLM_API_KEY_MAP.get(llm_type.lower(), [])
    if required_keys:
        return f"{llm_type} (requires {', '.join(required_keys)})"

    return f"{llm_type} (no API key required)"


# ---------------------------------------------------------------------------
# Minimum context window (tokens) recommended for deep research.
# The orchestrator and planner need large windows for multi-step planning,
# source aggregation, and report generation.
# ---------------------------------------------------------------------------
DEEP_RESEARCH_MIN_CONTEXT_TOKENS = 32_768


def _resolve_config_value(raw: str) -> str:
    """Resolve a config value that may contain ${VAR:-default} syntax.

    Handles values like '${VLLM_BASE_URL:-http://localhost:8000}/v1' where
    there is text after the env var substitution block.
    """
    if not isinstance(raw, str):
        return str(raw) if raw is not None else ""
    match = re.match(r"(\$\{[^}]+\})(.*)", raw)
    if match:
        env_part, suffix = match.group(1), match.group(2)
        env_var, default = _extract_env_var(env_part)
        if env_var:
            return os.getenv(env_var, default or "") + suffix
    return raw


def _resolve_base_url(llm_config: dict[str, Any]) -> str | None:
    """Resolve the base_url from an LLM config, expanding env vars."""
    raw = llm_config.get("base_url", "")
    if not isinstance(raw, str) or not raw:
        return None
    return _resolve_config_value(raw).rstrip("/")


def _resolve_api_key(llm_config: dict[str, Any]) -> str | None:
    """Resolve the api_key from an LLM config, expanding env vars."""
    raw = llm_config.get("api_key", "")
    if not isinstance(raw, str) or not raw:
        return None
    return _resolve_config_value(raw)


async def _probe_endpoint(base_url: str, api_key: str | None, timeout: float = 10.0) -> dict[str, Any]:
    """Probe an OpenAI-compatible endpoint via GET /v1/models.

    Returns:
        Dict with keys:
        - reachable (bool)
        - models (dict[str, dict]): model_id -> model info from the endpoint
        - error (str | None): error message if unreachable
    """

    import httpx

    url = f"{base_url}/v1/models" if not base_url.endswith("/v1") else f"{base_url}/models"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                models = {}
                for m in data.get("data", []):
                    model_id = m.get("id", "")
                    models[model_id] = m
                return {"reachable": True, "models": models, "error": None}
            return {
                "reachable": False,
                "models": {},
                "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
            }
    except httpx.TimeoutException:
        return {"reachable": False, "models": {}, "error": f"Connection timed out after {timeout}s"}
    except Exception as e:
        return {"reachable": False, "models": {}, "error": str(e)}


async def _probe_context_window(
    base_url: str, api_key: str | None, model_name: str, timeout: float = 10.0
) -> int | None:
    """Probe a model's context window by sending a minimal chat completion with an
    impossibly high max_tokens value and reading the error message.

    Returns the context window size in tokens, or None if it cannot be determined.
    """
    import httpx

    url = f"{base_url}/v1/chat/completions" if not base_url.endswith("/v1") else f"{base_url}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 999_999,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code == 200:
                # Model accepted 999k tokens — context window is huge, no concern
                return None
            body = resp.text
            # LiteLLM / vLLM typically return: "maximum context length is N tokens"
            import re as _re

            match = _re.search(r"maximum context length is (\d[\d,]*)", body)
            if match:
                return int(match.group(1).replace(",", ""))
    except Exception:
        pass
    return None


async def validate_llm_endpoints(config: dict[str, Any]) -> list[str]:
    """Probe configured LLM endpoints at startup and return a list of warning messages.

    Checks performed:
    1. Endpoint reachability (GET /v1/models)
    2. Configured model exists on the endpoint
    3. Context window is sufficient for deep research roles

    Args:
        config: Full workflow configuration dictionary (raw YAML, before env substitution)

    Returns:
        List of warning strings (empty if all checks pass).
    """
    llms_config = config.get("llms", {})
    functions_config = config.get("functions", {})
    if not llms_config:
        return []

    warnings: list[str] = []

    # Identify which LLM names are used for deep research roles
    deep_research_roles: set[str] = set()
    for fn_name, fn_config in functions_config.items():
        if not isinstance(fn_config, dict):
            continue
        fn_type = fn_config.get("_type", "")
        if fn_type == "deep_research_agent":
            # writer_llm and source_router_llm are checked too: the writer produces the
            # final report (the largest single generation in a deep-research run) and
            # both carry their own max_tokens, so both can exceed the context window
            # independently of the orchestrator.
            for role_key in (
                "orchestrator_llm",
                "researcher_llm",
                "planner_llm",
                "writer_llm",
                "source_router_llm",
            ):
                ref = fn_config.get(role_key)
                if ref:
                    deep_research_roles.add(ref)

    # Group LLMs by resolved base_url to avoid duplicate probes
    endpoint_llms: dict[str, list[tuple[str, dict]]] = {}  # base_url -> [(llm_name, llm_config), ...]
    for llm_name, llm_config in llms_config.items():
        if not isinstance(llm_config, dict):
            continue
        base_url = _resolve_base_url(llm_config)
        if not base_url:
            continue
        endpoint_llms.setdefault(base_url, []).append((llm_name, llm_config))

    # Skip NIM endpoints — they don't support /v1/models the same way
    nim_urls = {"https://integrate.api.nvidia.com"}

    for base_url, llm_entries in endpoint_llms.items():
        if any(base_url.startswith(nim) for nim in nim_urls):
            continue

        # Use the first LLM's api_key for the probe (they share an endpoint)
        api_key = _resolve_api_key(llm_entries[0][1])

        # 1. Reachability
        probe = await _probe_endpoint(base_url, api_key)
        if not probe["reachable"]:
            warnings.append(
                f"LLM endpoint unreachable: {base_url} — {probe['error']}. "
                f"Affected LLMs: {', '.join(name for name, _ in llm_entries)}"
            )
            continue

        available_models = probe["models"]

        for llm_name, llm_config in llm_entries:
            # NAT's preprocessed config (/tmp/nat_config*.yml) renames `model_name` to `model`
            # for openai-type LLMs, so accept either key.
            raw_model_name = llm_config.get("model_name") or llm_config.get("model") or ""
            model_name = _resolve_config_value(raw_model_name)

            # If env var resolution returned empty, try the default value directly
            if not model_name and raw_model_name:
                env_var, default = _extract_env_var(raw_model_name)
                if env_var and not model_name:
                    # Env var not set in this process — use default if available
                    model_name = default or ""
                    if not model_name:
                        logger.info(
                            "Endpoint validation: skipping model check for '%s' — "
                            "model name uses env var $%s which is not set in this process.",
                            llm_name,
                            env_var,
                        )
                        continue

            # 2. Model availability
            if available_models and model_name not in available_models:
                warnings.append(
                    f"Model '{model_name}' (configured as '{llm_name}') not found on {base_url}. "
                    f"Available models: {', '.join(sorted(available_models.keys()))}"
                )
                continue

            # 3. Context window check for deep research roles
            if llm_name in deep_research_roles:
                ctx_window = await _probe_context_window(base_url, api_key, model_name)
                if ctx_window is not None and ctx_window < DEEP_RESEARCH_MIN_CONTEXT_TOKENS:
                    warnings.append(
                        f"Deep research may be unreliable: '{llm_name}' uses model '{model_name}' "
                        f"with a {ctx_window:,}-token context window (minimum recommended: "
                        f"{DEEP_RESEARCH_MIN_CONTEXT_TOKENS:,}). Consider using a model with a "
                        f"larger context window for orchestrator/planner roles, or reduce max_tokens "
                        f"in the config."
                    )
                # Also check if configured max_tokens exceeds context window
                max_tokens_raw = llm_config.get("max_tokens")
                if max_tokens_raw is not None and ctx_window is not None:
                    max_tokens = int(_resolve_config_value(str(max_tokens_raw)))
                    if max_tokens > ctx_window:
                        warnings.append(
                            f"Config error: '{llm_name}' has max_tokens={max_tokens:,} but model "
                            f"'{model_name}' only supports {ctx_window:,} tokens. Requests will fail "
                            f"with 400 Bad Request. Reduce max_tokens or use VLLM_ORCHESTRATOR_MAX_TOKENS."
                        )

    return warnings

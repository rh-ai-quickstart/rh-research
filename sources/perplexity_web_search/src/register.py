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

import asyncio
import html
import logging
import os
import re
from collections.abc import AsyncGenerator
from typing import Any
from typing import Literal

import httpx
from pydantic import Field
from pydantic import SecretStr

from nat.builder.builder import Builder
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.function import FunctionBaseConfig

logger = logging.getLogger(__name__)

PERPLEXITY_SEARCH_URL = "https://api.perplexity.ai/search"

_missing_key_warned = False
_INVALID_XML_CHARACTERS = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\uD800-\uDFFF￾￿]")


def _xml_text(value: object) -> str:
    """Normalize provider text and remove characters forbidden by XML 1.0."""
    return _INVALID_XML_CHARACTERS.sub("", "" if value is None else str(value))


def _render_document(url: object, title: object, content: object) -> str:
    """Render provider-controlled fields inside the trusted document structure."""
    url_text = _xml_text(url)
    title_text = _xml_text(title)
    content_text = _xml_text(content)
    return (
        f'<Document href="{html.escape(url_text, quote=True)}">\n'
        f"<title>\n{html.escape(title_text, quote=True)}\n</title>\n"
        f"{html.escape(content_text, quote=True)}\n</Document>"
    )


def _build_client(timeout: float) -> httpx.AsyncClient:
    """Create the HTTP client. Tests replace this to inject a mock transport."""
    return httpx.AsyncClient(timeout=timeout)


class PerplexityWebSearchToolConfig(FunctionBaseConfig, name="perplexity_web_search"):
    """
    Tool that retrieves relevant contexts from web search (using the Perplexity Search API) for the given question.
    Requires a PERPLEXITY_API_KEY environment variable or api_key config.
    """

    api_key: SecretStr | None = Field(
        default=None,
        description="Perplexity API key. Falls back to the PERPLEXITY_API_KEY environment variable.",
    )
    max_results: int = Field(default=5, ge=1, le=20, description="Maximum number of search results to return (1-20)")
    max_content_length: int | None = Field(
        default=10000,
        description="Max characters per result snippet. Set to None to disable truncation.",
    )
    search_type: Literal["web", "fast"] = Field(
        default="web",
        description="Perplexity search type: 'web' (default) or 'fast' for lower latency and cost",
    )
    search_domain_filter: list[str] | None = Field(
        default=None,
        max_length=20,
        description=(
            "Optional list of up to 20 domains. Plain entries form an allowlist; entries prefixed with '-' form a "
            "denylist. Do not mix the two."
        ),
    )
    timeout: float = Field(default=30.0, gt=0, description="Request timeout in seconds")
    max_retries: int = Field(
        default=3,
        ge=1,
        description="Maximum attempts for timeouts, connection errors, and HTTP 5xx responses",
    )


def _resolve_api_key(tool_config: PerplexityWebSearchToolConfig) -> str | None:
    if tool_config.api_key is not None:
        value = tool_config.api_key.get_secret_value()
        if value:
            return value
    return os.environ.get("PERPLEXITY_API_KEY") or None


def _rate_limit_message(response: httpx.Response) -> str:
    message = "Error: Perplexity search rate limit reached (HTTP 429)."
    retry_after = response.headers.get("retry-after", "").strip()
    if retry_after.isdigit():
        message += f" Retry after {retry_after} seconds."
    else:
        message += " Try again later."
    return message


@register_function(config_type=PerplexityWebSearchToolConfig)
async def perplexity_web_search(
    tool_config: PerplexityWebSearchToolConfig,
    builder: Builder,
) -> AsyncGenerator[FunctionInfo, None]:
    """Register the Perplexity Search API web search tool with NAT.

    Calls `POST https://api.perplexity.ai/search` with httpx. If no API key is
    available (via `tool_config.api_key` or `PERPLEXITY_API_KEY`), a stub
    function is registered that returns an informative error instead of
    failing at import time.

    Args:
        tool_config: Configuration controlling result count, search type,
            domain filter, timeout, retries, and snippet truncation.
        builder: NAT builder handle (unused; accepted for interface parity).

    Yields:
        A `FunctionInfo` wrapping either the live search callable or the
        missing-key stub.
    """
    api_key = _resolve_api_key(tool_config)

    if not api_key:
        global _missing_key_warned
        if not _missing_key_warned:
            logger.warning(
                "PERPLEXITY_API_KEY not found. The Perplexity web search tool will be registered but will "
                "return an error when called. To enable: set PERPLEXITY_API_KEY in your environment, "
                ".env file, or specify api_key in your workflow config."
            )
            _missing_key_warned = True

        async def _perplexity_web_search_stub(question: str) -> str:
            """Web search tool (unavailable - missing PERPLEXITY_API_KEY)."""
            return (
                "Error: Perplexity web search is unavailable because PERPLEXITY_API_KEY is not set.\n"
                "To enable this tool:\n"
                "1. Get an API key from https://www.perplexity.ai/account/api\n"
                "2. Set the API key in your environment or in your .env file\n"
                "3. Restart the application"
            )

        yield FunctionInfo.from_fn(
            _perplexity_web_search_stub,
            description=_perplexity_web_search_stub.__doc__,
        )
        return

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    def _truncate_content(content: object) -> str:
        content = "" if content is None else str(content)
        if tool_config.max_content_length and len(content) > tool_config.max_content_length:
            return content[: tool_config.max_content_length - 3] + "..."
        return content

    def _build_payload(question: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "query": question,
            "max_results": tool_config.max_results,
            "search_type": tool_config.search_type,
        }
        if tool_config.search_domain_filter:
            payload["search_domain_filter"] = list(tool_config.search_domain_filter)
        return payload

    async with _build_client(tool_config.timeout) as client:

        async def _perplexity_web_search(question: str) -> str:
            """Retrieves relevant contexts from web search (using the Perplexity Search API) for the given question.

            Args:
                question (str): The question to be answered.

            Returns:
                str: The web search results containing relevant documents and their URLs.
            """
            payload = _build_payload(question)
            last_error = "Error: Perplexity search failed after all retries"

            for attempt in range(tool_config.max_retries):
                try:
                    response = await client.post(PERPLEXITY_SEARCH_URL, json=payload, headers=headers)
                except httpx.TimeoutException:
                    last_error = f"Error: Perplexity search timed out after {tool_config.timeout:g} seconds."
                except httpx.RequestError as e:
                    last_error = f"Error: Perplexity search request failed ({type(e).__name__})."
                else:
                    status = response.status_code
                    if status == 429:
                        return _rate_limit_message(response)
                    if status in (401, 403):
                        return (
                            f"Error: Perplexity search failed due to an invalid API key (HTTP {status}).\n"
                            "Please check your PERPLEXITY_API_KEY and ensure it is valid.\n"
                        )
                    if status >= 500:
                        last_error = f"Error: Perplexity search failed with a server error (HTTP {status})."
                    elif status >= 400:
                        return f"Error: Perplexity search failed (HTTP {status})."
                    else:
                        try:
                            data = response.json()
                        except ValueError:
                            return "Error: Perplexity search returned an invalid response."

                        results = data.get("results") if isinstance(data, dict) else None
                        if not results:
                            return "Search returned no results"

                        documents = [
                            _render_document(
                                item.get("url"),
                                item.get("title"),
                                _truncate_content(item.get("snippet")),
                            )
                            for item in results
                            if isinstance(item, dict)
                        ]
                        return "\n\n---\n\n".join(documents) if documents else "Search returned no results"

                if attempt < tool_config.max_retries - 1:
                    await asyncio.sleep(2**attempt)

            return last_error

        yield FunctionInfo.from_fn(
            _perplexity_web_search,
            description=_perplexity_web_search.__doc__,
        )

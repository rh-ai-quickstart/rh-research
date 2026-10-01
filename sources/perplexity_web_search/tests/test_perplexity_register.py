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

"""Tests for the perplexity_web_search NAT registration. All HTTP is mocked."""

import json
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock

import httpx
import pytest
from perplexity_web_search.register import PERPLEXITY_SEARCH_URL
from perplexity_web_search.register import PerplexityWebSearchToolConfig
from perplexity_web_search.register import perplexity_web_search
from pydantic import SecretStr
from pydantic import ValidationError

FAKE_KEY = "pplx-test-not-a-real-key"  # pragma: allowlist secret

ADVERSARIAL_URL = 'https://example.com/pa\x00th?q="quoted"&next=<unsafe>&close=</Document>'
ADVERSARIAL_TITLE = 'Research\x00 & "Roadmap" <2026> </title>'
ADVERSARIAL_CONTENT = 'Evidence\x00 & "claims" <external> </Document> </title>'
SANITIZED_URL = 'https://example.com/path?q="quoted"&next=<unsafe>&close=</Document>'
SANITIZED_TITLE = 'Research & "Roadmap" <2026> </title>'
SANITIZED_CONTENT = 'Evidence & "claims" <external> </Document> </title>'


def _parse_document(output: str) -> tuple[ET.Element, ET.Element]:
    assert output.count("<Document ") == 1
    assert output.count("</Document>") == 1
    root = ET.fromstring(output)
    title = root.find("title")
    assert title is not None
    return root, title


def _result(url: str, title: str, snippet: str) -> dict:
    return {"title": title, "url": url, "snippet": snippet, "date": "2026-01-01", "last_updated": "2026-01-02"}


class _FakeServer:
    """Records requests and replays a queue of responses or exceptions."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def body(self, index: int = 0) -> dict:
        return json.loads(self.requests[index].content)


@pytest.fixture
def fake_server(monkeypatch):
    server = _FakeServer()

    def _client(timeout):
        return httpx.AsyncClient(transport=httpx.MockTransport(server.handler), timeout=timeout)

    monkeypatch.setattr("perplexity_web_search.register._build_client", _client)
    return server


@pytest.fixture(autouse=True)
def _reset_warn_flag():
    import perplexity_web_search.register as reg

    reg._missing_key_warned = False
    yield
    reg._missing_key_warned = False


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)


@pytest.fixture
def no_sleep(monkeypatch):
    async def _no_sleep(_):
        return None

    monkeypatch.setattr("perplexity_web_search.register.asyncio.sleep", _no_sleep)


async def _search(config: PerplexityWebSearchToolConfig, question: str = "query") -> str:
    async with perplexity_web_search(config, MagicMock()) as info:
        return await info.single_fn(question)


class TestPerplexityWebSearchToolConfig:
    def test_defaults(self):
        config = PerplexityWebSearchToolConfig()
        assert config.api_key is None
        assert config.max_results == 5
        assert config.max_content_length == 10000
        assert config.search_type == "web"
        assert config.search_domain_filter is None
        assert config.timeout == 30.0
        assert config.max_retries == 3

    @pytest.mark.parametrize("value", [0, 21])
    def test_max_results_bounds(self, value):
        with pytest.raises(ValidationError):
            PerplexityWebSearchToolConfig(max_results=value)

    def test_rejects_unknown_search_type(self):
        with pytest.raises(ValidationError):
            PerplexityWebSearchToolConfig(search_type="deep")

    def test_inherits_from_function_base_config(self):
        from nat.data_models.function import FunctionBaseConfig

        assert issubclass(PerplexityWebSearchToolConfig, FunctionBaseConfig)


class TestPerplexityWebSearchStub:
    async def test_stub_when_no_api_key(self, fake_server):
        out = await _search(PerplexityWebSearchToolConfig(), "anything")

        assert "PERPLEXITY_API_KEY" in out
        assert "unavailable" in out.lower()
        assert fake_server.requests == []


class TestPerplexityWebSearchLive:
    async def test_request_built_from_config(self, fake_server):
        fake_server.responses.append(httpx.Response(200, json={"results": [_result("https://a.example", "A", "a")]}))
        config = PerplexityWebSearchToolConfig(
            api_key=SecretStr(FAKE_KEY),
            max_results=7,
            search_type="fast",
            search_domain_filter=["redhat.com", "-reddit.com"],
        )

        await _search(config, "what is vllm")

        request = fake_server.requests[0]
        assert request.method == "POST"
        assert str(request.url) == PERPLEXITY_SEARCH_URL
        assert request.headers["authorization"] == f"Bearer {FAKE_KEY}"
        assert fake_server.body() == {
            "query": "what is vllm",
            "max_results": 7,
            "search_type": "fast",
            "search_domain_filter": ["redhat.com", "-reddit.com"],
        }

    async def test_env_key_used_and_domain_filter_omitted(self, fake_server, monkeypatch):
        monkeypatch.setenv("PERPLEXITY_API_KEY", FAKE_KEY)
        fake_server.responses.append(httpx.Response(200, json={"results": [_result("https://a.example", "A", "a")]}))

        await _search(PerplexityWebSearchToolConfig())

        assert fake_server.requests[0].headers["authorization"] == f"Bearer {FAKE_KEY}"
        assert fake_server.body() == {"query": "query", "max_results": 5, "search_type": "web"}

    async def test_results_rendered_as_documents(self, fake_server, monkeypatch):
        monkeypatch.setenv("PERPLEXITY_API_KEY", FAKE_KEY)
        fake_server.responses.append(
            httpx.Response(
                200,
                json={
                    "id": "req-1",
                    "results": [
                        _result("https://a.example", "Title A", "Body A"),
                        _result("https://b.example", "Title B", "Body B"),
                    ],
                },
            )
        )

        out = await _search(PerplexityWebSearchToolConfig())

        blocks = out.split("\n\n---\n\n")
        assert len(blocks) == 2
        doc_a, title_a = _parse_document(blocks[0])
        assert doc_a.attrib["href"] == "https://a.example"
        assert (title_a.text or "").strip("\n") == "Title A"
        assert (title_a.tail or "").strip("\n") == "Body A"
        assert '<Document href="https://b.example">' in blocks[1]

    async def test_structurally_escapes_provider_fields(self, fake_server, monkeypatch):
        monkeypatch.setenv("PERPLEXITY_API_KEY", FAKE_KEY)
        fake_server.responses.append(
            httpx.Response(200, json={"results": [_result(ADVERSARIAL_URL, ADVERSARIAL_TITLE, ADVERSARIAL_CONTENT)]})
        )

        out = await _search(PerplexityWebSearchToolConfig())

        document, title = _parse_document(out)
        assert document.attrib["href"] == SANITIZED_URL
        assert (title.text or "").strip("\n") == SANITIZED_TITLE
        assert (title.tail or "").strip("\n") == SANITIZED_CONTENT

    async def test_truncates_snippet(self, fake_server, monkeypatch):
        monkeypatch.setenv("PERPLEXITY_API_KEY", FAKE_KEY)
        fake_server.responses.append(httpx.Response(200, json={"results": [_result("u", "t", "abcdefghijklmnop")]}))

        out = await _search(PerplexityWebSearchToolConfig(max_content_length=8))

        _, title = _parse_document(out)
        assert (title.tail or "").strip("\n") == "abcde..."

    async def test_empty_results(self, fake_server, monkeypatch):
        monkeypatch.setenv("PERPLEXITY_API_KEY", FAKE_KEY)
        fake_server.responses.append(httpx.Response(200, json={"results": []}))

        out = await _search(PerplexityWebSearchToolConfig())

        assert "no results" in out.lower()

    async def test_invalid_json(self, fake_server, monkeypatch):
        monkeypatch.setenv("PERPLEXITY_API_KEY", FAKE_KEY)
        fake_server.responses.append(httpx.Response(200, content=b"not json"))

        out = await _search(PerplexityWebSearchToolConfig())

        assert out.startswith("Error:")


class TestPerplexityWebSearchErrors:
    async def test_429_returns_rate_limit_message_without_retry(self, fake_server, monkeypatch, no_sleep):
        monkeypatch.setenv("PERPLEXITY_API_KEY", FAKE_KEY)
        fake_server.responses.append(httpx.Response(429, headers={"retry-after": "12"}))

        out = await _search(PerplexityWebSearchToolConfig())

        assert "rate limit" in out.lower()
        assert "429" in out
        assert "12 seconds" in out
        assert len(fake_server.requests) == 1

    async def test_401_returns_key_message_without_secret(self, fake_server, monkeypatch, no_sleep):
        monkeypatch.setenv("PERPLEXITY_API_KEY", FAKE_KEY)
        fake_server.responses.append(httpx.Response(401, json={"error": "unauthorized"}))

        out = await _search(PerplexityWebSearchToolConfig())

        assert "401" in out
        assert "PERPLEXITY_API_KEY" in out
        assert FAKE_KEY not in out
        assert len(fake_server.requests) == 1

    async def test_other_4xx_not_retried(self, fake_server, monkeypatch, no_sleep):
        monkeypatch.setenv("PERPLEXITY_API_KEY", FAKE_KEY)
        fake_server.responses.append(httpx.Response(400))

        out = await _search(PerplexityWebSearchToolConfig())

        assert out == "Error: Perplexity search failed (HTTP 400)."
        assert len(fake_server.requests) == 1

    async def test_5xx_retried_then_succeeds(self, fake_server, monkeypatch, no_sleep):
        monkeypatch.setenv("PERPLEXITY_API_KEY", FAKE_KEY)
        fake_server.responses.extend(
            [httpx.Response(503), httpx.Response(200, json={"results": [_result("https://a.example", "A", "ok")]})]
        )

        out = await _search(PerplexityWebSearchToolConfig(max_retries=3))

        assert "ok" in out
        assert len(fake_server.requests) == 2

    async def test_timeout_returns_error_after_retries(self, fake_server, monkeypatch, no_sleep):
        monkeypatch.setenv("PERPLEXITY_API_KEY", FAKE_KEY)
        fake_server.responses.extend([httpx.ReadTimeout("slow"), httpx.ReadTimeout("slow")])

        out = await _search(PerplexityWebSearchToolConfig(max_retries=2, timeout=5))

        assert out == "Error: Perplexity search timed out after 5 seconds."
        assert len(fake_server.requests) == 2

    async def test_connection_error_returns_error(self, fake_server, monkeypatch, no_sleep):
        monkeypatch.setenv("PERPLEXITY_API_KEY", FAKE_KEY)
        fake_server.responses.append(httpx.ConnectError("refused"))

        out = await _search(PerplexityWebSearchToolConfig(max_retries=1))

        assert out == "Error: Perplexity search request failed (ConnectError)."

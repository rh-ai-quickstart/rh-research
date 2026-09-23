# SPDX-FileCopyrightText: Copyright (c) 2025-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the deep researcher's one-shot citation repair."""

from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage

from aiq_agent.agents.deep_researcher.agent import DeepResearcherAgent
from aiq_agent.agents.deep_researcher.register import DeepResearchAgentConfig
from aiq_agent.common import LLMProvider
from aiq_agent.common.citation_verification import CitationIntegrityError
from aiq_agent.common.citation_verification import SourceEntry
from aiq_agent.common.citation_verification import format_citation_repair_sources

SOURCES = [SourceEntry(url="https://example.test/a", title="A"), SourceEntry(citation_key="Doc B", title="B")]


def _agent(**kwargs) -> DeepResearcherAgent:
    provider = LLMProvider()
    provider.set_default(MagicMock())
    return DeepResearcherAgent(llm_provider=provider, tools=[], **kwargs)


def test_repair_sources_render_as_numbered_lines():
    assert format_citation_repair_sources(SOURCES) == "- [1] Source 1 - https://example.test/a\n- [2] Doc B"


def test_repair_sources_ignore_entries_without_url_or_key():
    assert format_citation_repair_sources([SourceEntry(title="no locator")]) == ""


@pytest.mark.asyncio
async def test_repair_returns_the_rewritten_report(monkeypatch):
    agent = _agent()
    seen = {}

    async def fake_invoke(model, messages, callbacks=None, config=None):
        seen["prompt"] = messages[-1].content
        return AIMessage(content="# Report\n\nClaim [1].\n\n## Sources\n\n- [1] Source 1 - https://example.test/a")

    monkeypatch.setattr("aiq_agent.agents.deep_researcher.agent.ainvoke_with_relay", fake_invoke)

    repaired = await agent._repair_missing_citations("# Report\n\nClaim with no citation.", SOURCES)

    assert "[1]" in repaired and "## Sources" in repaired
    assert "https://example.test/a" in seen["prompt"]
    assert "Claim with no citation." in seen["prompt"]


@pytest.mark.asyncio
async def test_repair_without_usable_sources_fails_closed():
    with pytest.raises(CitationIntegrityError):
        await _agent()._repair_missing_citations("# Report", [SourceEntry(title="no locator")])


@pytest.mark.asyncio
async def test_repair_rejects_an_empty_rewrite(monkeypatch):
    async def fake_invoke(model, messages, callbacks=None, config=None):
        return AIMessage(content="   ")

    monkeypatch.setattr("aiq_agent.agents.deep_researcher.agent.ainvoke_with_relay", fake_invoke)

    with pytest.raises(CitationIntegrityError):
        await _agent()._repair_missing_citations("# Report", SOURCES)


@pytest.mark.asyncio
async def test_repair_honours_its_timeout(monkeypatch):
    import asyncio

    async def slow_invoke(model, messages, callbacks=None, config=None):
        await asyncio.sleep(5)

    monkeypatch.setattr("aiq_agent.agents.deep_researcher.agent.ainvoke_with_relay", slow_invoke)

    with pytest.raises(asyncio.TimeoutError):
        await _agent(citation_repair_timeout=0.05)._repair_missing_citations("# Report", SOURCES)


def test_citation_repair_timeout_is_configurable():
    assert DeepResearchAgentConfig.model_fields["citation_repair_timeout"].default == 180.0
    config = DeepResearchAgentConfig(orchestrator_llm="llm", citation_repair_timeout=600)
    assert config.citation_repair_timeout == 600
    assert _agent(citation_repair_timeout=600).citation_repair_timeout == 600

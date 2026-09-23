# SPDX-FileCopyrightText: Copyright (c) 2025-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for relaxing forced tool choice on OpenAI-compatible models."""

import pytest
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from aiq_agent.agents.deep_researcher.register import DeepResearchAgentConfig
from aiq_agent.agents.deep_researcher.tool_choice import relax_forced_tool_choice


@tool
def lookup(query: str) -> str:
    """Look something up."""
    return query


def _model() -> ChatOpenAI:
    return ChatOpenAI(model="served-model", api_key="not-used", base_url="http://127.0.0.1:1/v1")


def _sent_tool_choice(runnable) -> object:
    return runnable.kwargs.get("tool_choice")


@pytest.mark.parametrize("forced", ["any", "required", True])
def test_forced_tool_choice_is_sent_as_auto(forced):
    relaxed = relax_forced_tool_choice(_model())

    assert _sent_tool_choice(relaxed.bind_tools([lookup], tool_choice=forced)) == "auto"


def test_named_and_default_tool_choice_pass_through():
    relaxed = relax_forced_tool_choice(_model())

    named = _sent_tool_choice(relaxed.bind_tools([lookup], tool_choice="lookup"))
    assert named == {"type": "function", "function": {"name": "lookup"}}
    assert _sent_tool_choice(relaxed.bind_tools([lookup])) is None


def test_original_model_keeps_forced_tool_choice():
    model = _model()
    relax_forced_tool_choice(model)

    assert _sent_tool_choice(model.bind_tools([lookup], tool_choice="any")) == "required"


def test_relaxation_keeps_instance_level_patches():
    """NAT patches public methods on the instance (retries); the relaxed copy must still call them."""
    model = _model()
    calls = []
    original = model.bind_tools

    def patched_bind_tools(tools, **kwargs):
        calls.append(kwargs.get("tool_choice"))
        return original(tools, **kwargs)

    object.__setattr__(model, "bind_tools", patched_bind_tools)

    relax_forced_tool_choice(model).bind_tools([lookup], tool_choice="any")

    assert calls == ["auto"]


def test_force_tool_choice_defaults_to_upstream_behaviour():
    assert DeepResearchAgentConfig.model_fields["force_tool_choice"].default is True


def test_relaxed_provider_covers_every_role_and_keeps_the_original():
    from aiq_agent.agents.deep_researcher.tool_choice import relax_provider_tool_choice
    from aiq_agent.common import LLMProvider
    from aiq_agent.common import LLMRole

    shared, writer = _model(), _model()
    provider = LLMProvider()
    provider.set_default(shared)
    provider.configure(LLMRole.REPORT_WRITER, writer)

    relaxed = relax_provider_tool_choice(provider)

    for role in (LLMRole.ORCHESTRATOR, LLMRole.PLANNER, LLMRole.RESEARCHER, LLMRole.REPORT_WRITER):
        assert _sent_tool_choice(relaxed.get(role).bind_tools([lookup], tool_choice="any")) == "auto"
    assert relaxed.get(LLMRole.PLANNER) is relaxed.get(LLMRole.RESEARCHER)
    assert _sent_tool_choice(provider.get(LLMRole.PLANNER).bind_tools([lookup], tool_choice="any")) == "required"


@pytest.mark.parametrize(("force_tool_choice", "expected"), [(True, "required"), (False, "auto")])
def test_deep_researcher_agent_applies_force_tool_choice(force_tool_choice, expected):
    from aiq_agent.agents.deep_researcher.agent import DeepResearcherAgent
    from aiq_agent.common import LLMProvider
    from aiq_agent.common import LLMRole

    provider = LLMProvider()
    provider.set_default(_model())

    agent = DeepResearcherAgent(llm_provider=provider, tools=[lookup], force_tool_choice=force_tool_choice)

    planner = agent.llm_provider.get(LLMRole.PLANNER)
    assert _sent_tool_choice(planner.bind_tools([lookup], tool_choice="any")) == expected

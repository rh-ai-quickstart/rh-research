# SPDX-FileCopyrightText: Copyright (c) 2025-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Optional relaxation of forced tool choice for OpenAI-compatible servers.

LangChain's structured-output ``ToolStrategy`` binds tools with ``tool_choice="any"``,
which OpenAI-compatible clients send as ``"required"``. vLLM enforces that with a
grammar and, while the model writes the structured tool call, sends no stream chunks
(0.18) or can run to ``max_tokens`` (0.27). Relaxing to ``"auto"`` keeps the stream
alive; ``StructuredResponseTextFallbackMiddleware`` already accepts a text answer.
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel

from aiq_agent.common import LLMProvider
from aiq_agent.common import LLMRole

FORCED_TOOL_CHOICES = ("any", "required", True)


def relax_forced_tool_choice(model: BaseChatModel) -> BaseChatModel:
    """Return a copy of ``model`` whose ``bind_tools`` sends ``"auto"`` instead of a forced choice.

    A named tool choice or ``"auto"``/``None`` passes through unchanged. The original
    model is not modified, so other agents sharing it keep upstream behaviour.
    """
    original_bind_tools = model.bind_tools

    def bind_tools(tools: Any, *, tool_choice: Any = None, **kwargs: Any) -> Any:
        if tool_choice in FORCED_TOOL_CHOICES:
            tool_choice = "auto"
        return original_bind_tools(tools, tool_choice=tool_choice, **kwargs)

    relaxed = model.model_copy()
    object.__setattr__(relaxed, "bind_tools", bind_tools)
    return relaxed


def relax_provider_tool_choice(provider: LLMProvider) -> LLMProvider:
    """Return a new provider whose models for every role send ``"auto"`` instead of a forced choice."""
    relaxed_provider = LLMProvider()
    relaxed_by_model: dict[int, BaseChatModel] = {}
    for role in LLMRole:
        try:
            model = provider.get(role)
        except ValueError:
            continue
        if id(model) not in relaxed_by_model:
            relaxed_by_model[id(model)] = relax_forced_tool_choice(model)
        relaxed_provider.configure(role, relaxed_by_model[id(model)])
    return relaxed_provider

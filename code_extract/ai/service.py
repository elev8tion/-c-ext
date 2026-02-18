"""Core AI service — async DeepSeek client for context-aware code chat."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from . import AIConfig

logger = logging.getLogger(__name__)

# Limits to keep prompts within context window
MAX_CODE_BLOCKS = 10
MAX_CODE_CHARS = 1000


class DeepSeekService:
    """Async client for the DeepSeek API (OpenAI-compatible)."""

    def __init__(self, config: AIConfig | None = None):
        self.config = config or AIConfig()
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
        )

    async def chat_with_code(
        self,
        query: str,
        code_context: list[dict[str, Any]],
        analysis_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a chat request with code and analysis context.

        Args:
            query: User question about the code.
            code_context: List of code block dicts with name/type/language/code.
            analysis_context: Optional analysis data (health, deps, dead_code).

        Returns:
            OpenAI-compatible response dict.
        """
        messages = self._build_messages(query, code_context, analysis_context)

        response = await self.client.post(
            f"{self.config.base_url}/chat/completions",
            json={
                "model": self.config.model.value,
                "messages": messages,
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
                "stream": False,
            },
        )
        response.raise_for_status()
        return response.json()

    def _build_messages(
        self,
        query: str,
        code_context: list[dict[str, Any]],
        analysis_context: dict[str, Any] | None,
    ) -> list[dict[str, str]]:
        """Build context-aware message list for the API."""
        system_prompt = self._build_system_prompt(code_context, analysis_context)
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ]

    def _build_system_prompt(
        self,
        code_context: list[dict[str, Any]],
        analysis_context: dict[str, Any] | None,
    ) -> str:
        """Build system prompt with code blocks and analysis summary."""
        parts = [
            "You are a code analysis assistant integrated with code-extract.",
            "You have access to the following code context and analysis data.",
            "Provide specific, actionable insights about the code.",
            "Reference actual code when possible.",
            "Consider language-specific best practices.",
        ]

        if code_context:
            parts.append("\n## Code Context:")
            for i, block in enumerate(code_context[:MAX_CODE_BLOCKS]):
                name = block.get("name", "Unknown")
                btype = block.get("type", "Unknown")
                lang = block.get("language", "text")
                fpath = block.get("file", "Unknown")
                code = block.get("code", "")[:MAX_CODE_CHARS]
                parts.append(
                    f"\n### {i + 1}. {name}\n"
                    f"Type: {btype} | Language: {lang} | File: {fpath}\n"
                    f"```{lang}\n{code}\n```"
                )

        if analysis_context:
            parts.append("\n## Analysis Context:")
            if "health" in analysis_context:
                health = analysis_context["health"]
                score = health.get("score", "N/A")
                parts.append(f"Health Score: {score}/100")
            if "dependencies" in analysis_context:
                parts.append(
                    f"Dependencies: {len(analysis_context['dependencies'])} items"
                )
            if "dead_code" in analysis_context:
                parts.append(
                    f"Potential Dead Code: {len(analysis_context['dead_code'])} items"
                )

        return "\n".join(parts)

    async def close(self):
        """Clean up the HTTP client."""
        await self.client.aclose()

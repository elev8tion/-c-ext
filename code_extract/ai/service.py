"""Core AI service — async DeepSeek client for context-aware code chat."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from . import AIConfig

logger = logging.getLogger(__name__)

# Limits to keep prompts within context window
MAX_CODE_BLOCKS = 10
MAX_CODE_CHARS = 1000
MAX_TOOL_ITERATIONS = 8


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
                score = getattr(health, "score", None) or (health.get("score") if isinstance(health, dict) else "N/A")
                parts.append(f"Health Score: {score}/100")
            if "dependencies" in analysis_context:
                dep = analysis_context["dependencies"]
                # DependencyGraph has .nodes dict and .edges list
                n_nodes = len(getattr(dep, "nodes", {})) if hasattr(dep, "nodes") else (len(dep) if isinstance(dep, (list, dict)) else 0)
                n_edges = len(getattr(dep, "edges", [])) if hasattr(dep, "edges") else 0
                parts.append(f"Dependencies: {n_nodes} nodes, {n_edges} edges")
            if "dead_code" in analysis_context:
                dc = analysis_context["dead_code"]
                count = len(dc) if isinstance(dc, (list, dict)) else 0
                parts.append(f"Potential Dead Code: {count} items")

        return "\n".join(parts)

    # ── Agentic copilot ───────────────────────────────────────────

    async def agent_chat(
        self,
        query: str,
        scan_id: str,
        history: list[dict[str, str]],
        code_context: list[dict[str, Any]] | None = None,
        analysis_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run an agentic chat with tool-calling loop.

        Args:
            query: User's natural language request.
            scan_id: Active scan session ID.
            history: Last N conversation turns as {role, content} dicts.
            code_context: Code blocks from the scan (same as chat endpoint).
            analysis_context: Analysis data (health, deps, dead_code).

        Returns:
            {answer, actions, model, usage, history_update}
        """
        from .tools import TOOL_DEFINITIONS, execute_tool

        system_prompt = self._build_agent_system_prompt(
            code_context=code_context,
            analysis_context=analysis_context,
        )
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": query})

        all_actions: list[dict] = []
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        model_name = self.config.model.value

        for iteration in range(MAX_TOOL_ITERATIONS):
            logger.info("[agent] iteration=%d, model=%s, messages=%d",
                        iteration, self.config.model.value, len(messages))

            # On the last iteration, omit tools to force a text summary
            # instead of another tool call that would be lost.
            is_last = iteration == MAX_TOOL_ITERATIONS - 1
            request_body: dict[str, Any] = {
                "model": self.config.model.value,
                "messages": messages,
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
                "stream": False,
            }
            if not is_last:
                request_body["tools"] = TOOL_DEFINITIONS
                request_body["tool_choice"] = "auto"

            response = await self.client.post(
                f"{self.config.base_url}/chat/completions",
                json=request_body,
            )
            response.raise_for_status()
            data = response.json()

            # Accumulate usage
            usage = data.get("usage", {})
            for k in total_usage:
                total_usage[k] += usage.get(k, 0)

            model_name = data.get("model", model_name)
            choice = data.get("choices", [{}])[0]
            message = choice.get("message", {})
            finish_reason = choice.get("finish_reason", "stop")

            logger.info("[agent] finish_reason=%s, has_tool_calls=%s, content_len=%d",
                        finish_reason, bool(message.get("tool_calls")),
                        len(message.get("content") or ""))

            # No tool calls — we have the final answer
            if finish_reason != "tool_calls" and not message.get("tool_calls"):
                answer = message.get("content", "")
                logger.info("[agent] final answer, %d chars, %d actions",
                            len(answer), len(all_actions))
                history_update = [
                    {"role": "user", "content": query},
                    {"role": "assistant", "content": answer},
                ]
                return {
                    "answer": answer,
                    "actions": all_actions,
                    "model": model_name,
                    "usage": total_usage,
                    "history_update": history_update,
                }

            # Process tool calls
            # Add the assistant message with tool_calls to conversation
            messages.append(message)

            for tool_call in message.get("tool_calls", []):
                fn = tool_call.get("function", {})
                tool_name = fn.get("name", "")
                try:
                    arguments = json.loads(fn.get("arguments", "{}"))
                except (json.JSONDecodeError, TypeError):
                    arguments = {}

                tool_id = tool_call.get("id", "")
                logger.info("[agent] tool_call: %s(%s) id=%s",
                            tool_name, json.dumps(arguments)[:200], tool_id)
                result_text, actions = execute_tool(tool_name, scan_id, arguments)
                logger.info("[agent] tool_result: %d chars, %d actions",
                            len(result_text), len(actions))
                all_actions.extend(actions)

                # Add tool result to conversation
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": result_text,
                })

        # Safety: max iterations reached — return whatever we have
        answer = "I completed the available actions. Let me know if you need anything else."
        return {
            "answer": answer,
            "actions": all_actions,
            "model": model_name,
            "usage": total_usage,
            "history_update": [
                {"role": "user", "content": query},
                {"role": "assistant", "content": answer},
            ],
        }

    def _build_agent_system_prompt(
        self,
        code_context: list[dict[str, Any]] | None = None,
        analysis_context: dict[str, Any] | None = None,
    ) -> str:
        """System prompt for the agentic copilot with code and analysis context."""
        parts = [
            "You are an AI copilot integrated with code-extract, a code analysis and extraction tool.",
            "You can answer questions about the scanned codebase AND take actions in the UI.",
            "You have access to the code context and analysis data below.",
            "Provide specific, actionable insights about the code.",
            "Reference actual code when possible.",
            "",
            "## Available capabilities:",
            "- **Data queries**: Search items, get source code, health scores, architecture info, "
            "dead code, dependencies, docs summaries, tour steps, and component catalog.",
            "- **UI navigation**: Switch between tabs (scan, catalog, architecture, health, docs, "
            "deadcode, tour, clone, boilerplate, migration, remix).",
            "- **Boilerplate**: Detect boilerplate patterns, get template code with variables, "
            "and generate new code from templates by filling in variables.",
            "- **Workflows**: Clone items, add to remix board, build remix projects, "
            "run comparisons, smart-extract code with dependencies, apply migration patterns.",
            "",
            "## Guidelines:",
            "- Use data tools to gather information before answering questions.",
            "- Use UI action tools when the user wants to navigate or perform operations.",
            "- For multi-step workflows (like cloning), use the appropriate workflow tool.",
            "- Be concise but helpful in your responses.",
            "- If an item name is ambiguous, search first to find the exact match.",
            "- When reporting data, summarize the key findings clearly.",
        ]

        # Embed code context (same format as chat system prompt)
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

        # Embed analysis context (same format as chat system prompt)
        if analysis_context:
            parts.append("\n## Analysis Context:")
            if "health" in analysis_context:
                health = analysis_context["health"]
                score = getattr(health, "score", None) or (health.get("score") if isinstance(health, dict) else "N/A")
                parts.append(f"Health Score: {score}/100")
            if "dependencies" in analysis_context:
                dep = analysis_context["dependencies"]
                n_nodes = len(getattr(dep, "nodes", {})) if hasattr(dep, "nodes") else (len(dep) if isinstance(dep, (list, dict)) else 0)
                n_edges = len(getattr(dep, "edges", [])) if hasattr(dep, "edges") else 0
                parts.append(f"Dependencies: {n_nodes} nodes, {n_edges} edges")
            if "dead_code" in analysis_context:
                dc = analysis_context["dead_code"]
                count = len(dc) if isinstance(dc, (list, dict)) else 0
                parts.append(f"Potential Dead Code: {count} items")

        return "\n".join(parts)

    async def close(self):
        """Clean up the HTTP client."""
        await self.client.aclose()

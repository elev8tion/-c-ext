"""Core AI service — async DeepSeek client for context-aware code chat."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from . import AIConfig, AIModel
from .token_utils import estimate_messages_tokens, has_tiktoken

logger = logging.getLogger(__name__)

# Limits to keep prompts within context window
MAX_CODE_BLOCKS = 10
MAX_CODE_CHARS = 2500
MAX_TOOL_ITERATIONS = 6


class DeepSeekService:
    """Async client for the DeepSeek API (OpenAI-compatible)."""

    def __init__(
        self,
        config: AIConfig | None = None,
        tool_system=None,
        intelligence=None,
    ):
        self.config = config or AIConfig()
        self._tool_system = tool_system
        self._intelligence = intelligence
        self.client = httpx.AsyncClient(
            timeout=60.0,
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
                "temperature": self.config.get_optimal_temperature(),
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
        model_value = self.config.model.value
        # Reasoner cannot use system messages — fold into user message
        if self.config.model == AIModel.DEEPSEEK_REASONER:
            system_prompt = self._build_system_prompt(code_context, analysis_context, model=model_value)
            return [
                {"role": "user", "content": f"{system_prompt}\n\n---\n\n{query}"},
            ]
        system_prompt = self._build_system_prompt(code_context, analysis_context, model=model_value)
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ]

    @staticmethod
    def _format_analysis_context(analysis_context: dict[str, Any]) -> str:
        """Format analysis data into rich context text for system prompts."""
        parts: list[str] = []

        # Health details
        if "health" in analysis_context:
            health = analysis_context["health"]
            if isinstance(health, dict):
                score = health.get("score", "N/A")
                parts.append(f"### Health — Score: {score}/100")
                # Top long functions
                long_fns = health.get("long_functions", [])[:5]
                if long_fns:
                    lines = [f"- `{f.get('name', '?')}` — {f.get('line_count', f.get('lines', '?'))} lines"
                             for f in long_fns if isinstance(f, dict)]
                    if lines:
                        parts.append("**Longest functions:**\n" + "\n".join(lines))
                # Top duplications
                dupes = health.get("duplications", health.get("duplication", []))
                if isinstance(dupes, list):
                    for d in dupes[:3]:
                        if isinstance(d, dict):
                            names = d.get("names", d.get("items", []))
                            sim = d.get("similarity", "?")
                            parts.append(f"- Duplication: {', '.join(str(n) for n in names[:3])} ({sim}% similar)")
                # High coupling
                coupling = health.get("high_coupling", [])[:3]
                if coupling:
                    lines = [f"- `{c.get('name', '?')}` — {c.get('coupling', c.get('score', '?'))} coupling score"
                             for c in coupling if isinstance(c, dict)]
                    if lines:
                        parts.append("**High coupling:**\n" + "\n".join(lines))
            else:
                score = getattr(health, "score", "N/A")
                parts.append(f"### Health — Score: {score}/100")

        # Dependencies
        if "dependencies" in analysis_context:
            dep = analysis_context["dependencies"]
            nodes = getattr(dep, "nodes", {}) if hasattr(dep, "nodes") else (dep if isinstance(dep, dict) else {})
            edges = getattr(dep, "edges", []) if hasattr(dep, "edges") else []
            n_nodes = len(nodes)
            n_edges = len(edges)
            parts.append(f"### Dependencies — {n_nodes} nodes, {n_edges} edges")
            # Top most-depended-on items
            if isinstance(nodes, dict):
                dep_counts: list[tuple[str, int]] = []
                for name, node in nodes.items():
                    if isinstance(node, dict):
                        dep_counts.append((name, node.get("dependents", 0)))
                    elif hasattr(node, "dependents"):
                        dep_counts.append((name, len(getattr(node, "dependents", []))))
                dep_counts.sort(key=lambda x: x[1], reverse=True)
                top = dep_counts[:5]
                if top and any(c > 0 for _, c in top):
                    lines = [f"- `{n}` — {c} dependents" for n, c in top if c > 0]
                    if lines:
                        parts.append("**Most depended-on:**\n" + "\n".join(lines))

        # Dead code
        if "dead_code" in analysis_context:
            dc = analysis_context["dead_code"]
            items = dc if isinstance(dc, list) else (list(dc.values()) if isinstance(dc, dict) else [])
            parts.append(f"### Dead Code — {len(items)} items detected")
            # High-confidence items
            high_conf = [i for i in items if isinstance(i, dict) and i.get("confidence", 0) >= 0.7][:5]
            if high_conf:
                lines = []
                for item in high_conf:
                    name = item.get("name", item.get("qualified_name", "?"))
                    itype = item.get("type", "?")
                    reason = item.get("reason", "unused")
                    lines.append(f"- `{name}` ({itype}) — {reason}")
                parts.append("**High-confidence dead code:**\n" + "\n".join(lines))

        # Architecture summary
        if "architecture" in analysis_context:
            arch = analysis_context["architecture"]
            if isinstance(arch, dict):
                stats = arch.get("stats", {})
                modules = arch.get("modules", [])
                parts.append(
                    f"### Architecture — {len(modules)} modules, "
                    f"{stats.get('total_items', '?')} items, "
                    f"{stats.get('cross_module_edges', '?')} cross-module edges"
                )
                if modules:
                    parts.append("**Modules:** " + ", ".join(str(m) for m in modules[:15]))

        # Catalog summary
        if "catalog" in analysis_context:
            cat = analysis_context["catalog"]
            if isinstance(cat, dict):
                total = cat.get("total", 0)
                types = cat.get("types", {})
                parts.append(f"### Catalog — {total} items")
                if types:
                    dist = ", ".join(f"{k}: {v}" for k, v in sorted(types.items(), key=lambda x: -x[1])[:8])
                    parts.append(f"**Types:** {dist}")

        # Tour summary
        if "tour" in analysis_context:
            tour = analysis_context["tour"]
            if isinstance(tour, dict):
                steps = tour.get("step_count", 0)
                entries = tour.get("entry_points", [])
                parts.append(f"### Tour — {steps} steps")
                if entries:
                    parts.append("**Entry points:** " + ", ".join(str(e) for e in entries[:5]))

        return "\n".join(parts)

    def _build_system_prompt(
        self,
        code_context: list[dict[str, Any]],
        analysis_context: dict[str, Any] | None,
        model: str | None = None,
    ) -> str:
        """Build system prompt with sandwich structure: identity → context → guidelines."""
        # TOP: Role identity
        parts = [
            "You are an expert software engineer and code analyst integrated with code-extract.",
            "Your expertise covers architecture, code quality, security, performance, and best practices.",
            "IMPORTANT: Always reference code by name and file path.",
        ]

        # Model-specific annotations (F2)
        if model == "deepseek-coder":
            parts.append("Focus on code structure, implementation patterns, and architecture relationships.")

        # MIDDLE: Code context
        if code_context:
            parts.append("\n## Code Context:")
            for i, block in enumerate(code_context[:MAX_CODE_BLOCKS]):
                name = block.get("name", "Unknown")
                btype = block.get("type", "Unknown")
                lang = block.get("language", "text")
                fpath = block.get("file", "Unknown")
                code = block.get("code", "")[:MAX_CODE_CHARS]
                if model == "deepseek-coder":
                    parts.append(
                        f"\n### File: {fpath} — {name} ({btype})\n"
                        f"Language: {lang}\n"
                        f"```{lang}\n{code}\n```"
                    )
                else:
                    parts.append(
                        f"\n### {i + 1}. {name}\n"
                        f"Type: {btype} | Language: {lang} | File: {fpath}\n"
                        f"```{lang}\n{code}\n```"
                    )

        # MIDDLE: Analysis context
        if analysis_context:
            parts.append("\n## Analysis Context:")
            parts.append(self._format_analysis_context(analysis_context))

        # BOTTOM: Response guidelines (sandwich — model pays most attention to start + end)
        parts.append("")
        parts.append("## Response Guidelines:")
        parts.append("- Lead with the direct answer, then explain reasoning.")
        parts.append("- Reference code by name, file path, and line range when possible.")
        parts.append("- Use markdown: headers for sections, code blocks for snippets, bullets for lists.")
        parts.append("- Explain both *what* the issue is and *why* it matters.")
        parts.append("- Suggest concrete fixes with code examples when applicable.")
        parts.append("- Consider language-specific idioms and best practices.")

        return "\n".join(parts)

    # ── Tool execution bridge ──────────────────────────────────────

    def _execute_tool(
        self, tool_name: str, scan_id: str, arguments: dict
    ) -> tuple[str, list[dict]]:
        """Execute a tool, routing through ToolSystem when available.

        Falls back to the legacy ``tools.execute_tool()`` dispatcher if
        no tool system was injected (zero-risk degradation).
        """
        if not self._tool_system:
            from .tools import execute_tool
            return execute_tool(tool_name, scan_id, arguments)

        start_time = time.time()
        success = True
        try:
            result, _exec_info = self._tool_system.registry.execute(
                tool_name, {"scan_id": scan_id, **arguments}
            )
            # result is (str, list) from the legacy wrapper
            return result
        except Exception as e:
            success = False
            logger.exception("Tool execution error via ToolSystem: %s", tool_name)
            return json.dumps({"error": f"Tool error: {e}"}), []
        finally:
            if self._intelligence:
                execution_time = time.time() - start_time
                try:
                    self._intelligence.record_tool_usage(
                        tool_name=tool_name,
                        parameters=arguments,
                        execution_time=execution_time,
                        success=success,
                    )
                except Exception:
                    pass

    # ── Reasoner (no tools, no system message) ─────────────────────

    def _build_reasoner_message(
        self,
        query: str,
        scan_id: str,
        code_context: list[dict[str, Any]] | None,
        analysis_context: dict[str, Any] | None,
        history_summary: str = "",
    ) -> str:
        """Build a single comprehensive user message for the Reasoner model."""
        parts = [
            "You are an expert code analyst. Analyze the following codebase information and answer the question.",
        ]

        # Pre-gather tool data
        for tool_name, label in [
            ("get_health_summary", "Health Summary"),
            ("get_architecture_info", "Architecture Info"),
            ("get_dead_code_list", "Dead Code"),
        ]:
            try:
                result_text, _ = self._execute_tool(tool_name, scan_id, {})
                if result_text and "error" not in result_text[:50].lower():
                    parts.append(f"\n## {label}:\n{result_text[:1500]}")
            except Exception:
                pass

        if code_context:
            parts.append("\n## Code Context:")
            for block in code_context[:MAX_CODE_BLOCKS]:
                name = block.get("name", "Unknown")
                lang = block.get("language", "text")
                fpath = block.get("file", "Unknown")
                code = block.get("code", "")[:MAX_CODE_CHARS]
                parts.append(f"\n### {name} ({fpath})\n```{lang}\n{code}\n```")

        if analysis_context:
            parts.append("\n## Analysis Context:")
            parts.append(self._format_analysis_context(analysis_context))

        if history_summary:
            parts.append(f"\n{history_summary}")

        parts.append(f"\n---\n\n**Question:** {query}")
        parts.append(
            "\nProvide a thorough answer using markdown formatting. "
            "Reference specific code by name and file path."
        )
        return "\n".join(parts)

    async def _reasoner_chat(
        self,
        query: str,
        scan_id: str,
        history: list[dict[str, str]],
        code_context: list[dict[str, Any]] | None = None,
        analysis_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Single-shot chat for Reasoner model (no tools, no system message)."""
        from .token_utils import estimate_messages_tokens

        history_summary, _ = self._summarize_history(history)
        content = self._build_reasoner_message(
            query, scan_id, code_context, analysis_context, history_summary,
        )
        messages = [{"role": "user", "content": content}]

        context_tokens = estimate_messages_tokens(messages)

        try:
            response = await self.client.post(
                f"{self.config.base_url}/chat/completions",
                json={
                    "model": self.config.model.value,
                    "messages": messages,
                    "temperature": self.config.get_optimal_temperature(),
                    "max_tokens": self.config.max_tokens,
                    "stream": False,
                },
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.exception("Reasoner API error: %s", e)
            return {
                "answer": f"Reasoner request failed: {e}",
                "actions": [],
                "model": self.config.model.value,
                "usage": {},
                "history_update": [],
                "context_size": context_tokens,
                "context_unit": "tokens" if has_tiktoken() else "chars_estimated",
                "tool_calls_made": 0,
            }

        usage = data.get("usage", {})
        model_name = data.get("model", self.config.model.value)
        answer = data.get("choices", [{}])[0].get("message", {}).get("content", "")

        return {
            "answer": answer,
            "actions": [],
            "model": model_name,
            "usage": usage,
            "history_update": [
                {"role": "user", "content": query},
                {"role": "assistant", "content": answer},
            ],
            "context_size": context_tokens,
            "context_unit": "tokens" if has_tiktoken() else "chars_estimated",
            "tool_calls_made": 0,
        }

    # ── Agentic copilot ───────────────────────────────────────────

    # Token budget limits per model (80% of context window)
    TOKEN_LIMITS = {
        "deepseek-chat": 64000,
        "deepseek-coder": 128000,
        "deepseek-reasoner": 128000,
    }

    async def agent_chat(
        self,
        query: str,
        scan_id: str,
        history: list[dict[str, str]],
        code_context: list[dict[str, Any]] | None = None,
        analysis_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run an agentic chat with tool-calling loop.

        The loop executes tool calls up to MAX_TOOL_ITERATIONS times.
        If the model produces a text answer during the loop, it's returned
        immediately.  Otherwise a **synthesis step** makes one final API
        call with NO tools, guaranteeing a rich text answer.

        Returns:
            {answer, actions, model, usage, history_update,
             context_size, context_unit, tool_calls_made}
        """
        # Reasoner cannot use tools — single-shot path
        if self.config.model == AIModel.DEEPSEEK_REASONER:
            return await self._reasoner_chat(
                query, scan_id, history, code_context, analysis_context,
            )

        from .tool_bridge import get_openai_tool_definitions

        # Summarize older history to keep context window lean
        history_summary, recent_history = self._summarize_history(history)

        system_prompt = self._build_agent_system_prompt(
            code_context=code_context,
            analysis_context=analysis_context,
            history_summary=history_summary,
            model=self.config.model.value,
        )
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        messages.extend(recent_history)
        messages.append({"role": "user", "content": query})

        context_tokens = estimate_messages_tokens(messages)
        context_unit = "tokens" if has_tiktoken() else "chars_estimated"

        all_actions: list[dict] = []
        tool_trace: list[dict[str, str]] = []
        tool_calls_made = 0
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        model_name = self.config.model.value
        budget = int(self.TOKEN_LIMITS.get(self.config.model.value, 64000) * 0.80)

        for iteration in range(MAX_TOOL_ITERATIONS):
            # Token budget check — force synthesis if over budget
            if estimate_messages_tokens(messages) > budget:
                logger.info("token budget exceeded — forcing synthesis")
                break

            request_body: dict[str, Any] = {
                "model": self.config.model.value,
                "messages": messages,
                "temperature": self.config.get_tool_temperature(),
                "max_tokens": self.config.max_tokens,
                "stream": False,
                "tools": get_openai_tool_definitions(),
                "tool_choice": "auto",
            }

            logger.info(
                "iter=%d/%d messages=%d",
                iteration, MAX_TOOL_ITERATIONS, len(messages),
            )

            try:
                response = await self.client.post(
                    f"{self.config.base_url}/chat/completions",
                    json=request_body,
                )
                response.raise_for_status()
            except Exception as e:
                logger.info("iter=%d API error: %s", iteration, e)
                break

            data = response.json()

            # Accumulate usage
            usage = data.get("usage", {})
            for k in total_usage:
                total_usage[k] += usage.get(k, 0)

            model_name = data.get("model", model_name)
            choice = data.get("choices", [{}])[0]
            message = choice.get("message", {})
            finish_reason = choice.get("finish_reason", "stop")
            tool_calls = message.get("tool_calls")
            content = message.get("content") or ""

            logger.debug(
                "iter=%d finish=%s tool_calls=%d content=%d chars",
                iteration, finish_reason,
                len(tool_calls) if tool_calls else 0, len(content),
            )

            # No tool calls — we have the final answer
            if finish_reason != "tool_calls" and not tool_calls:
                logger.info(
                    "direct answer: %d chars, %d actions",
                    len(content), len(all_actions),
                )
                return {
                    "answer": content,
                    "actions": all_actions,
                    "model": model_name,
                    "usage": total_usage,
                    "history_update": [
                        {"role": "user", "content": query},
                        {"role": "assistant", "content": content},
                    ],
                    "context_size": context_tokens,
                    "context_unit": context_unit,
                    "tool_calls_made": tool_calls_made,
                }

            # Process tool calls
            messages.append(message)

            for tool_call in (tool_calls or []):
                fn = tool_call.get("function", {})
                tool_name = fn.get("name", "")
                try:
                    arguments = json.loads(fn.get("arguments", "{}"))
                except (json.JSONDecodeError, TypeError):
                    arguments = {}

                tool_id = tool_call.get("id", "")
                logger.info("tool: %s(%s)", tool_name, json.dumps(arguments)[:120])
                result_text, actions = self._execute_tool(tool_name, scan_id, arguments)
                logger.debug("result: %d chars, %d actions", len(result_text), len(actions))
                all_actions.extend(actions)
                tool_calls_made += 1

                tool_trace.append({
                    "tool": tool_name,
                    "args": json.dumps(arguments)[:200],
                    "result": result_text[:500],
                })

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": result_text,
                })

        # Loop exhausted or broke — synthesize a text answer
        logger.info(
            "synthesis step: %d tool calls, %d actions",
            len(tool_trace), len(all_actions),
        )
        answer = await self._synthesize_answer(
            query=query,
            tool_trace=tool_trace,
            system_prompt=system_prompt,
            total_usage=total_usage,
        )
        return {
            "answer": answer,
            "actions": all_actions,
            "model": model_name,
            "usage": total_usage,
            "history_update": [
                {"role": "user", "content": query},
                {"role": "assistant", "content": answer},
            ],
            "context_size": context_tokens,
            "context_unit": context_unit,
            "tool_calls_made": tool_calls_made,
        }

    async def _synthesize_answer(
        self,
        query: str,
        tool_trace: list[dict[str, str]],
        system_prompt: str,
        total_usage: dict[str, int],
    ) -> str:
        """Make a final API call with NO tools to guarantee a text answer.

        Falls back to a readable summary of tool results if the call fails.
        """
        # Build a compact numbered list of tool results
        trace_lines = []
        for i, t in enumerate(tool_trace, 1):
            trace_lines.append(
                f"{i}. {t['tool']}({t['args'][:120]})\n   → {t['result'][:800]}"
            )
        trace_text = "\n".join(trace_lines) or "(no tools were called)"

        synth_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": (
                f"Original question: {query}\n\n"
                f"Tool results collected:\n{trace_text}\n\n"
                "Synthesize a comprehensive answer to the original question using the tool results above.\n"
                "- Structure your response with markdown headers and sections.\n"
                "- Transform raw data into actionable insights — don't just echo numbers.\n"
                "- Include relevant code snippets when they clarify the answer.\n"
                "- Reference specific items by name and file path.\n"
                "Do NOT call any tools."
            )},
        ]

        try:
            response = await self.client.post(
                f"{self.config.base_url}/chat/completions",
                json={
                    "model": self.config.model.value,
                    "messages": synth_messages,
                    "temperature": self.config.get_optimal_temperature(),
                    "max_tokens": self.config.max_tokens,
                    "stream": False,
                },
            )
            response.raise_for_status()
            data = response.json()

            usage = data.get("usage", {})
            for k in total_usage:
                total_usage[k] += usage.get(k, 0)

            content = data["choices"][0]["message"].get("content", "")
            if content:
                logger.info("synthesis answer: %d chars", len(content))
                return content
        except Exception as e:
            logger.info("synthesis API error: %s — using raw summary", e)

        # Graceful degradation: return raw tool results as readable text
        if tool_trace:
            parts = ["Here's what I found:\n"]
            for t in tool_trace:
                parts.append(f"### {t['tool']}\n{t['result'][:800]}")
            return "\n\n".join(parts)
        return "I wasn't able to complete the request. Please try again."

    @staticmethod
    def _summarize_history(history: list[dict[str, str]], recent_count: int = 12) -> tuple[str, list[dict[str, str]]]:
        """Summarize older history and return (summary_text, recent_messages).

        When history exceeds *recent_count* messages, older user questions are
        condensed into a short summary (no extra API call). The recent messages
        are returned as-is for explicit inclusion in the conversation.
        """
        if len(history) <= recent_count:
            return "", history

        older = history[:-recent_count]
        recent = history[-recent_count:]

        # Extract first 80 chars of each older user question
        summaries: list[str] = []
        for msg in older:
            if msg.get("role") == "user":
                text = (msg.get("content") or "")[:80].strip()
                if text:
                    summaries.append(f"- {text}")

        if summaries:
            summary = "## Earlier conversation topics:\n" + "\n".join(summaries)
        else:
            summary = ""

        return summary, recent

    def _build_agent_system_prompt(
        self,
        code_context: list[dict[str, Any]] | None = None,
        analysis_context: dict[str, Any] | None = None,
        history_summary: str = "",
        model: str | None = None,
    ) -> str:
        """System prompt with sandwich structure: identity+caps → context → guidelines."""
        # TOP: Identity + capabilities
        parts = [
            "You are an expert AI copilot integrated with code-extract, a code analysis and extraction tool.",
            "You are a skilled software engineer with deep expertise in architecture, code quality, security, and performance.",
            "You can answer questions about the scanned codebase AND take actions in the UI.",
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
        ]

        # MIDDLE: History summary
        if history_summary:
            parts.append("")
            parts.append(history_summary)

        # MIDDLE: Code context
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

        # MIDDLE: Analysis context
        if analysis_context:
            parts.append("\n## Analysis Context:")
            parts.append(self._format_analysis_context(analysis_context))

        # BOTTOM: Guidelines + Response Format (sandwich)
        parts.append("")
        parts.append("## Guidelines:")
        parts.append("- Use data tools to gather information before answering questions.")
        parts.append("- Use UI action tools when the user wants to navigate or perform operations.")
        parts.append("- For multi-step workflows (like cloning), use the appropriate workflow tool.")
        parts.append("- If an item name is ambiguous, search first to find the exact match.")
        parts.append("")
        parts.append("## Response Format:")
        parts.append("- Structure answers with markdown headers for multi-part responses.")
        parts.append("- For health/architecture questions, lead with key metrics then details.")
        parts.append("- Include code snippets when referencing specific functions or patterns.")
        parts.append("- Present lists as tables or bullets for readability.")
        parts.append("- Synthesize tool results into a narrative — don't just echo raw data.")
        parts.append("- Reference items by name and file path (e.g. `func_name` in `path/file.py`).")

        return "\n".join(parts)

    async def structured_analyze(
        self,
        scan_id: str,
        code_context: list[dict[str, Any]] | None = None,
        analysis_context: dict[str, Any] | None = None,
        focus: str | None = None,
    ) -> dict[str, Any]:
        """Structured JSON analysis — gathers data then synthesizes JSON."""
        from .token_utils import truncate_to_tokens

        # Phase 1: Data gathering
        gathered: dict[str, str] = {}
        tools_to_run = [
            ("get_health_summary", "health"),
            ("get_architecture_info", "architecture"),
            ("get_dead_code_list", "dead_code"),
        ]
        for tool_name, key in tools_to_run:
            if focus and key != focus:
                continue
            try:
                result_text, _ = self._execute_tool(tool_name, scan_id, {})
                if result_text and "error" not in result_text[:50].lower():
                    gathered[key] = truncate_to_tokens(result_text, 600)
            except Exception:
                pass

        # Phase 2: JSON synthesis
        data_section = "\n".join(
            f"## {k.replace('_', ' ').title()}:\n{v}" for k, v in gathered.items()
        )

        code_section = ""
        if code_context:
            parts = []
            for block in code_context[:MAX_CODE_BLOCKS]:
                name = block.get("name", "Unknown")
                lang = block.get("language", "text")
                code = block.get("code", "")[:MAX_CODE_CHARS]
                parts.append(f"### {name}\n```{lang}\n{code}\n```")
            code_section = "\n## Code:\n" + "\n".join(parts)

        analysis_section = ""
        if analysis_context:
            analysis_section = "\n## Analysis:\n" + self._format_analysis_context(analysis_context)

        system_prompt = (
            "You are a code analysis engine. Respond with ONLY valid JSON in this exact schema:\n"
            '{"summary": "string", "issues": [{"severity": "high|medium|low", "file": "string", '
            '"line": 0, "type": "string", "description": "string", "fix": "string"}], '
            '"recommendations": ["string"]}\n'
            "Analyze the codebase data provided and identify issues and recommendations."
        )

        user_content = f"{data_section}{code_section}{analysis_section}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            response = await self.client.post(
                f"{self.config.base_url}/chat/completions",
                json={
                    "model": self.config.model.value,
                    "messages": messages,
                    "temperature": self.config.get_optimal_temperature(),
                    "max_tokens": self.config.max_tokens,
                    "stream": False,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            return {
                "analysis": {"summary": f"Analysis request failed: {e}", "issues": [], "recommendations": []},
                "model": self.config.model.value,
                "usage": {},
                "gathered_data_keys": list(gathered.keys()),
            }

        usage = data.get("usage", {})
        model_name = data.get("model", self.config.model.value)
        raw_content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

        try:
            analysis = json.loads(raw_content)
        except (json.JSONDecodeError, TypeError):
            analysis = {"summary": raw_content, "issues": [], "recommendations": []}

        return {
            "analysis": analysis,
            "model": model_name,
            "usage": usage,
            "gathered_data_keys": list(gathered.keys()),
        }

    async def close(self):
        """Clean up the HTTP client."""
        await self.client.aclose()

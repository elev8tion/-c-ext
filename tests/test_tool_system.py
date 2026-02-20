"""Tests for the AI tool system — Phases 1-6."""

import json
import time
import threading
from datetime import datetime
from typing import Dict, Any
from unittest.mock import patch, MagicMock

import pytest

from code_extract.ai.tool_registry import (
    ToolRegistry, ToolCategory, ToolMetadata, registry as global_registry,
)
from code_extract.ai.tool_migration import (
    ToolIntegrationLayer, ToolMigrationError,
)
from code_extract.ai.tool_enhancement import (
    ExecutionContext, ToolDependency, DependencyGraph,
    ToolChain, ToolValidator,
)
from code_extract.ai.tool_system import (
    ToolSystem, ToolSystemConfig, ToolSystemHealth,
    SystemStatus, HealthStatus, HealthMetric,
)
from code_extract.ai.tool_intelligence import (
    IntelligenceLayer, UsageHistory, PatternRecognizer,
    ToolRecommender, WorkflowGenerator, PredictiveAnalytics,
    ToolUsage, ToolPattern, ToolRecommendation,
    RecommendationType, PatternType,
)
from code_extract.ai.tool_orchestration import (
    OrchestrationLayer, AutonomousOrchestrator,
    EventBus, PolicyEngine, ResourceManager, SelfOptimizer,
    OrchestrationMode, OptimizationStrategy, SystemEventType,
    SystemEvent, OrchestrationPolicy, OrchestrationResult,
)


# ── Phase 1: Tool Registry ─────────────────────────────────────


class TestToolCategory:
    def test_all_categories_exist(self):
        expected = {
            "general", "code_analysis", "ui_operations", "data_queries",
            "workflows", "boilerplate", "migration", "extraction",
        }
        actual = {c.value for c in ToolCategory}
        assert actual == expected

    def test_category_enum_access(self):
        assert ToolCategory.GENERAL.value == "general"
        assert ToolCategory.CODE_ANALYSIS.value == "code_analysis"


class TestToolRegistry:
    def _make_registry(self):
        """Create a fresh registry for isolated testing."""
        return ToolRegistry()

    def test_register_tool(self):
        reg = self._make_registry()

        @reg.register(
            name="test_tool",
            description="A test tool",
            category=ToolCategory.GENERAL,
        )
        def my_tool(x: int, y: str = "default"):
            return {"x": x, "y": y}

        tool = reg.get_tool("test_tool")
        assert tool is not None
        assert tool.name == "test_tool"
        assert tool.description == "A test tool"
        assert tool.category == "general"
        assert "x" in tool.parameters
        assert "x" in tool.required_params
        assert "y" not in tool.required_params

    def test_execute_tool(self):
        reg = self._make_registry()

        @reg.register(name="add", description="Add two numbers")
        def add_tool(a: int, b: int):
            return a + b

        result, info = reg.execute("add", {"a": 3, "b": 4})
        assert result == 7
        assert info["success"] is True
        assert info["tool"] == "add"

    def test_execute_missing_tool_raises(self):
        reg = self._make_registry()
        with pytest.raises(ValueError, match="not found"):
            reg.execute("nonexistent", {})

    def test_execute_missing_params_raises(self):
        reg = self._make_registry()

        @reg.register(name="need_param", description="Needs param")
        def need_param(required_arg: str):
            return required_arg

        with pytest.raises(ValueError, match="Missing required"):
            reg.execute("need_param", {})

    def test_execute_records_history(self):
        reg = self._make_registry()

        @reg.register(name="hist_tool", description="History test")
        def hist_tool():
            return "ok"

        assert len(reg.get_execution_history()) == 0
        reg.execute("hist_tool", {})
        assert len(reg.get_execution_history()) == 1
        assert reg.get_execution_history()[0]["tool"] == "hist_tool"

    def test_execute_records_error(self):
        reg = self._make_registry()

        @reg.register(name="fail_tool", description="Fails")
        def fail_tool():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            reg.execute("fail_tool", {})

        history = reg.get_execution_history()
        assert len(history) == 1
        assert history[0]["success"] is False
        assert "boom" in history[0]["error"]

    def test_get_all_tools(self):
        reg = self._make_registry()

        @reg.register(name="t1", description="Tool 1")
        def t1():
            pass

        @reg.register(name="t2", description="Tool 2")
        def t2():
            pass

        all_tools = reg.get_all_tools()
        assert "t1" in all_tools
        assert "t2" in all_tools

    def test_get_tools_by_category(self):
        reg = self._make_registry()

        @reg.register(name="query_tool", description="Q", category=ToolCategory.DATA_QUERIES)
        def query_tool():
            pass

        @reg.register(name="ui_tool", description="U", category=ToolCategory.UI_OPERATIONS)
        def ui_tool():
            pass

        query_tools = reg.get_tools_by_category(ToolCategory.DATA_QUERIES)
        assert len(query_tools) == 1
        assert query_tools[0].name == "query_tool"

    def test_generate_openapi_schema(self):
        reg = self._make_registry()

        @reg.register(name="schema_tool", description="Schema test")
        def schema_tool(query: str):
            return []

        schema = reg.generate_openapi_schema()
        assert schema["openapi"] == "3.0.0"
        assert "/tools/schema_tool" in schema["paths"]

    def test_context_tool_execution(self):
        reg = self._make_registry()

        @reg.register(name="ctx_tool", description="Context tool", requires_context=True)
        def ctx_tool(value: str, context: Dict[str, Any] = None):
            return {"value": value, "has_context": context is not None}

        result, _ = reg.execute("ctx_tool", {"value": "test"}, context={"user": "alice"})
        assert result["value"] == "test"
        assert result["has_context"] is True

    def test_global_registry_has_example_tools(self):
        assert global_registry.get_tool("search_items") is not None
        assert global_registry.get_tool("get_item_code") is not None


# ── Phase 2: Tool Migration ────────────────────────────────────


class TestToolIntegrationLayer:
    def test_init(self):
        reg = ToolRegistry()
        layer = ToolIntegrationLayer(reg)
        assert layer.registry is reg
        assert len(layer._migrated_tools) == 0

    def test_is_tool_function(self):
        reg = ToolRegistry()
        layer = ToolIntegrationLayer(reg)
        assert layer._is_tool_function("my_func", lambda: None) is True
        assert layer._is_tool_function("_private", lambda: None) is False
        assert layer._is_tool_function("MyClass", type("MyClass", (), {})) is False

    def test_infer_category(self):
        reg = ToolRegistry()
        layer = ToolIntegrationLayer(reg)
        assert layer._infer_category("search_items", "mod") == "data_queries"
        assert layer._infer_category("navigate_to", "mod") == "ui_operations"
        assert layer._infer_category("clone_pattern", "mod") == "workflows"
        assert layer._infer_category("boilerplate_gen", "mod") == "boilerplate"
        assert layer._infer_category("migrate_schema", "mod") == "migration"
        assert layer._infer_category("random_func", "tools.mod") == "code_analysis"
        assert layer._infer_category("random_func", "mod") == "general"

    def test_extract_tool_info(self):
        reg = ToolRegistry()
        layer = ToolIntegrationLayer(reg)

        def sample(a: int, b: str = "x"):
            """Sample tool."""
            pass

        info = layer._extract_tool_info("sample", sample, "test.module")
        assert info["name"] == "sample"
        assert info["description"] == "Sample tool."
        assert "a" in info["parameters"]
        assert "a" in info["required_params"]
        assert "b" not in info["required_params"]

    def test_migrate_tool(self):
        reg = ToolRegistry()
        layer = ToolIntegrationLayer(reg)

        def my_tool(x: int):
            return x * 2

        tool_info = layer._extract_tool_info("my_tool", my_tool, "test.module")
        name = layer.migrate_tool(tool_info)

        assert name == "my_tool"
        assert reg.get_tool("my_tool") is not None
        assert "my_tool" in layer._migrated_tools
        assert "my_tool" in layer._compatibility_layer

    def test_compatibility_shim(self):
        reg = ToolRegistry()
        layer = ToolIntegrationLayer(reg)

        @reg.register(name="shim_test", description="Shim test")
        def shim_test(val: str):
            return f"result: {val}"

        shim = layer.create_compatibility_shim()
        result = shim("shim_test", val="hello")
        assert result == "result: hello"

    def test_compatibility_shim_not_found(self):
        reg = ToolRegistry()
        layer = ToolIntegrationLayer(reg)
        shim = layer.create_compatibility_shim()

        with pytest.raises(ValueError, match="not available"):
            shim("nonexistent")

    def test_generate_migration_report(self):
        reg = ToolRegistry()
        layer = ToolIntegrationLayer(reg)
        report = layer.generate_migration_report()
        assert "migration_summary" in report
        assert report["migration_summary"]["total_migrated"] == 0


# ── Phase 3: Tool Enhancement ──────────────────────────────────


class TestExecutionContext:
    def test_init_defaults(self):
        ctx = ExecutionContext()
        assert ctx.session_id is not None
        assert len(ctx.session_id) == 16
        assert ctx.user_id is None

    def test_init_with_user(self):
        ctx = ExecutionContext(user_id="alice", session_id="custom123")
        assert ctx.user_id == "alice"
        assert ctx.session_id == "custom123"

    def test_data_operations(self):
        ctx = ExecutionContext()
        ctx.set_data("key", "value")
        assert ctx.get_data("key") == "value"
        assert ctx.get_data("missing", "default") == "default"

    def test_update_state(self):
        ctx = ExecutionContext()
        ctx.update_state({"a": 1, "b": 2})
        assert ctx.state["a"] == 1
        assert ctx.state["b"] == 2

    def test_record_execution(self):
        ctx = ExecutionContext()
        ctx.record_execution("tool_a", {"result": "ok"}, {"meta": True})
        assert len(ctx.execution_history) == 1
        assert ctx.execution_history[0]["tool"] == "tool_a"

    def test_execution_summary(self):
        ctx = ExecutionContext(user_id="bob")
        ctx.set_data("x", 1)
        ctx.record_execution("t1", None, {})
        summary = ctx.get_execution_summary()
        assert summary["user_id"] == "bob"
        assert summary["execution_count"] == 1
        assert summary["data_items"] == 1


class TestDependencyGraph:
    def test_add_and_get_dependencies(self):
        graph = DependencyGraph()
        dep = ToolDependency("tool_a", "tool_b", "prerequisite")
        graph.add_dependency(dep)

        deps = graph.get_dependencies_for("tool_a")
        assert len(deps) == 1
        assert deps[0].source_tool == "tool_a"

    def test_get_prerequisites(self):
        graph = DependencyGraph()
        graph.add_dependency(ToolDependency("a", "b", "prerequisite"))
        graph.add_dependency(ToolDependency("c", "b", "prerequisite"))

        prereqs = graph.get_prerequisites("b")
        assert set(prereqs) == {"a", "c"}

    def test_get_downstream_tools(self):
        graph = DependencyGraph()
        graph.add_dependency(ToolDependency("a", "b", "output"))
        graph.add_dependency(ToolDependency("a", "c", "output"))

        downstream = graph.get_downstream_tools("a")
        assert set(downstream) == {"b", "c"}

    def test_find_execution_path(self):
        graph = DependencyGraph()
        graph.add_dependency(ToolDependency("a", "b", "prerequisite"))
        graph.add_dependency(ToolDependency("b", "c", "prerequisite"))

        path = graph.find_execution_path("c")
        assert path == ["a", "b", "c"]

    def test_validate_workflow_valid(self):
        graph = DependencyGraph()
        graph.add_dependency(ToolDependency("a", "b", "prerequisite"))
        valid, errors = graph.validate_workflow(["a", "b"])
        assert valid is True
        assert errors == []

    def test_validate_workflow_missing_prereq(self):
        graph = DependencyGraph()
        graph.add_dependency(ToolDependency("a", "b", "prerequisite"))
        valid, errors = graph.validate_workflow(["b"])
        assert valid is False
        assert len(errors) == 1

    def test_to_dict(self):
        graph = DependencyGraph()
        graph.add_dependency(ToolDependency("a", "b", "prerequisite"))
        d = graph.to_dict()
        assert set(d["nodes"]) == {"a", "b"}
        assert len(d["edges"]) == 1


class TestToolChain:
    def test_add_steps_fluent(self):
        chain = ToolChain(name="test_chain")
        result = chain.add_step("tool_a", {"x": 1}).add_step("tool_b", {"y": 2})
        assert result is chain
        assert len(chain.steps) == 2

    def test_resolve_arguments_literal(self):
        chain = ToolChain(name="test")
        resolved = chain._resolve_arguments({"key": "value"}, {})
        assert resolved == {"key": "value"}

    def test_resolve_arguments_template(self):
        chain = ToolChain(name="test")
        resolved = chain._resolve_arguments(
            {"key": "{{ my_var }}"},
            {"my_var": "resolved_value"}
        )
        assert resolved == {"key": "resolved_value"}

    def test_resolve_arguments_missing_var(self):
        chain = ToolChain(name="test")
        with pytest.raises(ValueError, match="Undefined variable"):
            chain._resolve_arguments({"key": "{{ missing }}"}, {})

    def test_execute_chain(self):
        reg = ToolRegistry()

        @reg.register(name="double", description="Double a number")
        def double(n: int):
            return n * 2

        chain = ToolChain(name="double_chain")
        chain.add_step("double", {"n": 5}, store_result_as="doubled")

        result = chain.execute(reg)
        assert result["success"] is True
        assert result["results"]["doubled"] == 10
        assert result["steps_executed"] == 1

    def test_execute_chain_with_condition_pass(self):
        reg = ToolRegistry()

        @reg.register(name="noop", description="No-op")
        def noop():
            return "ok"

        chain = ToolChain(name="cond_chain")
        chain.add_condition(lambda data: True, "Always pass")
        chain.add_step("noop", {})

        result = chain.execute(reg)
        assert result["success"] is True

    def test_execute_chain_with_condition_fail(self):
        reg = ToolRegistry()
        chain = ToolChain(name="fail_chain")
        chain.add_condition(lambda data: False, "Always fail")
        chain.add_step("noop", {})

        with pytest.raises(ValueError, match="Chain condition failed"):
            chain.execute(reg)

    def test_to_dict(self):
        chain = ToolChain(name="my_chain", description="A chain")
        chain.add_step("t1", {"a": 1}, store_result_as="r1")
        d = chain.to_dict()
        assert d["name"] == "my_chain"
        assert len(d["steps"]) == 1
        assert d["steps"][0]["tool"] == "t1"


class TestToolValidator:
    def test_validate_missing_tool(self):
        reg = ToolRegistry()
        validator = ToolValidator(reg)
        valid, errors = validator.validate_execution("nonexistent", {})
        assert valid is False
        assert "not found" in errors[0].lower()

    def test_validate_missing_params(self):
        reg = ToolRegistry()

        @reg.register(name="needs_x", description="Needs x")
        def needs_x(x: str):
            return x

        validator = ToolValidator(reg)
        valid, errors = validator.validate_execution("needs_x", {})
        assert valid is False
        assert any("Missing" in e for e in errors)

    def test_validate_passes(self):
        reg = ToolRegistry()

        @reg.register(name="ok_tool", description="OK tool")
        def ok_tool(x: str):
            return x

        validator = ToolValidator(reg)
        valid, errors = validator.validate_execution("ok_tool", {"x": "hello"})
        assert valid is True
        assert errors == []

    def test_custom_validation_rule(self):
        reg = ToolRegistry()

        @reg.register(name="rule_tool", description="Has rules")
        def rule_tool(n: int):
            return n

        validator = ToolValidator(reg)
        validator.add_validation_rule(
            "rule_tool",
            lambda args, ctx: "n must be positive" if args.get("n", 0) < 0 else True
        )

        valid, errors = validator.validate_execution("rule_tool", {"n": -1})
        assert valid is False
        assert "n must be positive" in errors

        valid, errors = validator.validate_execution("rule_tool", {"n": 5})
        assert valid is True

    def test_resource_limit_check(self):
        reg = ToolRegistry()

        @reg.register(name="limited", description="Limited")
        def limited():
            return "ok"

        validator = ToolValidator(reg)
        ctx = ExecutionContext()
        ctx.resource_limits = {"max_executions": 2}
        ctx.execution_history = [{"tool": "a"}, {"tool": "b"}]

        valid, errors = validator.validate_execution("limited", {}, ctx)
        assert valid is False
        assert any("limit" in e.lower() for e in errors)

    def test_safe_executor(self):
        reg = ToolRegistry()

        @reg.register(name="safe_tool", description="Safe")
        def safe_tool(x: int):
            return x + 1

        validator = ToolValidator(reg)
        safe_exec = validator.create_safe_executor(reg)

        result = safe_exec("safe_tool", {"x": 10})
        assert result == 11

    def test_safe_executor_rejects_invalid(self):
        reg = ToolRegistry()

        @reg.register(name="safe_tool2", description="Safe 2")
        def safe_tool2(x: int):
            return x

        validator = ToolValidator(reg)
        safe_exec = validator.create_safe_executor(reg)

        with pytest.raises(ValueError, match="validation failed"):
            safe_exec("safe_tool2", {})


# ── Phase 4: Tool System ───────────────────────────────────────


class TestToolSystemConfig:
    def test_defaults(self):
        config = ToolSystemConfig()
        assert config.auto_discover_tools is True
        assert config.max_concurrent_executions == 10
        assert config.cache_results is True

    def test_to_dict(self):
        config = ToolSystemConfig()
        d = config.to_dict()
        assert isinstance(d, dict)
        assert "auto_discover_tools" in d
        assert "max_concurrent_executions" in d

    def test_from_dict(self):
        config = ToolSystemConfig.from_dict({"cache_results": False, "rest_port": 9090})
        assert config.cache_results is False
        assert config.rest_port == 9090

    def test_from_dict_ignores_unknown(self):
        config = ToolSystemConfig.from_dict({"unknown_field": True})
        assert not hasattr(config, "unknown_field")


class TestHealthMetric:
    def test_healthy(self):
        metric = HealthMetric(
            name="test", value=1.0, unit="seconds",
            status=HealthStatus.HEALTHY,
        )
        assert metric.is_healthy() is True

    def test_unhealthy(self):
        metric = HealthMetric(
            name="test", value=10.0, unit="seconds",
            status=HealthStatus.CRITICAL,
        )
        assert metric.is_healthy() is False

    def test_to_dict(self):
        metric = HealthMetric(
            name="latency", value=0.5, unit="seconds",
            status=HealthStatus.HEALTHY,
        )
        d = metric.to_dict()
        assert d["name"] == "latency"
        assert d["status"] == "healthy"


class TestToolSystemHealth:
    def test_update_and_get_metric(self, tmp_path):
        config = ToolSystemConfig(
            config_dir=str(tmp_path),
            enable_health_monitoring=True,
        )
        health = ToolSystemHealth(config)
        health.update_metric("latency", 0.5, "seconds", warning_threshold=1.0, critical_threshold=5.0)

        summary = health.get_metrics_summary()
        assert summary["overall_status"] == "healthy"
        assert "latency" in summary["metrics"]

    def test_warning_status(self, tmp_path):
        config = ToolSystemConfig(config_dir=str(tmp_path))
        health = ToolSystemHealth(config)
        health.update_metric("errors", 15, "count", warning_threshold=10, critical_threshold=50)
        assert health.get_overall_status() == HealthStatus.WARNING

    def test_critical_status(self, tmp_path):
        config = ToolSystemConfig(config_dir=str(tmp_path))
        health = ToolSystemHealth(config)
        health.update_metric("errors", 100, "count", warning_threshold=10, critical_threshold=50)
        assert health.get_overall_status() == HealthStatus.CRITICAL

    def test_unknown_when_empty(self, tmp_path):
        config = ToolSystemConfig(config_dir=str(tmp_path))
        health = ToolSystemHealth(config)
        assert health.get_overall_status() == HealthStatus.UNKNOWN


class TestSystemStatus:
    def test_enum_values(self):
        assert SystemStatus.INITIALIZING.value == "initializing"
        assert SystemStatus.RUNNING.value == "running"
        assert SystemStatus.STOPPED.value == "stopped"


# ── Phase 5: Intelligence Layer ────────────────────────────────


class TestToolUsage:
    def test_to_dict_roundtrip(self):
        usage = ToolUsage(
            tool_name="search",
            user_id="alice",
            execution_time=1.5,
            success=True,
        )
        d = usage.to_dict()
        restored = ToolUsage.from_dict(d)
        assert restored.tool_name == "search"
        assert restored.user_id == "alice"
        assert restored.execution_time == 1.5
        assert restored.success is True


class TestUsageHistory:
    def test_record_and_stats(self):
        history = UsageHistory()
        history.record_usage(ToolUsage("tool_a", execution_time=1.0, success=True))
        history.record_usage(ToolUsage("tool_a", execution_time=2.0, success=False))

        stats = history.get_tool_stats("tool_a")
        assert stats["count"] == 2
        assert stats["success_rate"] == 0.5
        assert stats["avg_time"] == 1.5

    def test_user_history(self):
        history = UsageHistory()
        history.record_usage(ToolUsage("t1", user_id="alice"))
        history.record_usage(ToolUsage("t2", user_id="bob"))
        history.record_usage(ToolUsage("t3", user_id="alice"))

        alice_hist = history.get_user_history("alice")
        assert len(alice_hist) == 2
        assert alice_hist[0].tool_name == "t1"

    def test_popular_tools(self):
        history = UsageHistory()
        for _ in range(5):
            history.record_usage(ToolUsage("popular"))
        for _ in range(2):
            history.record_usage(ToolUsage("less_popular"))

        popular = history.get_popular_tools(limit=2)
        assert popular[0] == ("popular", 5)
        assert popular[1] == ("less_popular", 2)

    def test_trim_history(self):
        history = UsageHistory(max_history_size=5)
        for i in range(10):
            history.record_usage(ToolUsage(f"tool_{i}"))

        assert len(history.history) == 5
        assert history.history[0].tool_name == "tool_5"

    def test_get_tool_sequences(self):
        history = UsageHistory()
        for name in ["a", "b", "c", "d", "e"]:
            history.record_usage(ToolUsage(name))

        sequences = history.get_tool_sequences(window_size=3)
        assert len(sequences) == 3
        assert sequences[0] == ["a", "b", "c"]

    def test_save_and_load(self, tmp_path):
        filepath = str(tmp_path / "history.json")
        history = UsageHistory()
        history.record_usage(ToolUsage("saved_tool", user_id="user1", execution_time=0.5))
        history.save_to_file(filepath)

        loaded = UsageHistory()
        loaded.load_from_file(filepath)
        assert len(loaded.history) == 1
        assert loaded.history[0].tool_name == "saved_tool"

    def test_recent_history(self):
        history = UsageHistory()
        for i in range(20):
            history.record_usage(ToolUsage(f"t_{i}"))

        recent = history.get_recent_history(limit=5)
        assert len(recent) == 5
        assert recent[-1].tool_name == "t_19"


class TestPatternRecognizer:
    def _populated_history(self):
        """Create a history with repeating patterns."""
        history = UsageHistory()
        # Repeat a pattern many times to exceed min_support
        for _ in range(20):
            for name in ["scan", "extract", "format"]:
                history.record_usage(ToolUsage(name))
        return history

    def test_discover_sequential_patterns(self):
        history = self._populated_history()
        recognizer = PatternRecognizer(min_support=0.05, min_confidence=0.1)
        patterns = recognizer.discover_patterns(history)
        assert len(patterns) > 0

        seq_patterns = [p for p in patterns if p.pattern_type == PatternType.SEQUENCE]
        assert len(seq_patterns) > 0

    def test_predict_next_tool(self):
        history = self._populated_history()
        recognizer = PatternRecognizer(min_support=0.05, min_confidence=0.1)
        recognizer.discover_patterns(history)

        predictions = recognizer.predict_next_tool(["scan"])
        assert len(predictions) > 0
        # "extract" should be predicted after "scan"
        tool_names = [t for t, _ in predictions]
        assert "extract" in tool_names

    def test_get_similar_patterns(self):
        history = self._populated_history()
        recognizer = PatternRecognizer(min_support=0.05, min_confidence=0.1)
        recognizer.discover_patterns(history)

        similar = recognizer.get_similar_patterns(["scan", "extract"])
        assert len(similar) > 0

    def test_empty_history(self):
        history = UsageHistory()
        recognizer = PatternRecognizer()
        patterns = recognizer.discover_patterns(history)
        assert patterns == []

    def test_predict_no_data(self):
        recognizer = PatternRecognizer()
        predictions = recognizer.predict_next_tool(["unknown"])
        assert predictions == []

    def test_predict_empty_input(self):
        recognizer = PatternRecognizer()
        predictions = recognizer.predict_next_tool([])
        assert predictions == []


class TestToolPattern:
    def test_to_dict(self):
        pattern = ToolPattern(
            pattern_id="p1",
            pattern_type=PatternType.SEQUENCE,
            tools=["a", "b"],
            frequency=10,
            confidence=0.8,
        )
        d = pattern.to_dict()
        assert d["pattern_id"] == "p1"
        assert d["pattern_type"] == "sequence"
        assert d["confidence"] == 0.8


class TestToolRecommendation:
    def test_to_dict(self):
        rec = ToolRecommendation(
            tool_name="search",
            recommendation_type=RecommendationType.CONTEXT_BASED,
            confidence=0.9,
            explanation="Matches task",
        )
        d = rec.to_dict()
        assert d["tool_name"] == "search"
        assert d["recommendation_type"] == "context_based"


class TestPredictiveAnalytics:
    def test_forecast_empty(self):
        history = UsageHistory()
        recognizer = PatternRecognizer()
        analytics = PredictiveAnalytics(history, recognizer)
        result = analytics.forecast_tool_demand()
        assert "error" in result

    def test_forecast_with_data(self):
        history = UsageHistory()
        for _ in range(10):
            history.record_usage(ToolUsage("tool_x"))

        analytics = PredictiveAnalytics(history, PatternRecognizer())
        result = analytics.forecast_tool_demand()
        assert "forecasts" in result
        assert "tool_x" in result["forecasts"]

    def test_identify_bottlenecks_slow(self):
        history = UsageHistory()
        for _ in range(10):
            history.record_usage(ToolUsage("slow_tool", execution_time=6.0, success=True))

        analytics = PredictiveAnalytics(history, PatternRecognizer())
        bottlenecks = analytics.identify_bottlenecks()
        slow = [b for b in bottlenecks if b["type"] == "slow_execution"]
        assert len(slow) == 1
        assert slow[0]["tool"] == "slow_tool"

    def test_identify_bottlenecks_error_rate(self):
        history = UsageHistory()
        for _ in range(10):
            history.record_usage(ToolUsage("bad_tool", execution_time=0.1, success=False))

        analytics = PredictiveAnalytics(history, PatternRecognizer())
        bottlenecks = analytics.identify_bottlenecks()
        error_bots = [b for b in bottlenecks if b["type"] == "high_error_rate"]
        assert len(error_bots) == 1

    def test_predict_user_needs_no_history(self):
        history = UsageHistory()
        analytics = PredictiveAnalytics(history, PatternRecognizer())
        result = analytics.predict_user_needs("unknown_user")
        assert "error" in result

    def test_predict_user_needs_with_history(self):
        history = UsageHistory()
        for _ in range(5):
            history.record_usage(ToolUsage("fav_tool", user_id="alice"))

        analytics = PredictiveAnalytics(history, PatternRecognizer())
        result = analytics.predict_user_needs("alice")
        assert "predictions" in result
        assert len(result["predictions"]) > 0


# ── Phase 6: Orchestration Layer ───────────────────────────────


class TestEventBus:
    def test_publish_subscribe(self):
        bus = EventBus()
        received = []

        bus.subscribe(SystemEventType.TOOL_EXECUTION, lambda e: received.append(e))

        event = SystemEvent(
            event_id="test_1",
            event_type=SystemEventType.TOOL_EXECUTION,
            data={"tool": "t1"},
        )
        bus.publish(event)

        assert len(received) == 1
        assert received[0].event_id == "test_1"

    def test_unsubscribe(self):
        bus = EventBus()
        received = []
        callback = lambda e: received.append(e)

        bus.subscribe(SystemEventType.ERROR, callback)
        bus.unsubscribe(SystemEventType.ERROR, callback)

        bus.publish(SystemEvent(event_id="e1", event_type=SystemEventType.ERROR))
        assert len(received) == 0

    def test_event_history(self):
        bus = EventBus()
        for i in range(5):
            bus.publish(SystemEvent(event_id=f"e_{i}", event_type=SystemEventType.WARNING))

        events = bus.get_recent_events(limit=3)
        assert len(events) == 3

    def test_get_events_by_type(self):
        bus = EventBus()
        bus.publish(SystemEvent(event_id="a", event_type=SystemEventType.ERROR))
        bus.publish(SystemEvent(event_id="b", event_type=SystemEventType.WARNING))
        bus.publish(SystemEvent(event_id="c", event_type=SystemEventType.ERROR))

        errors = bus.get_events_by_type(SystemEventType.ERROR)
        assert len(errors) == 2

    def test_callback_error_doesnt_crash(self):
        bus = EventBus()
        bus.subscribe(SystemEventType.ERROR, lambda e: 1 / 0)  # Will raise

        # Should not raise
        bus.publish(SystemEvent(event_id="x", event_type=SystemEventType.ERROR))
        assert len(bus.get_recent_events()) == 1


class TestSystemEvent:
    def test_to_dict(self):
        event = SystemEvent(
            event_id="evt_1",
            event_type=SystemEventType.TOOL_EXECUTION,
            source="test",
            data={"key": "value"},
        )
        d = event.to_dict()
        assert d["event_id"] == "evt_1"
        assert d["event_type"] == "tool_execution"
        assert d["source"] == "test"


class TestOrchestrationPolicy:
    def test_to_dict(self):
        policy = OrchestrationPolicy(
            policy_id="p1",
            name="Test Policy",
            description="A test",
            mode=OrchestrationMode.AUTOMATED,
            optimization_strategy=OptimizationStrategy.PERFORMANCE,
            priority=5,
        )
        d = policy.to_dict()
        assert d["policy_id"] == "p1"
        assert d["mode"] == "automated"
        assert d["optimization_strategy"] == "performance"
        assert d["priority"] == 5


class TestPolicyEngine:
    def test_add_and_evaluate(self):
        bus = EventBus()
        engine = PolicyEngine(bus)

        policy = OrchestrationPolicy(
            policy_id="p1", name="Auto", description="",
            mode=OrchestrationMode.AUTOMATED,
            optimization_strategy=OptimizationStrategy.BALANCED,
            rules=[],  # No rules = always applies
            priority=1, active=True,
        )
        engine.add_policy(policy)

        mode = engine.evaluate_context({})
        assert mode == OrchestrationMode.AUTOMATED

    def test_evaluate_with_rules(self):
        bus = EventBus()
        engine = PolicyEngine(bus)

        policy = OrchestrationPolicy(
            policy_id="p1", name="High Priority", description="",
            mode=OrchestrationMode.AUTONOMOUS,
            optimization_strategy=OptimizationStrategy.PERFORMANCE,
            rules=[{"type": "condition", "field": "priority", "operator": "equals", "value": "high"}],
            priority=5, active=True,
        )
        engine.add_policy(policy)

        # Matches
        assert engine.evaluate_context({"priority": "high"}) == OrchestrationMode.AUTONOMOUS
        # Doesn't match — falls back to ASSISTED
        assert engine.evaluate_context({"priority": "low"}) == OrchestrationMode.ASSISTED

    def test_deactivate_policy(self):
        bus = EventBus()
        engine = PolicyEngine(bus)

        policy = OrchestrationPolicy(
            policy_id="p1", name="Test", description="",
            mode=OrchestrationMode.AUTOMATED,
            optimization_strategy=OptimizationStrategy.BALANCED,
            priority=1, active=True,
        )
        engine.add_policy(policy)
        assert len(engine.active_policies) == 1

        engine.deactivate_policy("p1")
        assert len(engine.active_policies) == 0

    def test_remove_policy(self):
        bus = EventBus()
        engine = PolicyEngine(bus)

        policy = OrchestrationPolicy(
            policy_id="p1", name="Test", description="",
            mode=OrchestrationMode.MANUAL,
            optimization_strategy=OptimizationStrategy.BALANCED,
        )
        engine.add_policy(policy)
        engine.remove_policy("p1")

        assert "p1" not in engine.policies

    def test_rule_operators(self):
        bus = EventBus()
        engine = PolicyEngine(bus)

        # Test various operators
        rule_gt = {"type": "condition", "field": "count", "operator": "greater_than", "value": 5}
        assert engine._evaluate_rule(rule_gt, {"count": 10}) is True
        assert engine._evaluate_rule(rule_gt, {"count": 3}) is False

        rule_lt = {"type": "condition", "field": "count", "operator": "less_than", "value": 5}
        assert engine._evaluate_rule(rule_lt, {"count": 3}) is True

        rule_in = {"type": "condition", "field": "env", "operator": "in", "value": ["dev", "staging"]}
        assert engine._evaluate_rule(rule_in, {"env": "dev"}) is True
        assert engine._evaluate_rule(rule_in, {"env": "prod"}) is False

        rule_contains = {"type": "condition", "field": "name", "operator": "contains", "value": "test"}
        assert engine._evaluate_rule(rule_contains, {"name": "my_test_tool"}) is True

    def test_composite_rules(self):
        bus = EventBus()
        engine = PolicyEngine(bus)

        rule_and = {
            "type": "and",
            "rules": [
                {"type": "condition", "field": "a", "operator": "equals", "value": 1},
                {"type": "condition", "field": "b", "operator": "equals", "value": 2},
            ]
        }
        assert engine._evaluate_rule(rule_and, {"a": 1, "b": 2}) is True
        assert engine._evaluate_rule(rule_and, {"a": 1, "b": 3}) is False

        rule_or = {
            "type": "or",
            "rules": [
                {"type": "condition", "field": "x", "operator": "equals", "value": "yes"},
                {"type": "condition", "field": "y", "operator": "equals", "value": "yes"},
            ]
        }
        assert engine._evaluate_rule(rule_or, {"x": "no", "y": "yes"}) is True

        rule_not = {
            "type": "not",
            "rule": {"type": "condition", "field": "flag", "operator": "equals", "value": True}
        }
        assert engine._evaluate_rule(rule_not, {"flag": False}) is True
        assert engine._evaluate_rule(rule_not, {"flag": True}) is False

    def test_no_policies_returns_manual(self):
        bus = EventBus()
        engine = PolicyEngine(bus)
        assert engine.evaluate_context({}) == OrchestrationMode.MANUAL


class TestOrchestrationResult:
    def test_to_dict(self):
        result = OrchestrationResult(
            operation_id="op_1",
            success=True,
            results=[{"step": 1}],
            execution_time=0.5,
        )
        d = result.to_dict()
        assert d["operation_id"] == "op_1"
        assert d["success"] is True
        assert d["execution_time"] == 0.5


class TestResourceManager:
    def test_execute_io_bound(self):
        rm = ResourceManager(max_workers=2)
        try:
            future = rm.execute_io_bound(lambda: 42)
            assert future.result(timeout=5) == 42
        finally:
            rm.shutdown()

    def test_system_load(self):
        rm = ResourceManager(max_workers=4)
        try:
            load = rm.get_system_load()
            assert load["max_workers"] == 4
            assert load["active_executions"] == 0
        finally:
            rm.shutdown()

    def test_update_resource_usage(self):
        rm = ResourceManager(max_workers=2)
        try:
            rm.update_resource_usage("tool_x", cpu_time=1.5, memory_usage=100)
            usage = rm.get_resource_usage("tool_x")
            assert usage["cpu_time"] == 1.5
            assert usage["execution_count"] == 1
        finally:
            rm.shutdown()


class TestSelfOptimizer:
    def test_on_tool_execution_records_metric(self):
        bus = EventBus()
        # Use MagicMock for tool_system and intelligence to avoid full init
        optimizer = SelfOptimizer(MagicMock(), MagicMock(), bus)

        event = SystemEvent(
            event_id="e1",
            event_type=SystemEventType.TOOL_EXECUTION,
            data={"tool_id": "fast_tool", "execution_time": 0.5},
        )
        optimizer._on_tool_execution(event)

        assert len(optimizer.performance_metrics["tool_fast_tool"]) == 1

    def test_bottleneck_detection(self):
        bus = EventBus()
        detected = []
        bus.subscribe(SystemEventType.BOTTLENECK_DETECTED, lambda e: detected.append(e))

        optimizer = SelfOptimizer(MagicMock(), MagicMock(), bus)

        # Simulate 15 slow executions (threshold is 10 to trigger, avg > 2.0)
        for _ in range(15):
            event = SystemEvent(
                event_id="e",
                event_type=SystemEventType.TOOL_EXECUTION,
                data={"tool_id": "slow_tool", "execution_time": 3.0},
            )
            optimizer._on_tool_execution(event)

        assert len(detected) > 0
        assert detected[0].data["type"] == "slow_execution"

    def test_analyze_tool_performance(self):
        bus = EventBus()
        optimizer = SelfOptimizer(MagicMock(), MagicMock(), bus)

        for i in range(10):
            optimizer.performance_metrics["tool_fast"].append(0.1)
            optimizer.performance_metrics["tool_slow"].append(5.0)

        analysis = optimizer.analyze_tool_performance()
        assert analysis["tools_analyzed"] == 2
        assert any(t["tool_id"] == "slow" for t in analysis["slow_tools"])
        assert any(t["tool_id"] == "fast" for t in analysis["reliable_tools"])


class TestOrchestrationEnums:
    def test_orchestration_modes(self):
        assert OrchestrationMode.MANUAL.value == "manual"
        assert OrchestrationMode.ADAPTIVE.value == "adaptive"

    def test_optimization_strategies(self):
        assert OptimizationStrategy.PERFORMANCE.value == "performance"
        assert OptimizationStrategy.LEARNING.value == "learning"

    def test_event_types(self):
        assert SystemEventType.TOOL_EXECUTION.value == "tool_execution"
        assert SystemEventType.ERROR.value == "error"

"""
Advanced tool capabilities: context management, dependency tracking,
tool chaining, and execution validation.
"""

from typing import Dict, Any, List, Optional, Set, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import time
from datetime import datetime
from functools import wraps

from .tool_registry import ToolRegistry, ToolMetadata, ToolCategory
from .tool_migration import ToolIntegrationLayer


class ExecutionContext:
    """
    Rich execution context for tools.
    Provides data, state, and environment information.
    """

    def __init__(self, user_id: Optional[str] = None, session_id: Optional[str] = None):
        self.user_id = user_id
        self.session_id = session_id or self._generate_session_id()
        self.start_time = datetime.now()
        self.data: Dict[str, Any] = {}
        self.state: Dict[str, Any] = {}
        self.environment: Dict[str, Any] = {}
        self.execution_history: List[Dict[str, Any]] = []
        self.permissions: Set[str] = set()
        self.resource_limits: Dict[str, Any] = {}

    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        timestamp = str(time.time()).encode()
        return hashlib.sha256(timestamp).hexdigest()[:16]

    def set_data(self, key: str, value: Any) -> None:
        """Store data in context."""
        self.data[key] = value

    def get_data(self, key: str, default: Any = None) -> Any:
        """Retrieve data from context."""
        return self.data.get(key, default)

    def update_state(self, updates: Dict[str, Any]) -> None:
        """Update execution state."""
        self.state.update(updates)

    def record_execution(self, tool_name: str, result: Any, metadata: Dict[str, Any]) -> None:
        """Record a tool execution in history."""
        entry = {
            "tool": tool_name,
            "timestamp": datetime.now().isoformat(),
            "result_type": type(result).__name__,
            "metadata": metadata,
            "context_snapshot": {
                "data_keys": list(self.data.keys()),
                "state_keys": list(self.state.keys())
            }
        }
        self.execution_history.append(entry)

    def get_execution_summary(self) -> Dict[str, Any]:
        """Get summary of context execution."""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "start_time": self.start_time.isoformat(),
            "duration_seconds": (datetime.now() - self.start_time).total_seconds(),
            "execution_count": len(self.execution_history),
            "data_items": len(self.data),
            "state_items": len(self.state),
            "recent_tools": [e["tool"] for e in self.execution_history[-5:]]
        }


@dataclass
class ToolDependency:
    """Represents a dependency between tools."""
    source_tool: str
    target_tool: str
    dependency_type: str  # "input", "output", "prerequisite", "alternative"
    description: str = ""
    required: bool = True

    def __hash__(self):
        return hash((self.source_tool, self.target_tool, self.dependency_type))


class DependencyGraph:
    """
    Graph of tool dependencies.
    Enables understanding of tool relationships and workflow planning.
    """

    def __init__(self):
        self.dependencies: Set[ToolDependency] = set()
        self._tool_nodes: Set[str] = set()

    def add_dependency(self, dependency: ToolDependency) -> None:
        """Add a dependency to the graph."""
        self.dependencies.add(dependency)
        self._tool_nodes.add(dependency.source_tool)
        self._tool_nodes.add(dependency.target_tool)

    def get_dependencies_for(self, tool_name: str) -> List[ToolDependency]:
        """Get all dependencies for a specific tool."""
        return [
            dep for dep in self.dependencies
            if dep.source_tool == tool_name or dep.target_tool == tool_name
        ]

    def get_prerequisites(self, tool_name: str) -> List[str]:
        """Get tools that must run before this tool."""
        return [
            dep.source_tool for dep in self.dependencies
            if dep.target_tool == tool_name and dep.dependency_type == "prerequisite"
        ]

    def get_downstream_tools(self, tool_name: str) -> List[str]:
        """Get tools that depend on this tool's output."""
        return [
            dep.target_tool for dep in self.dependencies
            if dep.source_tool == tool_name and dep.dependency_type == "output"
        ]

    def find_execution_path(self, target_tool: str, context: Optional[ExecutionContext] = None) -> List[str]:
        """
        Find optimal execution path to run a tool, considering dependencies.

        Args:
            target_tool: Tool to execute
            context: Optional context for state-aware planning

        Returns:
            Ordered list of tools to execute
        """
        visited = set()
        execution_order = []

        def dfs(tool: str):
            if tool in visited:
                return
            visited.add(tool)

            # Add prerequisites first
            for prereq in self.get_prerequisites(tool):
                dfs(prereq)

            # Add the tool itself
            if tool not in execution_order:
                execution_order.append(tool)

        dfs(target_tool)
        return execution_order

    def validate_workflow(self, tool_sequence: List[str]) -> Tuple[bool, List[str]]:
        """
        Validate if a sequence of tools can be executed.

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []
        executed = set()

        for i, tool in enumerate(tool_sequence):
            # Check if tool exists
            if tool not in self._tool_nodes:
                errors.append(f"Unknown tool: {tool}")
                continue

            # Check prerequisites
            prerequisites = self.get_prerequisites(tool)
            missing_prereqs = [p for p in prerequisites if p not in executed]

            if missing_prereqs:
                errors.append(
                    f"Tool '{tool}' requires prerequisites not yet executed: {missing_prereqs}"
                )

            executed.add(tool)

        return len(errors) == 0, errors

    def to_dict(self) -> Dict[str, Any]:
        """Convert graph to dictionary representation."""
        return {
            "nodes": list(self._tool_nodes),
            "edges": [
                {
                    "source": dep.source_tool,
                    "target": dep.target_tool,
                    "type": dep.dependency_type,
                    "required": dep.required,
                    "description": dep.description
                }
                for dep in self.dependencies
            ]
        }


class ToolChain:
    """
    Represents a chain of tools to execute in sequence.
    Supports conditional execution and result passing.
    """

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.steps: List[Dict[str, Any]] = []
        self.variables: Dict[str, Any] = {}
        self.conditions: List[Dict[str, Any]] = []

    def add_step(self, tool_name: str, arguments: Dict[str, Any],
                 store_result_as: Optional[str] = None) -> 'ToolChain':
        """
        Add a step to the chain.

        Args:
            tool_name: Name of tool to execute
            arguments: Arguments to pass (can include template variables)
            store_result_as: Variable name to store result in

        Returns:
            Self for chaining
        """
        self.steps.append({
            "tool": tool_name,
            "arguments": arguments,
            "store_result_as": store_result_as
        })
        return self

    def add_condition(self, condition: Callable[[Dict[str, Any]], bool],
                     description: str = "") -> 'ToolChain':
        """
        Add a conditional check to the chain.

        Args:
            condition: Function that returns True/False based on context
            description: Description of the condition

        Returns:
            Self for chaining
        """
        self.conditions.append({
            "function": condition,
            "description": description
        })
        return self

    def execute(self, registry: ToolRegistry,
                initial_context: Optional[ExecutionContext] = None) -> Dict[str, Any]:
        """
        Execute the tool chain.

        Args:
            registry: Tool registry to use
            initial_context: Optional initial execution context

        Returns:
            Execution results
        """
        context = initial_context or ExecutionContext()
        results = {}

        # Check conditions
        for condition in self.conditions:
            if not condition["function"](context.data):
                raise ValueError(
                    f"Chain condition failed: {condition.get('description', 'Unknown')}"
                )

        # Execute steps
        for i, step in enumerate(self.steps):
            tool_name = step["tool"]
            arguments = self._resolve_arguments(step["arguments"], context.data)

            try:
                # Execute tool
                result, exec_info = registry.execute(tool_name, arguments, context)

                # Store result if requested
                if step["store_result_as"]:
                    context.set_data(step["store_result_as"], result)
                    results[step["store_result_as"]] = result

                # Record execution
                context.record_execution(tool_name, result, exec_info)

                print(f"Chain step {i+1}/{len(self.steps)}: {tool_name}")

            except Exception as e:
                raise RuntimeError(
                    f"Chain execution failed at step {i+1} ({tool_name}): {str(e)}"
                ) from e

        return {
            "success": True,
            "results": results,
            "context_summary": context.get_execution_summary(),
            "steps_executed": len(self.steps)
        }

    def _resolve_arguments(self, arguments: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve template variables in arguments."""
        resolved = {}

        for key, value in arguments.items():
            if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
                # Template variable
                var_name = value[2:-2].strip()
                if var_name in data:
                    resolved[key] = data[var_name]
                else:
                    raise ValueError(f"Undefined variable in template: {var_name}")
            else:
                resolved[key] = value

        return resolved

    def to_dict(self) -> Dict[str, Any]:
        """Convert chain to dictionary representation."""
        return {
            "name": self.name,
            "description": self.description,
            "steps": [
                {
                    "tool": step["tool"],
                    "arguments": step["arguments"],
                    "store_result_as": step["store_result_as"]
                }
                for step in self.steps
            ],
            "conditions": [
                {"description": cond["description"]}
                for cond in self.conditions
            ],
            "variable_count": len(self.variables)
        }


class ToolValidator:
    """
    Validates tool execution for safety and correctness.
    """

    def __init__(self, registry: ToolRegistry):
        self.registry = registry
        self.validation_rules: Dict[str, List[Callable]] = {}

    def add_validation_rule(self, tool_name: str, rule: Callable) -> None:
        """Add a validation rule for a specific tool."""
        if tool_name not in self.validation_rules:
            self.validation_rules[tool_name] = []
        self.validation_rules[tool_name].append(rule)

    def validate_execution(self, tool_name: str, arguments: Dict[str, Any],
                          context: Optional[ExecutionContext] = None) -> Tuple[bool, List[str]]:
        """
        Validate tool execution before running.

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        # Get tool metadata
        metadata = self.registry.get_tool(tool_name)
        if not metadata:
            return False, [f"Tool not found: {tool_name}"]

        # Check required parameters
        missing = [p for p in metadata.required_params if p not in arguments]
        if missing:
            errors.append(f"Missing required parameters: {missing}")

        # Type checking (basic)
        for param_name, value in arguments.items():
            if param_name in metadata.parameters:
                expected_type = metadata.parameters[param_name].get("type", "Any")
                if expected_type != "Any" and expected_type != "any":
                    # Basic type checking - in production would use proper type validation
                    actual_type = type(value).__name__
                    if expected_type.lower() != actual_type.lower():
                        errors.append(
                            f"Parameter '{param_name}' expects {expected_type}, got {actual_type}"
                        )

        # Apply custom validation rules
        if tool_name in self.validation_rules:
            for rule in self.validation_rules[tool_name]:
                try:
                    rule_result = rule(arguments, context)
                    if isinstance(rule_result, str):
                        errors.append(rule_result)
                    elif rule_result is False:
                        errors.append("Custom validation rule failed")
                except Exception as e:
                    errors.append(f"Validation rule error: {str(e)}")

        # Resource limit checking (if context provided)
        if context and context.resource_limits:
            # Check execution count limit
            max_executions = context.resource_limits.get("max_executions")
            if max_executions and len(context.execution_history) >= max_executions:
                errors.append(f"Execution limit reached: {max_executions}")

        return len(errors) == 0, errors

    def create_safe_executor(self, registry: ToolRegistry) -> Callable:
        """
        Create a safe execution wrapper that validates before running.

        Returns:
            Safe execution function
        """
        def safe_execute(tool_name: str, arguments: Dict[str, Any],
                        context: Optional[ExecutionContext] = None) -> Any:
            """Execute tool with validation."""
            # Validate
            is_valid, errors = self.validate_execution(tool_name, arguments, context)
            if not is_valid:
                raise ValueError(f"Tool execution validation failed: {', '.join(errors)}")

            # Execute
            result, exec_info = registry.execute(tool_name, arguments, context)

            # Post-execution validation (if any)
            # Could add result validation here

            return result

        return safe_execute


# Factory and utility functions
def create_enhanced_tool_system() -> Tuple[ToolRegistry, ToolIntegrationLayer, DependencyGraph, ToolValidator]:
    """
    Create a fully enhanced tool system with all capabilities.

    Returns:
        Tuple of (registry, integration, dependency_graph, validator)
    """
    # Create core components
    from .tool_registry import registry
    from .tool_migration import get_integration

    integration = get_integration()
    dependency_graph = DependencyGraph()
    validator = ToolValidator(registry)

    # Auto-populate dependency graph based on tool categories
    for tool_name, metadata in registry.get_all_tools().items():
        # Add basic dependencies based on category
        if metadata.category == ToolCategory.DATA_QUERIES.value:
            # Data queries often feed into other tools
            pass  # Would add real dependencies here

        # Add self as node
        dependency_graph._tool_nodes.add(tool_name)

    return registry, integration, dependency_graph, validator


def create_context_aware_tool(tool_func: Callable) -> Callable:
    """
    Decorator to make a tool context-aware.
    Injects execution context if tool accepts it.
    """
    @wraps(tool_func)
    def wrapper(*args, **kwargs):
        # Check if context is in signature
        import inspect
        sig = inspect.signature(tool_func)

        if 'context' in sig.parameters:
            # Create default context if not provided
            if 'context' not in kwargs:
                kwargs['context'] = ExecutionContext()

        return tool_func(*args, **kwargs)

    return wrapper

"""
Phase 6: Orchestration Layer
Advanced orchestration, self-optimization, and autonomous system management.
"""

import json
import time
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Set, Union, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque
import statistics
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
import threading
import queue
import logging

# Import previous phases
from .tool_system import ToolSystem, ToolSystemConfig
from .tool_intelligence import (
    IntelligenceLayer, ToolRecommender, WorkflowGenerator,
    PredictiveAnalytics, ToolUsage, ToolPattern,
    create_intelligence_layer, enhance_tool_system_with_intelligence
)
from .tool_registry import ToolRegistry, ToolCategory
from .tool_enhancement import ExecutionContext, ToolChain

logger = logging.getLogger(__name__)


class OrchestrationMode(Enum):
    """Modes of system orchestration."""
    MANUAL = "manual"           # User controls everything
    ASSISTED = "assisted"       # System suggests, user decides
    AUTOMATED = "automated"     # System executes with user approval
    AUTONOMOUS = "autonomous"   # System makes all decisions
    ADAPTIVE = "adaptive"       # System adapts mode based on context


class OptimizationStrategy(Enum):
    """Strategies for system optimization."""
    PERFORMANCE = "performance"      # Optimize for speed
    RELIABILITY = "reliability"      # Optimize for success rate
    RESOURCE = "resource"            # Optimize for resource usage
    BALANCED = "balanced"            # Balanced optimization
    LEARNING = "learning"            # Optimize for learning/improvement


class SystemEventType(Enum):
    """Types of system events."""
    TOOL_EXECUTION = "tool_execution"
    WORKFLOW_EXECUTION = "workflow_execution"
    RECOMMENDATION = "recommendation"
    PATTERN_DISCOVERY = "pattern_discovery"
    BOTTLENECK_DETECTED = "bottleneck_detected"
    OPTIMIZATION_APPLIED = "optimization_applied"
    SYSTEM_HEALTH_CHANGE = "system_health_change"
    USER_INTERACTION = "user_interaction"
    ERROR = "error"
    WARNING = "warning"


@dataclass
class SystemEvent:
    """A system event for monitoring and learning."""
    event_id: str
    event_type: SystemEventType
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "data": self.data,
            "metadata": self.metadata
        }


@dataclass
class OrchestrationPolicy:
    """Policy for system orchestration."""
    policy_id: str
    name: str
    description: str
    mode: OrchestrationMode
    optimization_strategy: OptimizationStrategy
    rules: List[Dict[str, Any]] = field(default_factory=list)
    constraints: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "policy_id": self.policy_id,
            "name": self.name,
            "description": self.description,
            "mode": self.mode.value,
            "optimization_strategy": self.optimization_strategy.value,
            "rules": self.rules,
            "constraints": self.constraints,
            "priority": self.priority,
            "active": self.active
        }


@dataclass
class OrchestrationResult:
    """Result of an orchestrated operation."""
    operation_id: str
    success: bool
    results: List[Dict[str, Any]]
    execution_time: float
    optimization_applied: List[Dict[str, Any]] = field(default_factory=list)
    events_generated: List[SystemEvent] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "operation_id": self.operation_id,
            "success": self.success,
            "results": self.results,
            "execution_time": self.execution_time,
            "optimization_applied": [opt for opt in self.optimization_applied],
            "events_generated": [event.to_dict() for event in self.events_generated],
            "metadata": self.metadata
        }


class EventBus:
    """Event bus for system-wide communication."""

    def __init__(self):
        self.subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self.event_history: deque = deque(maxlen=10000)
        self._lock = threading.RLock()

    def subscribe(self, event_type: SystemEventType, callback: Callable) -> None:
        """Subscribe to events of a specific type."""
        with self._lock:
            self.subscribers[event_type.value].append(callback)

    def unsubscribe(self, event_type: SystemEventType, callback: Callable) -> None:
        """Unsubscribe from events."""
        with self._lock:
            if event_type.value in self.subscribers:
                self.subscribers[event_type.value] = [
                    cb for cb in self.subscribers[event_type.value]
                    if cb != callback
                ]

    def publish(self, event: SystemEvent) -> None:
        """Publish an event to all subscribers."""
        with self._lock:
            # Store in history
            self.event_history.append(event)

            # Notify subscribers
            callbacks = self.subscribers.get(event.event_type.value, [])
            for callback in callbacks:
                try:
                    callback(event)
                except Exception as e:
                    logger.error(f"Error in event callback: {e}")

    def get_recent_events(self, limit: int = 100) -> List[SystemEvent]:
        """Get recent events."""
        return list(self.event_history)[-limit:]

    def get_events_by_type(self, event_type: SystemEventType, limit: int = 100) -> List[SystemEvent]:
        """Get recent events of a specific type."""
        return [e for e in self.event_history if e.event_type == event_type][-limit:]


class PolicyEngine:
    """Engine for managing and applying orchestration policies."""

    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.policies: Dict[str, OrchestrationPolicy] = {}
        self.active_policies: List[OrchestrationPolicy] = []
        self._policy_lock = threading.RLock()

        # Subscribe to events
        self.event_bus.subscribe(SystemEventType.SYSTEM_HEALTH_CHANGE, self._on_health_change)
        self.event_bus.subscribe(SystemEventType.BOTTLENECK_DETECTED, self._on_bottleneck_detected)

    def add_policy(self, policy: OrchestrationPolicy) -> None:
        """Add a new policy."""
        with self._policy_lock:
            self.policies[policy.policy_id] = policy
            if policy.active:
                self._activate_policy(policy)

    def remove_policy(self, policy_id: str) -> None:
        """Remove a policy."""
        with self._policy_lock:
            if policy_id in self.policies:
                policy = self.policies[policy_id]
                if policy in self.active_policies:
                    self.active_policies.remove(policy)
                del self.policies[policy_id]

    def activate_policy(self, policy_id: str) -> None:
        """Activate a policy."""
        with self._policy_lock:
            if policy_id in self.policies:
                policy = self.policies[policy_id]
                if policy not in self.active_policies:
                    self._activate_policy(policy)

    def deactivate_policy(self, policy_id: str) -> None:
        """Deactivate a policy."""
        with self._policy_lock:
            if policy_id in self.policies:
                policy = self.policies[policy_id]
                if policy in self.active_policies:
                    self.active_policies.remove(policy)
                    policy.active = False

    def _activate_policy(self, policy: OrchestrationPolicy) -> None:
        """Activate a policy."""
        self.active_policies.append(policy)
        policy.active = True

        # Sort by priority (higher priority first)
        self.active_policies.sort(key=lambda p: p.priority, reverse=True)

        # Publish event
        event = SystemEvent(
            event_id=f"policy_activated_{policy.policy_id}",
            event_type=SystemEventType.OPTIMIZATION_APPLIED,
            source="PolicyEngine",
            data={"policy": policy.to_dict()},
            metadata={"action": "policy_activated"}
        )
        self.event_bus.publish(event)

    def evaluate_context(self, context: Dict[str, Any]) -> OrchestrationMode:
        """Evaluate context and determine orchestration mode."""
        with self._policy_lock:
            if not self.active_policies:
                return OrchestrationMode.MANUAL

            # Apply policies in priority order
            for policy in self.active_policies:
                if self._policy_applies(policy, context):
                    return policy.mode

            # Default to assisted mode
            return OrchestrationMode.ASSISTED

    def get_optimization_strategy(self, context: Dict[str, Any]) -> OptimizationStrategy:
        """Get optimization strategy for context."""
        with self._policy_lock:
            if not self.active_policies:
                return OptimizationStrategy.BALANCED

            for policy in self.active_policies:
                if self._policy_applies(policy, context):
                    return policy.optimization_strategy

            return OptimizationStrategy.BALANCED

    def _policy_applies(self, policy: OrchestrationPolicy, context: Dict[str, Any]) -> bool:
        """Check if a policy applies to the given context."""
        if not policy.rules:
            return True

        for rule in policy.rules:
            if not self._evaluate_rule(rule, context):
                return False

        return True

    def _evaluate_rule(self, rule: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """Evaluate a single rule."""
        rule_type = rule.get("type", "condition")

        if rule_type == "condition":
            field_name = rule.get("field")
            operator = rule.get("operator", "equals")
            value = rule.get("value")

            if field_name not in context:
                return False

            context_value = context[field_name]

            if operator == "equals":
                return context_value == value
            elif operator == "not_equals":
                return context_value != value
            elif operator == "greater_than":
                return context_value > value
            elif operator == "less_than":
                return context_value < value
            elif operator == "contains":
                return value in context_value
            elif operator == "in":
                return context_value in value
            elif operator == "not_in":
                return context_value not in value

        elif rule_type == "and":
            subrules = rule.get("rules", [])
            return all(self._evaluate_rule(subrule, context) for subrule in subrules)

        elif rule_type == "or":
            subrules = rule.get("rules", [])
            return any(self._evaluate_rule(subrule, context) for subrule in subrules)

        elif rule_type == "not":
            subrule = rule.get("rule", {})
            return not self._evaluate_rule(subrule, context)

        return False

    def _on_health_change(self, event: SystemEvent) -> None:
        """Handle system health change events."""
        health_status = event.data.get("status")

        if health_status == "degraded":
            # Activate reliability-focused policies
            for policy in self.policies.values():
                if policy.optimization_strategy == OptimizationStrategy.RELIABILITY:
                    self.activate_policy(policy.policy_id)

    def _on_bottleneck_detected(self, event: SystemEvent) -> None:
        """Handle bottleneck detection events."""
        bottleneck_type = event.data.get("type")

        if bottleneck_type == "slow_execution":
            # Activate performance-focused policies
            for policy in self.policies.values():
                if policy.optimization_strategy == OptimizationStrategy.PERFORMANCE:
                    self.activate_policy(policy.policy_id)


class ResourceManager:
    """Manages system resources and load balancing."""

    def __init__(self, max_workers: int = 10):
        self.max_workers = max_workers

        # Thread pool for I/O bound operations
        self.thread_pool = ThreadPoolExecutor(max_workers=max_workers)

        # Resource tracking
        self.resource_usage: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "cpu_time": 0.0,
            "memory_usage": 0,
            "execution_count": 0,
            "last_used": None
        })

        # Load balancing
        self.active_executions = 0
        self._lock = threading.RLock()

        # Start monitoring thread
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_resources, daemon=True)
        self.monitor_thread.start()

    def execute_io_bound(self, func: Callable, *args, **kwargs) -> concurrent.futures.Future:
        """Execute an I/O bound operation."""
        with self._lock:
            self.active_executions += 1

        future = self.thread_pool.submit(func, *args, **kwargs)

        # Add callback to track completion
        future.add_done_callback(self._on_execution_complete)

        return future

    def _on_execution_complete(self, future: concurrent.futures.Future) -> None:
        """Handle execution completion."""
        with self._lock:
            self.active_executions -= 1

    def get_resource_usage(self, resource_id: str) -> Dict[str, Any]:
        """Get resource usage for a specific resource."""
        return self.resource_usage.get(resource_id, {}).copy()

    def update_resource_usage(self, resource_id: str, cpu_time: float = 0.0,
                            memory_usage: int = 0) -> None:
        """Update resource usage."""
        with self._lock:
            usage = self.resource_usage[resource_id]
            usage["cpu_time"] += cpu_time
            usage["memory_usage"] = max(usage["memory_usage"], memory_usage)
            usage["execution_count"] += 1
            usage["last_used"] = datetime.now()

    def get_system_load(self) -> Dict[str, Any]:
        """Get current system load."""
        with self._lock:
            return {
                "active_executions": self.active_executions,
                "max_workers": self.max_workers,
                "total_resources": len(self.resource_usage),
                "timestamp": datetime.now().isoformat()
            }

    def _monitor_resources(self) -> None:
        """Monitor resource usage."""
        while self.monitoring:
            time.sleep(30)  # Check every 30 seconds

            # Clean up old resource entries
            cutoff_time = datetime.now() - timedelta(hours=1)
            with self._lock:
                to_delete = []
                for resource_id, usage in self.resource_usage.items():
                    if usage["last_used"] and usage["last_used"] < cutoff_time:
                        to_delete.append(resource_id)

                for resource_id in to_delete:
                    del self.resource_usage[resource_id]

    def shutdown(self) -> None:
        """Shutdown resource manager."""
        self.monitoring = False
        self.thread_pool.shutdown(wait=True)


class SelfOptimizer:
    """Self-optimizing component that learns and improves over time."""

    def __init__(self, tool_system: ToolSystem, intelligence_layer: IntelligenceLayer,
                 event_bus: EventBus):
        self.tool_system = tool_system
        self.intelligence = intelligence_layer
        self.event_bus = event_bus
        self.optimization_history: List[Dict[str, Any]] = []
        self.performance_metrics: Dict[str, List[float]] = defaultdict(list)

        # Subscribe to events
        self.event_bus.subscribe(SystemEventType.TOOL_EXECUTION, self._on_tool_execution)
        self.event_bus.subscribe(SystemEventType.WORKFLOW_EXECUTION, self._on_workflow_execution)

    def _on_tool_execution(self, event: SystemEvent) -> None:
        """Handle tool execution events."""
        tool_id = event.data.get("tool_id")
        execution_time = event.data.get("execution_time")

        if tool_id and execution_time:
            self.performance_metrics[f"tool_{tool_id}"].append(execution_time)

            # Check for performance degradation
            if len(self.performance_metrics[f"tool_{tool_id}"]) > 10:
                recent_times = self.performance_metrics[f"tool_{tool_id}"][-10:]
                avg_time = statistics.mean(recent_times)

                if avg_time > 2.0:  # Threshold for slow execution
                    bottleneck_event = SystemEvent(
                        event_id=f"bottleneck_{tool_id}",
                        event_type=SystemEventType.BOTTLENECK_DETECTED,
                        source="SelfOptimizer",
                        data={
                            "type": "slow_execution",
                            "tool_id": tool_id,
                            "avg_execution_time": avg_time,
                            "threshold": 2.0
                        }
                    )
                    self.event_bus.publish(bottleneck_event)

    def _on_workflow_execution(self, event: SystemEvent) -> None:
        """Handle workflow execution events."""
        workflow_id = event.data.get("workflow_id")
        total_time = event.data.get("total_time")

        if workflow_id and total_time:
            self.performance_metrics[f"workflow_{workflow_id}"].append(total_time)

            # Analyze workflow patterns for optimization
            if len(self.performance_metrics[f"workflow_{workflow_id}"]) > 5:
                self._analyze_workflow_pattern(workflow_id, event.data)

    def _analyze_workflow_pattern(self, workflow_id: str, data: Dict[str, Any]) -> None:
        """Analyze workflow patterns for optimization opportunities."""
        steps = data.get("steps", [])
        if not steps:
            return

        # Find slowest steps
        step_times = [(step.get("tool_id", f"step_{i}"), step.get("execution_time", 0))
                     for i, step in enumerate(steps)]
        step_times.sort(key=lambda x: x[1], reverse=True)

        if step_times and step_times[0][1] > 1.0:  # Slow step threshold
            # Suggest optimization
            optimization = {
                "type": "workflow_optimization",
                "workflow_id": workflow_id,
                "bottleneck": step_times[0][0],
                "execution_time": step_times[0][1],
                "suggestion": f"Consider optimizing or parallelizing step: {step_times[0][0]}",
                "timestamp": datetime.now().isoformat()
            }

            self.optimization_history.append(optimization)

            # Publish optimization suggestion
            event = SystemEvent(
                event_id=f"optimization_suggestion_{workflow_id}",
                event_type=SystemEventType.OPTIMIZATION_APPLIED,
                source="SelfOptimizer",
                data=optimization
            )
            self.event_bus.publish(event)

    def get_optimization_suggestions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent optimization suggestions."""
        return self.optimization_history[-limit:]

    def analyze_tool_performance(self) -> Dict[str, Any]:
        """Analyze overall tool performance."""
        analysis = {
            "tools_analyzed": 0,
            "slow_tools": [],
            "reliable_tools": [],
            "recommendations": []
        }

        for key, times in self.performance_metrics.items():
            if key.startswith("tool_"):
                tool_id = key[5:]  # Remove "tool_" prefix
                analysis["tools_analyzed"] += 1

                if len(times) >= 5:
                    avg_time = statistics.mean(times[-5:])
                    std_dev = statistics.stdev(times[-5:]) if len(times) >= 2 else 0

                    if avg_time > 1.5:
                        analysis["slow_tools"].append({
                            "tool_id": tool_id,
                            "avg_time": avg_time,
                            "std_dev": std_dev
                        })

                    if std_dev < 0.1 * avg_time:  # Low variance = reliable
                        analysis["reliable_tools"].append({
                            "tool_id": tool_id,
                            "avg_time": avg_time,
                            "std_dev": std_dev
                        })

        return analysis


class AutonomousOrchestrator:
    """Main orchestrator for autonomous system management."""

    def __init__(self, tool_system: ToolSystem, tool_registry: ToolRegistry,
                 intelligence_layer: IntelligenceLayer):
        self.tool_system = tool_system
        self.tool_registry = tool_registry
        self.intelligence = intelligence_layer

        # Core components
        self.event_bus = EventBus()
        self.policy_engine = PolicyEngine(self.event_bus)
        self.resource_manager = ResourceManager()
        self.self_optimizer = SelfOptimizer(tool_system, intelligence_layer, self.event_bus)

        # State management
        self.active_operations: Dict[str, Dict[str, Any]] = {}
        self.operation_history: deque = deque(maxlen=1000)
        self._operation_lock = threading.RLock()

        # Default policies
        self._setup_default_policies()

        # Start system monitoring
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._system_monitor, daemon=True)
        self.monitor_thread.start()

        logger.info("AutonomousOrchestrator initialized")

    def _setup_default_policies(self) -> None:
        """Setup default orchestration policies."""

        # Performance-focused policy
        perf_policy = OrchestrationPolicy(
            policy_id="perf_focused",
            name="Performance Focused",
            description="Optimize for execution speed",
            mode=OrchestrationMode.AUTOMATED,
            optimization_strategy=OptimizationStrategy.PERFORMANCE,
            rules=[
                {
                    "type": "condition",
                    "field": "priority",
                    "operator": "equals",
                    "value": "high"
                }
            ],
            priority=3
        )
        self.policy_engine.add_policy(perf_policy)

        # Reliability-focused policy
        reliability_policy = OrchestrationPolicy(
            policy_id="reliability_focused",
            name="Reliability Focused",
            description="Optimize for success rate",
            mode=OrchestrationMode.ASSISTED,
            optimization_strategy=OptimizationStrategy.RELIABILITY,
            rules=[
                {
                    "type": "condition",
                    "field": "task_type",
                    "operator": "in",
                    "value": ["critical", "production"]
                }
            ],
            priority=5  # Highest priority for critical tasks
        )
        self.policy_engine.add_policy(reliability_policy)

        # Learning-focused policy
        learning_policy = OrchestrationPolicy(
            policy_id="learning_focused",
            name="Learning Focused",
            description="Optimize for system learning",
            mode=OrchestrationMode.AUTONOMOUS,
            optimization_strategy=OptimizationStrategy.LEARNING,
            rules=[
                {
                    "type": "condition",
                    "field": "environment",
                    "operator": "equals",
                    "value": "development"
                }
            ],
            priority=1
        )
        self.policy_engine.add_policy(learning_policy)

    def orchestrate_operation(self, operation_type: str, parameters: Dict[str, Any],
                            context: Dict[str, Any] = None) -> OrchestrationResult:
        """Orchestrate a complete operation."""
        operation_id = self._generate_operation_id()
        start_time = time.time()

        if context is None:
            context = {}

        # Determine orchestration mode
        orchestration_mode = self.policy_engine.evaluate_context(context)
        optimization_strategy = self.policy_engine.get_optimization_strategy(context)

        # Log operation start
        with self._operation_lock:
            self.active_operations[operation_id] = {
                "type": operation_type,
                "parameters": parameters,
                "context": context,
                "mode": orchestration_mode.value,
                "strategy": optimization_strategy.value,
                "start_time": start_time,
                "status": "running"
            }

        # Publish operation start event
        start_event = SystemEvent(
            event_id=f"operation_start_{operation_id}",
            event_type=SystemEventType.WORKFLOW_EXECUTION,
            source="AutonomousOrchestrator",
            data={
                "operation_id": operation_id,
                "type": operation_type,
                "mode": orchestration_mode.value,
                "strategy": optimization_strategy.value
            }
        )
        self.event_bus.publish(start_event)

        try:
            # Execute based on orchestration mode
            if orchestration_mode == OrchestrationMode.MANUAL:
                results = self._execute_manual(operation_type, parameters, context)
            elif orchestration_mode == OrchestrationMode.ASSISTED:
                results = self._execute_assisted(operation_type, parameters, context)
            elif orchestration_mode == OrchestrationMode.AUTOMATED:
                results = self._execute_automated(operation_type, parameters, context)
            elif orchestration_mode == OrchestrationMode.AUTONOMOUS:
                results = self._execute_autonomous(operation_type, parameters, context)
            elif orchestration_mode == OrchestrationMode.ADAPTIVE:
                results = self._execute_adaptive(operation_type, parameters, context)
            else:
                results = []

            execution_time = time.time() - start_time

            # Create result
            result = OrchestrationResult(
                operation_id=operation_id,
                success=bool(results),
                results=results,
                execution_time=execution_time,
                metadata={
                    "mode": orchestration_mode.value,
                    "strategy": optimization_strategy.value,
                    "context": context
                }
            )

            # Update operation status
            with self._operation_lock:
                if operation_id in self.active_operations:
                    self.active_operations[operation_id].update({
                        "status": "completed",
                        "end_time": time.time(),
                        "success": bool(results)
                    })
                    self.operation_history.append(self.active_operations[operation_id])
                    del self.active_operations[operation_id]

            # Publish completion event
            complete_event = SystemEvent(
                event_id=f"operation_complete_{operation_id}",
                event_type=SystemEventType.WORKFLOW_EXECUTION,
                source="AutonomousOrchestrator",
                data={
                    "operation_id": operation_id,
                    "success": bool(results),
                    "execution_time": execution_time,
                    "result_count": len(results)
                }
            )
            self.event_bus.publish(complete_event)

            return result

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Operation {operation_id} failed: {e}")

            # Update operation status
            with self._operation_lock:
                if operation_id in self.active_operations:
                    self.active_operations[operation_id].update({
                        "status": "failed",
                        "end_time": time.time(),
                        "error": str(e)
                    })
                    self.operation_history.append(self.active_operations[operation_id])
                    del self.active_operations[operation_id]

            # Publish error event
            error_event = SystemEvent(
                event_id=f"operation_error_{operation_id}",
                event_type=SystemEventType.ERROR,
                source="AutonomousOrchestrator",
                data={
                    "operation_id": operation_id,
                    "error": str(e),
                    "execution_time": execution_time
                }
            )
            self.event_bus.publish(error_event)

            return OrchestrationResult(
                operation_id=operation_id,
                success=False,
                results=[],
                execution_time=execution_time,
                metadata={"error": str(e)}
            )

    def _execute_manual(self, operation_type: str, parameters: Dict[str, Any],
                       context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Execute in manual mode - minimal automation."""
        # In manual mode, just return tool recommendations
        rec_context = {"task_description": parameters.get("query", "")}
        recommendations = self.intelligence.get_recommendations(rec_context)

        return [{"type": "recommendations", "data": recommendations}]

    def _execute_assisted(self, operation_type: str, parameters: Dict[str, Any],
                         context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Execute in assisted mode - system suggests, user decides."""
        query = parameters.get("query", "")

        # Get tool recommendations
        rec_context = {"task_description": query}
        recommendations = self.intelligence.get_recommendations(rec_context, limit=3)

        # Generate workflow suggestions
        workflow_suggestions = self.intelligence.generate_workflow_for_goal(query)

        return [
            {"type": "tool_recommendations", "data": recommendations},
            {"type": "workflow_suggestions", "data": workflow_suggestions}
        ]

    def _execute_automated(self, operation_type: str, parameters: Dict[str, Any],
                          context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Execute in automated mode - system executes with validation."""
        query = parameters.get("query", "")

        # Generate and execute workflow
        workflow_result = self.intelligence.generate_workflow_for_goal(query)

        if not workflow_result.get("workflow"):
            return []

        results = []
        for tool_name in workflow_result["workflow"]:
            # Execute tool
            tool_result = self.tool_system.execute_tool(tool_name)

            # Publish execution event
            exec_event = SystemEvent(
                event_id=f"tool_exec_{tool_name}_{int(time.time())}",
                event_type=SystemEventType.TOOL_EXECUTION,
                source="AutonomousOrchestrator",
                data={
                    "tool_id": tool_name,
                    "result": tool_result,
                    "execution_time": tool_result.get("execution_time", 0)
                }
            )
            self.event_bus.publish(exec_event)

            results.append({
                "tool_id": tool_name,
                "result": tool_result
            })

        return results

    def _execute_autonomous(self, operation_type: str, parameters: Dict[str, Any],
                           context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Execute in autonomous mode - system makes all decisions."""
        query = parameters.get("query", "")

        # Get predictive insights
        insights = self.intelligence.get_insights()

        # Generate workflow
        workflow_result = self.intelligence.generate_workflow_for_goal(query)

        if not workflow_result.get("workflow"):
            return []

        # Execute steps via resource manager
        results = []
        futures = []
        for tool_name in workflow_result["workflow"]:
            future = self.resource_manager.execute_io_bound(
                self._execute_tool_with_tracking,
                tool_name, {}, None
            )
            futures.append((tool_name, future))

        # Collect results
        for tool_name, future in futures:
            try:
                result = future.result(timeout=30)
                results.append(result)
            except concurrent.futures.TimeoutError:
                logger.warning(f"Tool execution timeout for {tool_name}")
            except Exception as e:
                logger.error(f"Tool execution failed for {tool_name}: {e}")

        return results

    def _execute_adaptive(self, operation_type: str, parameters: Dict[str, Any],
                         context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Execute in adaptive mode - system adapts based on real-time feedback."""
        # Start with assisted mode
        initial_results = self._execute_assisted(operation_type, parameters, context)

        # Monitor execution and adapt
        if initial_results and len(initial_results) > 0:
            feedback = context.get("feedback")
            if feedback == "positive" or context.get("confidence", 0) > 0.7:
                # Switch to automated mode for similar future operations
                self._learn_from_success(operation_type, parameters, context)
                return self._execute_automated(operation_type, parameters, context)

        return initial_results

    def _execute_tool_with_tracking(self, tool_id: str, parameters: Dict[str, Any],
                                   step_id: str = None) -> Dict[str, Any]:
        """Execute a tool with resource tracking."""
        start_time = time.time()

        try:
            result = self.tool_system.execute_tool(tool_id, **parameters)
            execution_time = time.time() - start_time

            # Update resource usage
            self.resource_manager.update_resource_usage(
                f"tool_{tool_id}",
                cpu_time=execution_time,
                memory_usage=0
            )

            # Publish execution event
            exec_event = SystemEvent(
                event_id=f"tool_exec_{tool_id}_{int(time.time())}",
                event_type=SystemEventType.TOOL_EXECUTION,
                source="AutonomousOrchestrator",
                data={
                    "tool_id": tool_id,
                    "parameters": parameters,
                    "execution_time": execution_time,
                    "success": result.get("success", False),
                    "step_id": step_id
                }
            )
            self.event_bus.publish(exec_event)

            return {
                "tool_id": tool_id,
                "result": result,
                "execution_time": execution_time,
                "step_id": step_id
            }

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Tool {tool_id} execution failed: {e}")

            # Publish error event
            error_event = SystemEvent(
                event_id=f"tool_error_{tool_id}_{int(time.time())}",
                event_type=SystemEventType.ERROR,
                source="AutonomousOrchestrator",
                data={
                    "tool_id": tool_id,
                    "error": str(e),
                    "execution_time": execution_time,
                    "step_id": step_id
                }
            )
            self.event_bus.publish(error_event)

            return {
                "tool_id": tool_id,
                "error": str(e),
                "execution_time": execution_time,
                "step_id": step_id,
                "success": False
            }

    def _learn_from_success(self, operation_type: str, parameters: Dict[str, Any],
                           context: Dict[str, Any]) -> None:
        """Learn from successful operations."""
        # Record successful pattern
        pattern = {
            "operation_type": operation_type,
            "parameters": parameters,
            "context": context,
            "timestamp": datetime.now().isoformat(),
            "success": True
        }

        # Record via intelligence layer's usage recording
        self.intelligence.record_tool_usage(
            tool_name=f"workflow_{operation_type}",
            context=context,
            parameters=parameters,
            success=True
        )

        # Publish learning event
        learn_event = SystemEvent(
            event_id=f"learning_pattern_{int(time.time())}",
            event_type=SystemEventType.PATTERN_DISCOVERY,
            source="AutonomousOrchestrator",
            data=pattern
        )
        self.event_bus.publish(learn_event)

    def _generate_operation_id(self) -> str:
        """Generate a unique operation ID."""
        timestamp = int(time.time() * 1000)
        random_part = random.randint(1000, 9999)
        return f"op_{timestamp}_{random_part}"

    def _system_monitor(self) -> None:
        """Monitor system health and performance."""
        self._last_health_status = "healthy"

        while self.monitoring:
            try:
                # Check system load
                system_load = self.resource_manager.get_system_load()

                # Check active operations
                with self._operation_lock:
                    active_count = len(self.active_operations)
                    long_running = [
                        op_id for op_id, op in self.active_operations.items()
                        if time.time() - op.get("start_time", 0) > 300  # 5 minutes
                    ]

                # Determine system health
                health_status = "healthy"
                if system_load["active_executions"] > self.resource_manager.max_workers * 0.8:
                    health_status = "high_load"
                if len(long_running) > 3:
                    health_status = "degraded"

                # Publish health event if status changed
                if self._last_health_status != health_status:
                    health_event = SystemEvent(
                        event_id=f"health_change_{int(time.time())}",
                        event_type=SystemEventType.SYSTEM_HEALTH_CHANGE,
                        source="AutonomousOrchestrator",
                        data={
                            "status": health_status,
                            "previous_status": self._last_health_status,
                            "system_load": system_load,
                            "active_operations": active_count,
                            "long_running": len(long_running)
                        }
                    )
                    self.event_bus.publish(health_event)

                self._last_health_status = health_status

                # Sleep before next check
                time.sleep(60)  # Check every minute

            except Exception as e:
                logger.error(f"System monitor error: {e}")
                time.sleep(60)

    def get_system_status(self) -> Dict[str, Any]:
        """Get current system status."""
        with self._operation_lock:
            active_ops = list(self.active_operations.keys())

        system_load = self.resource_manager.get_system_load()
        optimization_suggestions = self.self_optimizer.get_optimization_suggestions(5)

        return {
            "status": "running",
            "active_operations": len(active_ops),
            "system_load": system_load,
            "recent_optimizations": optimization_suggestions,
            "orchestration_mode": "adaptive",
            "timestamp": datetime.now().isoformat()
        }

    def get_operation_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get operation history."""
        return list(self.operation_history)[-limit:]

    def cancel_operation(self, operation_id: str) -> bool:
        """Cancel an active operation."""
        with self._operation_lock:
            if operation_id in self.active_operations:
                self.active_operations[operation_id]["status"] = "cancelled"
                self.active_operations[operation_id]["end_time"] = time.time()
                self.operation_history.append(self.active_operations[operation_id])
                del self.active_operations[operation_id]

                # Publish cancellation event
                cancel_event = SystemEvent(
                    event_id=f"operation_cancelled_{operation_id}",
                    event_type=SystemEventType.WORKFLOW_EXECUTION,
                    source="AutonomousOrchestrator",
                    data={"operation_id": operation_id}
                )
                self.event_bus.publish(cancel_event)

                return True

        return False

    def add_custom_policy(self, policy: OrchestrationPolicy) -> None:
        """Add a custom orchestration policy."""
        self.policy_engine.add_policy(policy)

    def get_active_policies(self) -> List[Dict[str, Any]]:
        """Get active policies."""
        return [policy.to_dict() for policy in self.policy_engine.active_policies]

    def shutdown(self) -> None:
        """Shutdown the orchestrator."""
        self.monitoring = False

        # Cancel all active operations
        with self._operation_lock:
            for operation_id in list(self.active_operations.keys()):
                self.cancel_operation(operation_id)

        # Shutdown resource manager
        self.resource_manager.shutdown()

        logger.info("AutonomousOrchestrator shutdown complete")


class OrchestrationLayer:
    """
    Main Orchestration Layer - Integrates all Phase 6 components.

    Provides:
    1. Multi-mode orchestration (manual, assisted, automated, autonomous, adaptive)
    2. Policy-based decision making
    3. Resource management and load balancing
    4. Self-optimization and learning
    5. Event-driven architecture
    6. System health monitoring
    """

    def __init__(self, tool_system: ToolSystem, intelligence_layer: IntelligenceLayer,
                 config: Optional[Dict[str, Any]] = None):
        """Initialize the Orchestration Layer."""
        self.tool_system = tool_system
        self.intelligence = intelligence_layer
        self.config = config or {}

        # Get tool registry from tool system
        self.tool_registry = tool_system.registry

        # Initialize orchestrator
        self.orchestrator = AutonomousOrchestrator(
            tool_system=tool_system,
            tool_registry=self.tool_registry,
            intelligence_layer=intelligence_layer
        )

        # Setup API endpoints
        self._setup_api()

        logger.info("Orchestration Layer initialized")

    def _setup_api(self) -> None:
        """Setup API endpoints for external interaction."""
        self.api_endpoints = {
            "orchestrate": self.orchestrate,
            "get_status": self.get_status,
            "get_history": self.get_operation_history,
            "cancel_operation": self.cancel_operation,
            "add_policy": self.add_policy,
            "get_policies": self.get_policies,
            "get_insights": self.get_insights,
            "optimize_system": self.optimize_system
        }

    def orchestrate(self, operation_type: str, parameters: Dict[str, Any],
                   context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Orchestrate an operation.

        Args:
            operation_type: Type of operation
            parameters: Operation parameters
            context: Context information

        Returns:
            Orchestration result
        """
        result = self.orchestrator.orchestrate_operation(operation_type, parameters, context)
        return result.to_dict()

    def get_status(self) -> Dict[str, Any]:
        """Get system status."""
        return self.orchestrator.get_system_status()

    def get_operation_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get operation history."""
        return self.orchestrator.get_operation_history(limit)

    def cancel_operation(self, operation_id: str) -> Dict[str, Any]:
        """Cancel an operation."""
        success = self.orchestrator.cancel_operation(operation_id)
        return {"success": success, "operation_id": operation_id}

    def add_policy(self, policy_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add a custom policy."""
        try:
            policy = OrchestrationPolicy(
                policy_id=policy_data.get("policy_id", f"custom_{int(time.time())}"),
                name=policy_data["name"],
                description=policy_data.get("description", ""),
                mode=OrchestrationMode(policy_data["mode"]),
                optimization_strategy=OptimizationStrategy(policy_data.get("optimization_strategy", "balanced")),
                rules=policy_data.get("rules", []),
                constraints=policy_data.get("constraints", {}),
                priority=policy_data.get("priority", 0),
                active=policy_data.get("active", True)
            )

            self.orchestrator.add_custom_policy(policy)
            return {"success": True, "policy_id": policy.policy_id}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_policies(self) -> List[Dict[str, Any]]:
        """Get active policies."""
        return self.orchestrator.get_active_policies()

    def get_insights(self) -> Dict[str, Any]:
        """Get system insights."""
        system_status = self.get_status()
        intelligence_insights = self.intelligence.get_insights()
        tool_performance = self.orchestrator.self_optimizer.analyze_tool_performance()

        return {
            "system": system_status,
            "intelligence": intelligence_insights,
            "performance": tool_performance,
            "timestamp": datetime.now().isoformat()
        }

    def optimize_system(self) -> Dict[str, Any]:
        """Run system optimization."""
        intelligence_optimizations = self.intelligence.optimize_system()
        self_optimizations = self.orchestrator.self_optimizer.get_optimization_suggestions()

        applied_optimizations = []
        for optimization in self_optimizations:
            if optimization.get("type") == "workflow_optimization":
                workflow_id = optimization.get("workflow_id")
                if workflow_id:
                    applied_optimizations.append({
                        "type": "workflow_optimization",
                        "workflow_id": workflow_id,
                        "applied": True,
                        "details": optimization
                    })

        return {
            "intelligence_optimizations": intelligence_optimizations,
            "self_optimizations": self_optimizations,
            "applied_optimizations": applied_optimizations,
            "optimization_timestamp": datetime.now().isoformat()
        }

    def shutdown(self) -> None:
        """Shutdown the orchestration layer."""
        self.orchestrator.shutdown()
        logger.info("Orchestration Layer shutdown complete")


# Factory function for easy creation
def create_orchestration_layer(tool_system: ToolSystem,
                              intelligence_layer: IntelligenceLayer,
                              config: Optional[Dict[str, Any]] = None) -> OrchestrationLayer:
    """
    Create and initialize an Orchestration Layer.

    Args:
        tool_system: ToolSystem instance
        intelligence_layer: IntelligenceLayer instance
        config: Optional configuration

    Returns:
        Initialized OrchestrationLayer instance
    """
    return OrchestrationLayer(tool_system, intelligence_layer, config)


# Integration function for complete system
def create_complete_system(config: Optional[Dict[str, Any]] = None) -> Tuple[ToolSystem, IntelligenceLayer, OrchestrationLayer]:
    """
    Create a complete system with all phases integrated.

    Args:
        config: Configuration dictionary

    Returns:
        Tuple of (tool_system, intelligence_layer, orchestration_layer)
    """
    if config is None:
        config = {}

    # Create ToolSystem (Phase 1-4)
    tool_system_config = ToolSystemConfig()
    tool_system = ToolSystem(tool_system_config)

    # Create IntelligenceLayer (Phase 5)
    intelligence_config = config.get("intelligence_config", {})
    intelligence_layer = IntelligenceLayer(tool_system, intelligence_config)

    # Enhance tool system with intelligence
    enhanced_system, _ = enhance_tool_system_with_intelligence(tool_system, intelligence_config)

    # Create OrchestrationLayer (Phase 6)
    orchestration_config = config.get("orchestration_config", {})
    orchestration_layer = create_orchestration_layer(
        enhanced_system,
        intelligence_layer,
        orchestration_config
    )

    return enhanced_system, intelligence_layer, orchestration_layer


# CLI interface for orchestration layer
def orchestration_cli():
    """Command-line interface for Orchestration Layer management."""
    import argparse

    parser = argparse.ArgumentParser(description="Orchestration Layer Management CLI")
    parser.add_argument("--orchestrate", type=str, help="Orchestrate an operation (JSON)")
    parser.add_argument("--status", action="store_true", help="Get system status")
    parser.add_argument("--history", action="store_true", help="Get operation history")
    parser.add_argument("--insights", action="store_true", help="Get system insights")
    parser.add_argument("--optimize", action="store_true", help="Run system optimization")
    parser.add_argument("--config", type=str, help="Configuration file")

    args = parser.parse_args()

    # Load configuration
    config = {}
    if args.config:
        try:
            with open(args.config, 'r') as f:
                config = json.load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            return

    # Create complete system
    tool_system, intelligence, orchestration = create_complete_system(config)

    if args.orchestrate:
        try:
            params = json.loads(args.orchestrate)
            result = orchestration.orchestrate(
                params.get("type", "analyze"),
                params.get("parameters", {}),
                params.get("context", {})
            )
            print(json.dumps(result, indent=2))
        except json.JSONDecodeError:
            print("Invalid JSON for operation parameters")
        except Exception as e:
            print(f"Error orchestrating operation: {e}")

    elif args.status:
        status = orchestration.get_status()
        print(json.dumps(status, indent=2))

    elif args.history:
        history = orchestration.get_operation_history()
        print(json.dumps(history, indent=2))

    elif args.insights:
        insights = orchestration.get_insights()
        print(json.dumps(insights, indent=2))

    elif args.optimize:
        optimizations = orchestration.optimize_system()
        print(json.dumps(optimizations, indent=2))

    else:
        parser.print_help()

    orchestration.shutdown()


if __name__ == "__main__":
    orchestration_cli()

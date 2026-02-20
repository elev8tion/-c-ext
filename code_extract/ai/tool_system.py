"""
Phase 4: System Integration & Activation
ToolSystem - Unified tool management system with configuration, health monitoring, and API exposure.
"""

import os
import json
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
import logging

# Import existing components
from .tool_registry import ToolRegistry, ToolCategory
from .tool_migration import ToolIntegrationLayer, get_integration
from .tool_enhancement import (
    ExecutionContext,
    DependencyGraph,
    ToolValidator,
    ToolChain,
    create_enhanced_tool_system
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# yaml is optional
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


class SystemStatus(Enum):
    """System operational status."""
    INITIALIZING = "initializing"
    RUNNING = "running"
    DEGRADED = "degraded"
    STOPPED = "stopped"
    ERROR = "error"


class HealthStatus(Enum):
    """Health status levels."""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class ToolSystemConfig:
    """Configuration for the ToolSystem."""

    # System settings
    auto_discover_tools: bool = True
    auto_migrate_legacy: bool = True
    enable_health_monitoring: bool = True
    enable_execution_history: bool = True
    enable_dependency_tracking: bool = True

    # Performance settings
    max_concurrent_executions: int = 10
    execution_timeout_seconds: int = 30
    cache_results: bool = True
    cache_ttl_seconds: int = 300

    # Storage settings
    config_dir: str = "~/.code-extract"
    config_file: str = "tool_system.yaml"
    history_file: str = "execution_history.json"
    health_file: str = "health_metrics.json"

    # API settings
    enable_rest_api: bool = False
    rest_port: int = 8080
    enable_websocket: bool = False
    websocket_port: int = 8081
    enable_cli: bool = True

    # Security settings
    require_authentication: bool = False
    allowed_origins: List[str] = field(default_factory=lambda: ["*"])
    rate_limit_per_minute: int = 60

    # Module paths for tool discovery
    discovery_modules: List[str] = field(default_factory=lambda: [
        "code_extract.ai.tools",
    ])

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ToolSystemConfig':
        """Create config from dictionary."""
        # Filter to only known fields
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)

    def save(self, filepath: Optional[str] = None) -> None:
        """Save config to file."""
        if filepath is None:
            filepath = self._get_config_path()

        config_dir = os.path.dirname(filepath)
        os.makedirs(config_dir, exist_ok=True)

        data = self.to_dict()
        if HAS_YAML:
            with open(filepath, 'w') as f:
                yaml.dump(data, f, default_flow_style=False)
        else:
            json_path = filepath.replace('.yaml', '.json').replace('.yml', '.json')
            with open(json_path, 'w') as f:
                json.dump(data, f, indent=2)

    def load(self, filepath: Optional[str] = None) -> None:
        """Load config from file."""
        if filepath is None:
            filepath = self._get_config_path()

        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                if HAS_YAML:
                    data = yaml.safe_load(f)
                else:
                    data = json.load(f)
                if data:
                    for key, value in data.items():
                        if hasattr(self, key):
                            setattr(self, key, value)

    def _get_config_path(self) -> str:
        """Get full config file path."""
        config_dir = os.path.expanduser(self.config_dir)
        return os.path.join(config_dir, self.config_file)


@dataclass
class HealthMetric:
    """Health metric data."""
    name: str
    value: float
    unit: str
    status: HealthStatus
    timestamp: datetime = field(default_factory=datetime.now)
    threshold_warning: Optional[float] = None
    threshold_critical: Optional[float] = None

    def is_healthy(self) -> bool:
        """Check if metric is healthy."""
        return self.status == HealthStatus.HEALTHY

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "status": self.status.value,
            "timestamp": self.timestamp.isoformat(),
            "threshold_warning": self.threshold_warning,
            "threshold_critical": self.threshold_critical
        }


class ToolSystemHealth:
    """Health monitoring for the ToolSystem."""

    def __init__(self, config: ToolSystemConfig):
        self.config = config
        self.metrics: Dict[str, HealthMetric] = {}
        self.health_file = os.path.expanduser(
            os.path.join(config.config_dir, config.health_file)
        )
        self._load_metrics()

    def update_metric(self, name: str, value: float, unit: str,
                     warning_threshold: Optional[float] = None,
                     critical_threshold: Optional[float] = None) -> None:
        """Update a health metric."""
        status = self._calculate_status(value, warning_threshold, critical_threshold)

        metric = HealthMetric(
            name=name,
            value=value,
            unit=unit,
            status=status,
            threshold_warning=warning_threshold,
            threshold_critical=critical_threshold
        )

        self.metrics[name] = metric
        self._save_metrics()

    def _calculate_status(self, value: float, warning: Optional[float],
                         critical: Optional[float]) -> HealthStatus:
        """Calculate health status based on thresholds."""
        if critical is not None and value >= critical:
            return HealthStatus.CRITICAL
        elif warning is not None and value >= warning:
            return HealthStatus.WARNING
        else:
            return HealthStatus.HEALTHY

    def get_overall_status(self) -> HealthStatus:
        """Get overall system health status."""
        if not self.metrics:
            return HealthStatus.UNKNOWN

        statuses = [metric.status for metric in self.metrics.values()]

        if HealthStatus.CRITICAL in statuses:
            return HealthStatus.CRITICAL
        elif HealthStatus.WARNING in statuses:
            return HealthStatus.WARNING
        elif all(s == HealthStatus.HEALTHY for s in statuses):
            return HealthStatus.HEALTHY
        else:
            return HealthStatus.UNKNOWN

    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get summary of all metrics."""
        return {
            "overall_status": self.get_overall_status().value,
            "metrics": {name: metric.to_dict() for name, metric in self.metrics.items()},
            "timestamp": datetime.now().isoformat()
        }

    def _save_metrics(self) -> None:
        """Save metrics to file."""
        if not self.config.enable_health_monitoring:
            return

        try:
            os.makedirs(os.path.dirname(self.health_file), exist_ok=True)

            data = {
                "timestamp": datetime.now().isoformat(),
                "metrics": {name: metric.to_dict() for name, metric in self.metrics.items()}
            }

            with open(self.health_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save health metrics: {e}")

    def _load_metrics(self) -> None:
        """Load metrics from file."""
        if os.path.exists(self.health_file):
            try:
                with open(self.health_file, 'r') as f:
                    data = json.load(f)
                    for name, metric_data in data.get("metrics", {}).items():
                        self.metrics[name] = HealthMetric(
                            name=name,
                            value=metric_data["value"],
                            unit=metric_data["unit"],
                            status=HealthStatus(metric_data["status"]),
                            timestamp=datetime.fromisoformat(metric_data["timestamp"]),
                            threshold_warning=metric_data.get("threshold_warning"),
                            threshold_critical=metric_data.get("threshold_critical")
                        )
            except Exception as e:
                logger.warning(f"Failed to load health metrics: {e}")


class ToolSystem:
    """
    Unified Tool System - Phase 4 Integration.

    Integrates all previous phases into a single, operational system with:
    - Configuration management
    - Health monitoring
    - API exposure
    - State management
    """

    def __init__(self, config: Optional[ToolSystemConfig] = None):
        """Initialize the ToolSystem."""
        self.status = SystemStatus.INITIALIZING
        self.start_time = datetime.now()

        # Load or create configuration
        self.config = config or ToolSystemConfig()
        self.config.load()

        # Initialize components
        self._initialize_components()

        # Initialize health monitoring
        self.health = ToolSystemHealth(self.config)

        # State tracking
        self.execution_count = 0
        self.error_count = 0
        self.active_executions = 0
        self._lock = threading.Lock()

        # Update status
        self.status = SystemStatus.RUNNING
        logger.info(f"ToolSystem initialized at {self.start_time}")

    def _initialize_components(self) -> None:
        """Initialize all system components."""
        # Create enhanced system components (uses global registry + integration)
        self.registry, self.integration, self.dependency_graph, self.validator = (
            create_enhanced_tool_system()
        )

        # Create execution context factory
        self.context_factory = lambda: ExecutionContext()

        # Auto-discover and migrate tools if configured
        if self.config.auto_discover_tools:
            self.discover_and_register_tools()

        if self.config.auto_migrate_legacy:
            self.migrate_legacy_tools()

    def discover_and_register_tools(self) -> int:
        """Discover and register tools from the codebase."""
        discovered = self.integration.discover_existing_tools(self.config.discovery_modules)
        logger.info(f"Discovered {len(discovered)} potential tools")

        registered_count = 0
        for tool_info in discovered:
            try:
                self.integration.migrate_tool(tool_info)
                registered_count += 1
            except Exception as e:
                logger.warning(f"Failed to register tool {tool_info.get('name')}: {e}")

        logger.info(f"Registered {registered_count} tools")
        return registered_count

    def migrate_legacy_tools(self) -> Dict[str, Any]:
        """Migrate all discovered legacy tools."""
        migrated = self.integration.migrate_all_discovered(self.config.discovery_modules)

        # Update health metrics
        self.health.update_metric(
            name="legacy_tools_migrated",
            value=len(migrated),
            unit="count",
            warning_threshold=5,
            critical_threshold=10
        )

        return {"migrated_count": len(migrated), "migrated_tools": migrated}

    def execute_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """
        Execute a tool with enhanced capabilities.

        Args:
            tool_name: Name of the tool to execute
            **kwargs: Tool-specific arguments

        Returns:
            Execution result
        """
        with self._lock:
            self.active_executions += 1
            self.execution_count += 1

        context = None
        try:
            # Create execution context
            context = self.context_factory()
            context.update_state({"tool_name": tool_name, "start_time": datetime.now().isoformat()})

            # Validate tool execution
            if self.config.enable_dependency_tracking:
                is_valid, errors = self.validator.validate_execution(tool_name, kwargs, context)
                if not is_valid:
                    raise ValueError(f"Tool validation failed: {errors}")

            # Execute tool
            start_time = time.time()
            result, exec_info = self.registry.execute(tool_name, kwargs, context)
            execution_time = time.time() - start_time

            # Record execution
            context.record_execution(tool_name, result, {
                "parameters": {k: str(v)[:100] for k, v in kwargs.items()},
                "execution_time": execution_time,
                "success": True
            })

            # Update health metrics
            self.health.update_metric(
                name="tool_execution_time",
                value=execution_time,
                unit="seconds",
                warning_threshold=5.0,
                critical_threshold=10.0
            )

            self.health.update_metric(
                name="tool_execution_success_rate",
                value=1.0 - (self.error_count / max(self.execution_count, 1)),
                unit="ratio",
                warning_threshold=0.9,
                critical_threshold=0.8
            )

            logger.info(f"Tool '{tool_name}' executed in {execution_time:.2f}s")

            return {
                "success": True,
                "result": result,
                "execution_time": execution_time,
                "context_id": context.session_id
            }

        except Exception as e:
            with self._lock:
                self.error_count += 1

            # Update error metric
            self.health.update_metric(
                name="tool_execution_errors",
                value=self.error_count,
                unit="count",
                warning_threshold=10,
                critical_threshold=50
            )

            logger.error(f"Tool execution failed: {tool_name} - {e}")

            return {
                "success": False,
                "error": str(e),
                "context_id": context.session_id if context else None
            }

        finally:
            with self._lock:
                self.active_executions -= 1

    def create_tool_chain(self, name: str, tool_steps: List[Dict[str, Any]]) -> ToolChain:
        """
        Create a chain of tools to execute sequentially.

        Args:
            name: Name for the chain
            tool_steps: List of dicts with 'tool', 'arguments', and optional 'store_result_as'

        Returns:
            Configured ToolChain
        """
        chain = ToolChain(name=name)

        for step in tool_steps:
            chain.add_step(
                tool_name=step["tool"],
                arguments=step.get("arguments", {}),
                store_result_as=step.get("store_result_as")
            )

        return chain

    def get_system_info(self) -> Dict[str, Any]:
        """Get comprehensive system information."""
        tools = self.registry.get_all_tools()

        return {
            "status": self.status.value,
            "uptime": (datetime.now() - self.start_time).total_seconds(),
            "start_time": self.start_time.isoformat(),
            "config": self.config.to_dict(),
            "tools": {
                "total": len(tools),
                "by_category": {
                    category.value: len([t for t in tools.values() if t.category == category.value])
                    for category in ToolCategory
                }
            },
            "executions": {
                "total": self.execution_count,
                "errors": self.error_count,
                "active": self.active_executions,
                "success_rate": 1.0 - (self.error_count / max(self.execution_count, 1))
            },
            "health": self.health.get_metrics_summary()
        }

    def save_state(self) -> None:
        """Save system state to disk."""
        # Save configuration
        self.config.save()

        # Save health metrics
        self.health._save_metrics()

        logger.info("ToolSystem state saved")

    def shutdown(self) -> None:
        """Gracefully shutdown the ToolSystem."""
        self.status = SystemStatus.STOPPED

        # Save state
        self.save_state()

        # Clean up resources
        logger.info(f"ToolSystem shutdown after {self.get_system_info()['uptime']:.0f}s uptime")

    def get_openapi_schema(self) -> Dict[str, Any]:
        """Generate OpenAPI schema for all registered tools."""
        return self.registry.generate_openapi_schema()

    def export_configuration(self, filepath: str) -> None:
        """Export system configuration to file."""
        config_data = {
            "system": self.get_system_info(),
            "tools": {
                name: {
                    "name": metadata.name,
                    "description": metadata.description,
                    "category": metadata.category,
                    "parameters": metadata.parameters
                }
                for name, metadata in self.registry.get_all_tools().items()
            },
            "migration_report": self.integration.generate_migration_report(),
            "export_time": datetime.now().isoformat()
        }

        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

        if HAS_YAML:
            with open(filepath, 'w') as f:
                yaml.dump(config_data, f, default_flow_style=False)
        else:
            with open(filepath, 'w') as f:
                json.dump(config_data, f, indent=2)

        logger.info(f"Configuration exported to {filepath}")


# Factory function for easy system creation
def create_tool_system(config: Optional[ToolSystemConfig] = None) -> ToolSystem:
    """
    Create and initialize a ToolSystem.

    Args:
        config: Optional configuration

    Returns:
        Initialized ToolSystem instance
    """
    return ToolSystem(config)


# CLI interface
def cli_main():
    """Command-line interface for ToolSystem management."""
    import argparse

    parser = argparse.ArgumentParser(description="ToolSystem Management CLI")
    parser.add_argument("--init", action="store_true", help="Initialize ToolSystem")
    parser.add_argument("--status", action="store_true", help="Show system status")
    parser.add_argument("--discover", action="store_true", help="Discover and register tools")
    parser.add_argument("--migrate", action="store_true", help="Migrate legacy tools")
    parser.add_argument("--export", type=str, help="Export configuration to file")
    parser.add_argument("--health", action="store_true", help="Show health metrics")
    parser.add_argument("--openapi", action="store_true", help="Generate OpenAPI schema")

    args = parser.parse_args()

    system = create_tool_system()

    if args.status:
        print(json.dumps(system.get_system_info(), indent=2))
    elif args.discover:
        count = system.discover_and_register_tools()
        print(f"Discovered and registered {count} tools")
    elif args.migrate:
        report = system.migrate_legacy_tools()
        print(json.dumps(report, indent=2))
    elif args.export:
        system.export_configuration(args.export)
        print(f"Configuration exported to {args.export}")
    elif args.health:
        print(json.dumps(system.health.get_metrics_summary(), indent=2))
    elif args.openapi:
        print(json.dumps(system.get_openapi_schema(), indent=2))
    elif args.init:
        print(json.dumps(system.get_system_info(), indent=2))
    else:
        parser.print_help()

    system.shutdown()


if __name__ == "__main__":
    cli_main()

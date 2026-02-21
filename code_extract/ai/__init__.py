"""DeepSeek AI integration for context-aware code analysis chat."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum


class AIModel(Enum):
    DEEPSEEK_CHAT = "deepseek-chat"
    DEEPSEEK_CODER = "deepseek-coder"
    DEEPSEEK_REASONER = "deepseek-reasoner"


OPTIMAL_TEMPS: dict[str, float] = {
    "deepseek-chat": 0.7,
    "deepseek-coder": 0.7,
    "deepseek-reasoner": 0.6,
}
TOOL_TEMP_REDUCTION = 0.2


@dataclass
class AIConfig:
    api_key: str = ""
    model: AIModel = AIModel.DEEPSEEK_CODER
    temperature: float = 0.3
    max_tokens: int = 6000
    base_url: str = "https://api.deepseek.com/v1"

    def __post_init__(self):
        if not self.api_key:
            self.api_key = os.getenv("DEEPSEEK_API_KEY", "")

    def get_optimal_temperature(self) -> float:
        """Lookup optimal temperature for the current model."""
        return OPTIMAL_TEMPS.get(self.model.value, 0.7)

    def get_tool_temperature(self) -> float:
        """Lower temperature for precise tool selection."""
        return max(0.1, self.get_optimal_temperature() - TOOL_TEMP_REDUCTION)


# Phase 1: Centralized Tool Registry & Execution Engine
from .tool_registry import ToolRegistry, ToolCategory, ToolMetadata, registry

# Phase 2: Tool Migration & Integration Layer
from .tool_migration import (
    ToolIntegrationLayer, ToolMigrationError,
    create_tool_integration, get_integration,
    get_execute_tool_shim, migrate_tools_from_modules, get_migration_report,
)

# Phase 3: Advanced Tool Capabilities
from .tool_enhancement import (
    ExecutionContext, ToolDependency, DependencyGraph,
    ToolChain, ToolValidator,
    create_enhanced_tool_system, create_context_aware_tool,
)

# Phase 4: System Integration & Activation
from .tool_system import (
    ToolSystem, ToolSystemConfig, ToolSystemHealth,
    SystemStatus, HealthStatus, HealthMetric,
    create_tool_system,
)

# Phase 5: Intelligence Layer
from .tool_intelligence import (
    IntelligenceLayer, ToolRecommender, WorkflowGenerator,
    PredictiveAnalytics, PatternRecognizer, UsageHistory,
    ToolUsage, ToolPattern, ToolRecommendation,
    RecommendationType, PatternType,
    create_intelligence_layer, enhance_tool_system_with_intelligence,
)

# Phase 6: Orchestration Layer
from .tool_orchestration import (
    OrchestrationLayer, AutonomousOrchestrator,
    EventBus, PolicyEngine, ResourceManager, SelfOptimizer,
    OrchestrationMode, OptimizationStrategy, SystemEventType,
    SystemEvent, OrchestrationPolicy, OrchestrationResult,
    create_orchestration_layer, create_complete_system,
)

# Tool Bridge — legacy ↔ ToolSystem integration
from .tool_bridge import (
    register_legacy_tools,
    get_openai_tool_definitions,
    create_integrated_tool_system,
)

# Token utilities
from .token_utils import estimate_tokens, truncate_to_tokens, estimate_messages_tokens, has_tiktoken

# Rate limiting
from .rate_limiter import RateLimiter, get_rate_limiter

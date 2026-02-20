"""
Phase 5: Intelligence Layer
AI-powered tool recommendation, workflow generation, and pattern recognition.
"""

import os
import json
import time
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Set, Union
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict, Counter
import statistics
import logging

# Import Phase 4 components
from .tool_system import ToolSystem, ToolSystemConfig
from .tool_registry import ToolRegistry, ToolCategory, ToolMetadata
from .tool_enhancement import ExecutionContext, ToolChain

logger = logging.getLogger(__name__)

# Optional heavy dependencies
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False


class RecommendationType(Enum):
    """Types of tool recommendations."""
    CONTEXT_BASED = "context_based"
    PATTERN_BASED = "pattern_based"
    COLLABORATIVE = "collaborative"
    SEQUENTIAL = "sequential"
    ALTERNATIVE = "alternative"


class PatternType(Enum):
    """Types of usage patterns."""
    SEQUENCE = "sequence"
    CO_OCCURRENCE = "co_occurrence"
    TEMPORAL = "temporal"
    USER_SPECIFIC = "user_specific"
    CONTEXTUAL = "contextual"


@dataclass
class ToolUsage:
    """Record of a tool usage event."""
    tool_name: str
    user_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    parameters: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    execution_time: float = 0.0
    success: bool = True
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "tool_name": self.tool_name,
            "user_id": self.user_id,
            "context": self.context,
            "parameters": self.parameters,
            "result": self.result,
            "execution_time": self.execution_time,
            "success": self.success,
            "timestamp": self.timestamp.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ToolUsage':
        """Create from dictionary."""
        return cls(
            tool_name=data["tool_name"],
            user_id=data.get("user_id"),
            context=data.get("context"),
            parameters=data.get("parameters"),
            result=data.get("result"),
            execution_time=data.get("execution_time", 0.0),
            success=data.get("success", True),
            timestamp=datetime.fromisoformat(data["timestamp"])
        )


@dataclass
class ToolPattern:
    """A discovered pattern of tool usage."""
    pattern_id: str
    pattern_type: PatternType
    tools: List[str]
    frequency: int
    confidence: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    last_observed: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "pattern_id": self.pattern_id,
            "pattern_type": self.pattern_type.value,
            "tools": self.tools,
            "frequency": self.frequency,
            "confidence": self.confidence,
            "metadata": self.metadata,
            "last_observed": self.last_observed.isoformat()
        }


@dataclass
class ToolRecommendation:
    """A tool recommendation with explanation."""
    tool_name: str
    recommendation_type: RecommendationType
    confidence: float
    explanation: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "tool_name": self.tool_name,
            "recommendation_type": self.recommendation_type.value,
            "confidence": self.confidence,
            "explanation": self.explanation,
            "metadata": self.metadata
        }


class UsageHistory:
    """Manages tool usage history and statistics."""

    def __init__(self, max_history_size: int = 10000):
        self.max_history_size = max_history_size
        self.history: List[ToolUsage] = []
        self._user_history: Dict[str, List[ToolUsage]] = defaultdict(list)
        self._tool_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "count": 0,
            "success_count": 0,
            "total_time": 0.0,
            "users": set(),
            "last_used": None
        })

    def record_usage(self, usage: ToolUsage) -> None:
        """Record a tool usage event."""
        # Add to main history
        self.history.append(usage)

        # Add to user-specific history
        if usage.user_id:
            self._user_history[usage.user_id].append(usage)

        # Update tool statistics
        stats = self._tool_stats[usage.tool_name]
        stats["count"] += 1
        if usage.success:
            stats["success_count"] += 1
        stats["total_time"] += usage.execution_time
        if usage.user_id:
            stats["users"].add(usage.user_id)
        stats["last_used"] = usage.timestamp

        # Trim history if needed
        if len(self.history) > self.max_history_size:
            self._trim_history()

    def _trim_history(self) -> None:
        """Trim history to max size."""
        # Remove oldest entries
        self.history = self.history[-self.max_history_size:]

        # Rebuild user history
        self._user_history.clear()
        for usage in self.history:
            if usage.user_id:
                self._user_history[usage.user_id].append(usage)

    def get_tool_stats(self, tool_name: str) -> Dict[str, Any]:
        """Get statistics for a specific tool."""
        stats = self._tool_stats.get(tool_name, {
            "count": 0,
            "success_count": 0,
            "total_time": 0.0,
            "users": set(),
            "last_used": None
        })

        return {
            "count": stats["count"],
            "success_rate": stats["success_count"] / max(stats["count"], 1),
            "avg_time": stats["total_time"] / max(stats["count"], 1),
            "unique_users": len(stats["users"]),
            "last_used": stats["last_used"].isoformat() if stats["last_used"] else None
        }

    def get_user_history(self, user_id: str, limit: int = 100) -> List[ToolUsage]:
        """Get usage history for a specific user."""
        return self._user_history.get(user_id, [])[-limit:]

    def get_recent_history(self, limit: int = 100) -> List[ToolUsage]:
        """Get recent usage history."""
        return self.history[-limit:]

    def get_popular_tools(self, limit: int = 10) -> List[Tuple[str, int]]:
        """Get most popular tools by usage count."""
        tool_counts = Counter([u.tool_name for u in self.history])
        return tool_counts.most_common(limit)

    def get_tool_sequences(self, window_size: int = 5) -> List[List[str]]:
        """Extract sequences of tools used in temporal windows."""
        sequences = []

        for i in range(len(self.history) - window_size + 1):
            window = self.history[i:i + window_size]
            sequence = [u.tool_name for u in window]
            sequences.append(sequence)

        return sequences

    def save_to_file(self, filepath: str) -> None:
        """Save history to file."""
        data = {
            "history": [usage.to_dict() for usage in self.history],
            "timestamp": datetime.now().isoformat()
        }

        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

    def load_from_file(self, filepath: str) -> None:
        """Load history from file."""
        if not os.path.exists(filepath):
            return

        with open(filepath, 'r') as f:
            data = json.load(f)

        self.history = [ToolUsage.from_dict(u) for u in data.get("history", [])]

        # Rebuild indexes
        self._user_history.clear()
        self._tool_stats.clear()

        for usage in self.history:
            if usage.user_id:
                self._user_history[usage.user_id].append(usage)

            stats = self._tool_stats[usage.tool_name]
            stats["count"] += 1
            if usage.success:
                stats["success_count"] += 1
            stats["total_time"] += usage.execution_time
            if usage.user_id:
                stats["users"].add(usage.user_id)
            stats["last_used"] = usage.timestamp


class PatternRecognizer:
    """Recognizes patterns in tool usage."""

    def __init__(self, min_support: float = 0.1, min_confidence: float = 0.5):
        self.min_support = min_support
        self.min_confidence = min_confidence
        self.patterns: Dict[str, ToolPattern] = {}
        if HAS_NETWORKX:
            self.sequence_graph = nx.DiGraph()
        else:
            self.sequence_graph = None
            self._adjacency: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def discover_patterns(self, history: UsageHistory) -> List[ToolPattern]:
        """Discover patterns in usage history."""
        patterns = []

        # Discover sequential patterns
        seq_patterns = self._discover_sequential_patterns(history)
        patterns.extend(seq_patterns)

        # Discover co-occurrence patterns
        co_patterns = self._discover_co_occurrence_patterns(history)
        patterns.extend(co_patterns)

        # Update internal patterns
        for pattern in patterns:
            self.patterns[pattern.pattern_id] = pattern

        return patterns

    def _discover_sequential_patterns(self, history: UsageHistory) -> List[ToolPattern]:
        """Discover sequential patterns (A -> B -> C)."""
        sequences = history.get_tool_sequences(window_size=3)

        if not sequences:
            return []

        # Count sequence occurrences
        sequence_counts = Counter([tuple(seq) for seq in sequences])
        total_sequences = len(sequences)

        patterns = []
        for seq, count in sequence_counts.items():
            support = count / total_sequences

            if support >= self.min_support:
                pattern_id = f"seq_{hashlib.md5(str(seq).encode()).hexdigest()[:8]}"

                # Calculate confidence (probability of sequence occurring)
                confidence = support

                pattern = ToolPattern(
                    pattern_id=pattern_id,
                    pattern_type=PatternType.SEQUENCE,
                    tools=list(seq),
                    frequency=count,
                    confidence=confidence,
                    metadata={"support": support}
                )
                patterns.append(pattern)

                # Update sequence graph
                for i in range(len(seq) - 1):
                    if self.sequence_graph is not None:
                        self.sequence_graph.add_edge(seq[i], seq[i + 1], weight=count)
                    else:
                        self._adjacency[seq[i]][seq[i + 1]] += count

        return patterns

    def _discover_co_occurrence_patterns(self, history: UsageHistory) -> List[ToolPattern]:
        """Discover tools that are frequently used together."""
        # Get tool usage in windows
        windows = []
        for i in range(0, len(history.history), 3):
            window = history.history[i:i + 3]
            tools_in_window = set(u.tool_name for u in window)
            if len(tools_in_window) > 1:
                windows.append(tools_in_window)

        if not windows:
            return []

        # Count co-occurrences
        co_occurrence_counts = defaultdict(int)
        tool_counts = Counter()

        for window in windows:
            tools = list(window)
            for i in range(len(tools)):
                tool_counts[tools[i]] += 1
                for j in range(i + 1, len(tools)):
                    pair = tuple(sorted([tools[i], tools[j]]))
                    co_occurrence_counts[pair] += 1

        patterns = []
        for (tool_a, tool_b), co_count in co_occurrence_counts.items():
            support = co_count / len(windows)

            if support >= self.min_support:
                # Calculate confidence (P(B|A) and P(A|B))
                confidence_ab = co_count / tool_counts[tool_a]
                confidence_ba = co_count / tool_counts[tool_b]
                confidence = max(confidence_ab, confidence_ba)

                if confidence >= self.min_confidence:
                    pattern_id = f"co_{hashlib.md5(f'{tool_a}_{tool_b}'.encode()).hexdigest()[:8]}"

                    pattern = ToolPattern(
                        pattern_id=pattern_id,
                        pattern_type=PatternType.CO_OCCURRENCE,
                        tools=[tool_a, tool_b],
                        frequency=co_count,
                        confidence=confidence,
                        metadata={
                            "support": support,
                            "confidence_ab": confidence_ab,
                            "confidence_ba": confidence_ba
                        }
                    )
                    patterns.append(pattern)

        return patterns

    def predict_next_tool(self, current_tools: List[str], limit: int = 5) -> List[Tuple[str, float]]:
        """Predict the next tool based on current context."""
        if not current_tools:
            return []

        predictions = []
        last_tool = current_tools[-1]

        if self.sequence_graph is not None:
            # Use networkx graph
            if last_tool in self.sequence_graph:
                successors = list(self.sequence_graph.successors(last_tool))

                for succ in successors:
                    edge_data = self.sequence_graph.get_edge_data(last_tool, succ)
                    weight = edge_data.get('weight', 0)

                    total_outgoing = sum(
                        self.sequence_graph.get_edge_data(last_tool, n).get('weight', 0)
                        for n in self.sequence_graph.successors(last_tool)
                    )

                    probability = weight / max(total_outgoing, 1)
                    predictions.append((succ, probability))
        else:
            # Use simple adjacency dict
            if last_tool in self._adjacency:
                neighbors = self._adjacency[last_tool]
                total_outgoing = sum(neighbors.values())

                for succ, weight in neighbors.items():
                    probability = weight / max(total_outgoing, 1)
                    predictions.append((succ, probability))

        # Sort by probability and limit
        predictions.sort(key=lambda x: x[1], reverse=True)
        return predictions[:limit]

    def get_similar_patterns(self, tools: List[str], limit: int = 5) -> List[ToolPattern]:
        """Find patterns similar to given tools."""
        similar_patterns = []

        for pattern in self.patterns.values():
            # Calculate Jaccard similarity
            pattern_set = set(pattern.tools)
            query_set = set(tools)

            if not pattern_set or not query_set:
                continue

            similarity = len(pattern_set & query_set) / len(pattern_set | query_set)

            if similarity > 0:
                similar_patterns.append((pattern, similarity))

        # Sort by similarity
        similar_patterns.sort(key=lambda x: x[1], reverse=True)
        return [p for p, _ in similar_patterns[:limit]]


class ToolRecommender:
    """AI-powered tool recommendation engine."""

    def __init__(self, tool_system: ToolSystem, history: UsageHistory,
                 pattern_recognizer: PatternRecognizer):
        self.tool_system = tool_system
        self.history = history
        self.pattern_recognizer = pattern_recognizer
        self.tool_names: List[str] = []
        self.tool_to_index: Dict[str, int] = {}
        self.feature_matrix = None

        if HAS_SKLEARN:
            self.vectorizer = TfidfVectorizer(max_features=100)
            self._build_tool_features()
        else:
            self.vectorizer = None

    def _build_tool_features(self) -> None:
        """Build feature vectors for tools based on descriptions."""
        if not HAS_SKLEARN:
            return

        tools = self.tool_system.registry.get_all_tools()

        # Create documents for each tool
        documents = []
        self.tool_names = []

        for name, metadata in tools.items():
            doc = f"{metadata.description} {metadata.category}"
            if metadata.parameters:
                param_text = ' '.join([
                    f"{pname} {pinfo.get('description', '')}"
                    for pname, pinfo in metadata.parameters.items()
                ])
                doc += f" {param_text}"

            documents.append(doc)
            self.tool_names.append(name)

        if documents:
            self.feature_matrix = self.vectorizer.fit_transform(documents)
            self.tool_to_index = {name: i for i, name in enumerate(self.tool_names)}

    def recommend_tools(self, context: Dict[str, Any], limit: int = 5) -> List[ToolRecommendation]:
        """
        Recommend tools based on context.

        Args:
            context: Context dictionary with keys like:
                - current_tools: List of recently used tools
                - user_id: User identifier
                - task_description: Natural language task description
                - parameters: Current parameter values
            limit: Maximum number of recommendations

        Returns:
            List of tool recommendations
        """
        recommendations = []

        # Get context-based recommendations
        context_recs = self._get_context_based_recommendations(context)
        recommendations.extend(context_recs)

        # Get pattern-based recommendations
        pattern_recs = self._get_pattern_based_recommendations(context)
        recommendations.extend(pattern_recs)

        # Get collaborative recommendations
        collab_recs = self._get_collaborative_recommendations(context)
        recommendations.extend(collab_recs)

        # Get alternative recommendations
        alt_recs = self._get_alternative_recommendations(context)
        recommendations.extend(alt_recs)

        # Deduplicate and sort by confidence
        seen = set()
        unique_recs = []

        for rec in recommendations:
            if rec.tool_name not in seen:
                seen.add(rec.tool_name)
                unique_recs.append(rec)

        unique_recs.sort(key=lambda x: x.confidence, reverse=True)
        return unique_recs[:limit]

    def _get_context_based_recommendations(self, context: Dict[str, Any]) -> List[ToolRecommendation]:
        """Get recommendations based on current context."""
        recommendations = []

        # Check for task description
        task_description = context.get("task_description")
        if task_description and HAS_SKLEARN and self.feature_matrix is not None:
            # Find tools with similar descriptions
            task_vector = self.vectorizer.transform([task_description])
            similarities = cosine_similarity(task_vector, self.feature_matrix)[0]

            for i, similarity in enumerate(similarities):
                if similarity > 0.3:  # Threshold
                    tool_name = self.tool_names[i]
                    recommendations.append(
                        ToolRecommendation(
                            tool_name=tool_name,
                            recommendation_type=RecommendationType.CONTEXT_BASED,
                            confidence=float(similarity),
                            explanation=f"Tool description matches your task: '{task_description}'"
                        )
                    )

        # Check for current tools
        current_tools = context.get("current_tools", [])
        if current_tools:
            # Predict next tools based on patterns
            predictions = self.pattern_recognizer.predict_next_tool(current_tools)

            for tool_name, probability in predictions:
                recommendations.append(
                    ToolRecommendation(
                        tool_name=tool_name,
                        recommendation_type=RecommendationType.SEQUENTIAL,
                        confidence=probability,
                        explanation=f"Frequently used after: {', '.join(current_tools[-2:])}"
                    )
                )

        return recommendations

    def _get_pattern_based_recommendations(self, context: Dict[str, Any]) -> List[ToolRecommendation]:
        """Get recommendations based on usage patterns."""
        recommendations = []
        current_tools = context.get("current_tools", [])

        if current_tools:
            # Find similar patterns
            similar_patterns = self.pattern_recognizer.get_similar_patterns(current_tools)

            for pattern in similar_patterns:
                # Recommend tools from the pattern that aren't in current tools
                for tool_name in pattern.tools:
                    if tool_name not in current_tools:
                        recommendations.append(
                            ToolRecommendation(
                                tool_name=tool_name,
                                recommendation_type=RecommendationType.PATTERN_BASED,
                                confidence=pattern.confidence,
                                explanation=f"Part of pattern '{pattern.pattern_id}' (confidence: {pattern.confidence:.2f})"
                            )
                        )

        return recommendations

    def _get_collaborative_recommendations(self, context: Dict[str, Any]) -> List[ToolRecommendation]:
        """Get recommendations based on what similar users use."""
        recommendations = []
        user_id = context.get("user_id")

        if not user_id:
            return recommendations

        # Get current user's tool usage
        user_history = self.history.get_user_history(user_id)
        user_tools = set([u.tool_name for u in user_history])

        if not user_tools:
            return recommendations

        # Find users with similar tool usage
        all_users = list(self.history._user_history.keys())
        user_similarities = []

        for other_user in all_users:
            if other_user == user_id:
                continue

            other_history = self.history.get_user_history(other_user)
            other_tools = set([u.tool_name for u in other_history])

            if not other_tools:
                continue

            # Calculate Jaccard similarity
            similarity = len(user_tools & other_tools) / len(user_tools | other_tools)
            user_similarities.append((other_user, similarity))

        # Sort by similarity
        user_similarities.sort(key=lambda x: x[1], reverse=True)

        # Get tools from similar users
        for other_user, similarity in user_similarities[:3]:  # Top 3 similar users
            if similarity > 0.3:
                other_history = self.history.get_user_history(other_user)
                other_tools = set([u.tool_name for u in other_history])

                # Recommend tools the other user uses that current user doesn't
                for tool_name in other_tools - user_tools:
                    recommendations.append(
                        ToolRecommendation(
                            tool_name=tool_name,
                            recommendation_type=RecommendationType.COLLABORATIVE,
                            confidence=similarity,
                            explanation=f"Used by similar user '{other_user}' (similarity: {similarity:.2f})"
                        )
                    )

        return recommendations

    def _get_alternative_recommendations(self, context: Dict[str, Any]) -> List[ToolRecommendation]:
        """Get alternative tools that perform similar functions."""
        recommendations = []
        current_tools = context.get("current_tools", [])

        if not current_tools:
            return recommendations

        # For each current tool, find alternatives
        for tool_name in current_tools[-3:]:  # Last 3 tools
            # Get tool metadata
            tools = self.tool_system.registry.get_all_tools()
            if tool_name not in tools:
                continue

            current_metadata = tools[tool_name]

            # Find tools with similar categories and descriptions
            for other_name, other_metadata in tools.items():
                if other_name == tool_name:
                    continue

                # Calculate similarity
                similarity = 0.0

                # Category match
                if current_metadata.category == other_metadata.category:
                    similarity += 0.3

                # Description similarity
                if HAS_SKLEARN and self.feature_matrix is not None:
                    current_idx = self.tool_to_index.get(tool_name)
                    other_idx = self.tool_to_index.get(other_name)

                    if current_idx is not None and other_idx is not None:
                        desc_similarity = cosine_similarity(
                            self.feature_matrix[current_idx:current_idx+1],
                            self.feature_matrix[other_idx:other_idx+1]
                        )[0][0]
                        similarity += desc_similarity * 0.7

                if similarity > 0.5:
                    recommendations.append(
                        ToolRecommendation(
                            tool_name=other_name,
                            recommendation_type=RecommendationType.ALTERNATIVE,
                            confidence=similarity,
                            explanation=f"Alternative to '{tool_name}' with similar functionality"
                        )
                    )

        return recommendations

    def generate_workflow(self, goal: str, max_steps: int = 10) -> Dict[str, Any]:
        """
        Generate a workflow (sequence of tools) to achieve a goal.

        Args:
            goal: Natural language description of the goal
            max_steps: Maximum number of steps in the workflow

        Returns:
            Workflow specification
        """
        if not HAS_SKLEARN or not HAS_NUMPY or self.feature_matrix is None:
            return {"error": "Tool features not initialized (sklearn/numpy required)"}

        # First, find tools relevant to the goal
        goal_vector = self.vectorizer.transform([goal])
        similarities = cosine_similarity(goal_vector, self.feature_matrix)[0]

        # Get top relevant tools
        relevant_indices = np.argsort(similarities)[-5:][::-1]
        relevant_tools = [self.tool_names[i] for i in relevant_indices if similarities[i] > 0.3]

        if not relevant_tools:
            return {"error": "No relevant tools found for the goal"}

        # Build workflow using patterns
        workflow = []
        current_tool = relevant_tools[0]
        visited = set()

        for step in range(max_steps):
            if current_tool in visited:
                break

            workflow.append(current_tool)
            visited.add(current_tool)

            # Predict next tool
            predictions = self.pattern_recognizer.predict_next_tool([current_tool])
            if not predictions:
                break

            # Choose the most relevant next tool
            next_tool = None
            for pred_tool, probability in predictions:
                if pred_tool not in visited and pred_tool in relevant_tools:
                    next_tool = pred_tool
                    break

            if not next_tool:
                # Choose any next tool
                for pred_tool, probability in predictions:
                    if pred_tool not in visited:
                        next_tool = pred_tool
                        break

            if not next_tool:
                break

            current_tool = next_tool

        avg_confidence = float(np.mean([
            similarities[self.tool_to_index.get(t, 0)]
            for t in workflow if t in self.tool_to_index
        ])) if workflow else 0.0

        return {
            "goal": goal,
            "workflow": workflow,
            "steps": len(workflow),
            "confidence": avg_confidence,
            "explanation": f"Generated workflow to achieve: {goal}"
        }


class WorkflowGenerator:
    """Generates and manages automated workflows."""

    def __init__(self, tool_system: ToolSystem, recommender: ToolRecommender):
        self.tool_system = tool_system
        self.recommender = recommender
        self.workflows: Dict[str, Dict[str, Any]] = {}

    def create_workflow(self, name: str, tool_sequence: List[str],
                       parameters: Optional[Dict[str, Any]] = None) -> str:
        """
        Create a named workflow from a sequence of tools.

        Args:
            name: Name of the workflow
            tool_sequence: List of tool names in execution order
            parameters: Optional default parameters

        Returns:
            Workflow ID
        """
        workflow_id = f"workflow_{hashlib.md5(name.encode()).hexdigest()[:8]}"

        self.workflows[workflow_id] = {
            "id": workflow_id,
            "name": name,
            "tool_sequence": tool_sequence,
            "parameters": parameters or {},
            "created_at": datetime.now().isoformat(),
            "execution_count": 0,
            "success_count": 0
        }

        logger.info(f"Created workflow '{name}' with {len(tool_sequence)} tools")
        return workflow_id

    def execute_workflow(self, workflow_id: str,
                        context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute a workflow.

        Args:
            workflow_id: ID of the workflow to execute
            context: Optional execution context

        Returns:
            Execution results
        """
        if workflow_id not in self.workflows:
            return {"error": f"Workflow '{workflow_id}' not found"}

        workflow = self.workflows[workflow_id]
        tool_sequence = workflow["tool_sequence"]

        # Update execution count
        workflow["execution_count"] += 1

        # Execute tools in sequence
        results = []
        execution_context = context or {}

        for i, tool_name in enumerate(tool_sequence):
            try:
                # Merge workflow parameters with context
                tool_params = workflow["parameters"].get(tool_name, {})
                tool_params.update(execution_context.get(tool_name, {}))

                # Execute tool
                result = self.tool_system.execute_tool(tool_name, **tool_params)
                results.append({
                    "step": i + 1,
                    "tool": tool_name,
                    "result": result,
                    "success": result.get("success", False)
                })

                # Update context with result for next tools
                if result.get("success") and result.get("result"):
                    execution_context[f"result_{tool_name}"] = result["result"]

            except Exception as e:
                results.append({
                    "step": i + 1,
                    "tool": tool_name,
                    "error": str(e),
                    "success": False
                })
                break

        # Check if workflow succeeded
        success = all(r.get("success", False) for r in results)
        if success:
            workflow["success_count"] += 1

        return {
            "workflow_id": workflow_id,
            "workflow_name": workflow["name"],
            "success": success,
            "steps_executed": len(results),
            "results": results,
            "success_rate": workflow["success_count"] / max(workflow["execution_count"], 1)
        }

    def optimize_workflow(self, workflow_id: str) -> Dict[str, Any]:
        """
        Optimize a workflow based on execution patterns.

        Args:
            workflow_id: ID of the workflow to optimize

        Returns:
            Optimization suggestions
        """
        if workflow_id not in self.workflows:
            return {"error": f"Workflow '{workflow_id}' not found"}

        workflow = self.workflows[workflow_id]
        tool_sequence = workflow["tool_sequence"]

        suggestions = []

        # Check for redundant tools
        seen_tools = set()
        for i, tool_name in enumerate(tool_sequence):
            if tool_name in seen_tools:
                suggestions.append({
                    "type": "redundancy",
                    "step": i + 1,
                    "tool": tool_name,
                    "suggestion": f"Tool '{tool_name}' appears multiple times in the workflow",
                    "confidence": 0.8
                })
            seen_tools.add(tool_name)

        # Check for better tool sequences based on patterns
        for i in range(len(tool_sequence) - 1):
            current_tool = tool_sequence[i]
            next_tool = tool_sequence[i + 1]

            # Check if this sequence is common
            patterns = self.recommender.pattern_recognizer.get_similar_patterns([current_tool, next_tool])

            if not patterns:
                suggestions.append({
                    "type": "sequence",
                    "step": i + 1,
                    "tools": [current_tool, next_tool],
                    "suggestion": f"Sequence '{current_tool} -> {next_tool}' is uncommon",
                    "confidence": 0.6
                })

        # Generate alternative workflows
        alternative_sequences = []
        if tool_sequence:
            # Use pattern recognizer to suggest alternatives
            for i in range(min(3, len(tool_sequence))):
                current = tool_sequence[:i+1]
                predictions = self.recommender.pattern_recognizer.predict_next_tool(current)

                for alt_tool, probability in predictions:
                    if alt_tool not in tool_sequence and probability > 0.7:
                        alternative_sequences.append({
                            "position": i + 1,
                            "alternative": alt_tool,
                            "probability": probability,
                            "suggestion": f"Consider adding '{alt_tool}' after step {i + 1}"
                        })

        return {
            "workflow_id": workflow_id,
            "original_steps": len(tool_sequence),
            "suggestions": suggestions,
            "alternatives": alternative_sequences,
            "optimization_score": 1.0 - (len(suggestions) / max(len(tool_sequence), 1))
        }

    def get_workflow_stats(self) -> Dict[str, Any]:
        """Get statistics for all workflows."""
        total_executions = sum(w["execution_count"] for w in self.workflows.values())
        total_success = sum(w["success_count"] for w in self.workflows.values())

        return {
            "total_workflows": len(self.workflows),
            "total_executions": total_executions,
            "total_success": total_success,
            "overall_success_rate": total_success / max(total_executions, 1),
            "workflows": [
                {
                    "id": w["id"],
                    "name": w["name"],
                    "steps": len(w["tool_sequence"]),
                    "executions": w["execution_count"],
                    "success_rate": w["success_count"] / max(w["execution_count"], 1)
                }
                for w in self.workflows.values()
            ]
        }


class PredictiveAnalytics:
    """Predictive analytics for tool usage forecasting."""

    def __init__(self, history: UsageHistory, pattern_recognizer: PatternRecognizer):
        self.history = history
        self.pattern_recognizer = pattern_recognizer

    def forecast_tool_demand(self, horizon_days: int = 7) -> Dict[str, Any]:
        """
        Forecast tool usage demand.

        Args:
            horizon_days: Forecast horizon in days

        Returns:
            Demand forecast
        """
        # Get historical usage by day
        daily_usage = defaultdict(lambda: defaultdict(int))

        for usage in self.history.history:
            date = usage.timestamp.date()
            daily_usage[date][usage.tool_name] += 1

        if not daily_usage:
            return {"error": "Insufficient historical data"}

        # Simple forecasting: average of last 7 days
        dates = sorted(daily_usage.keys())
        recent_dates = dates[-7:] if len(dates) >= 7 else dates

        # Calculate averages
        tool_forecasts = {}
        for date in recent_dates:
            for tool_name, count in daily_usage[date].items():
                if tool_name not in tool_forecasts:
                    tool_forecasts[tool_name] = []
                tool_forecasts[tool_name].append(count)

        # Generate forecast
        forecast = {}
        for tool_name, counts in tool_forecasts.items():
            avg_daily = sum(counts) / len(counts)
            forecast[tool_name] = {
                "historical_avg": avg_daily,
                "forecast_daily": avg_daily,  # Simple forecast
                "trend": "stable",  # Could be calculated from slope
                "confidence": min(0.9, len(counts) / 7)  # More data = more confidence
            }

        return {
            "horizon_days": horizon_days,
            "forecast_generated": datetime.now().isoformat(),
            "tools_forecasted": len(forecast),
            "forecasts": forecast
        }

    def identify_bottlenecks(self) -> List[Dict[str, Any]]:
        """Identify potential bottlenecks in tool usage."""
        bottlenecks = []

        # Get tool statistics
        all_tools = set([u.tool_name for u in self.history.history])

        for tool_name in all_tools:
            stats = self.history.get_tool_stats(tool_name)

            # Check for high error rate
            if stats["success_rate"] < 0.8:  # 80% success threshold
                bottlenecks.append({
                    "tool": tool_name,
                    "type": "high_error_rate",
                    "metric": "success_rate",
                    "value": stats["success_rate"],
                    "threshold": 0.8,
                    "severity": "high" if stats["success_rate"] < 0.6 else "medium",
                    "suggestion": "Investigate frequent failures and consider adding validation or error handling"
                })

            # Check for slow execution
            if stats["avg_time"] > 5.0:  # 5 second threshold
                bottlenecks.append({
                    "tool": tool_name,
                    "type": "slow_execution",
                    "metric": "avg_time",
                    "value": stats["avg_time"],
                    "threshold": 5.0,
                    "severity": "high" if stats["avg_time"] > 10.0 else "medium",
                    "suggestion": "Optimize tool execution or add caching"
                })

            # Check for low usage (potentially dead code)
            if stats["count"] < 5 and len(self.history.history) > 100:
                bottlenecks.append({
                    "tool": tool_name,
                    "type": "low_usage",
                    "metric": "usage_count",
                    "value": stats["count"],
                    "threshold": 5,
                    "severity": "low",
                    "suggestion": "Consider deprecating or removing rarely used tool"
                })

        # Sort by severity
        severity_order = {"high": 3, "medium": 2, "low": 1}
        bottlenecks.sort(key=lambda x: severity_order.get(x["severity"], 0), reverse=True)

        return bottlenecks

    def predict_user_needs(self, user_id: str, time_window_hours: int = 24) -> Dict[str, Any]:
        """
        Predict what tools a user will need in the near future.

        Args:
            user_id: User identifier
            time_window_hours: Prediction time window

        Returns:
            Predicted tool needs
        """
        user_history = self.history.get_user_history(user_id)

        if not user_history:
            return {"error": "No user history available"}

        # Analyze user's typical patterns
        user_tools = [u.tool_name for u in user_history]
        tool_counts = Counter(user_tools)

        # Get time-based patterns
        hourly_patterns = defaultdict(lambda: defaultdict(int))
        for usage in user_history:
            hour = usage.timestamp.hour
            hourly_patterns[hour][usage.tool_name] += 1

        # Predict based on current time
        current_hour = datetime.now().hour
        current_pattern = hourly_patterns.get(current_hour, {})

        # Also consider overall popularity
        predictions = []

        for tool_name, count in tool_counts.items():
            # Base probability from overall usage
            base_prob = count / len(user_history)

            # Boost if used at this hour
            hour_boost = current_pattern.get(tool_name, 0) / max(sum(current_pattern.values()), 1)

            # Final probability
            probability = base_prob * 0.7 + hour_boost * 0.3

            if probability > 0.1:  # Threshold
                predictions.append({
                    "tool": tool_name,
                    "probability": probability,
                    "reason": f"Frequently used by this user (used {count} times)"
                })

        # Sort by probability
        predictions.sort(key=lambda x: x["probability"], reverse=True)

        return {
            "user_id": user_id,
            "time_window_hours": time_window_hours,
            "prediction_time": datetime.now().isoformat(),
            "predictions": predictions[:10],  # Top 10
            "confidence": min(0.9, len(user_history) / 100)  # More history = more confidence
        }


class IntelligenceLayer:
    """
    Main Intelligence Layer - Integrates all Phase 5 components.

    Provides:
    1. Tool recommendations based on context and patterns
    2. Automated workflow generation
    3. Usage pattern recognition
    4. Predictive analytics
    5. Workflow optimization
    """

    def __init__(self, tool_system: ToolSystem, config: Optional[Dict[str, Any]] = None):
        """Initialize the Intelligence Layer."""
        self.tool_system = tool_system
        self.config = config or {}

        # Initialize components
        self.history = UsageHistory(
            max_history_size=self.config.get("max_history_size", 10000)
        )

        self.pattern_recognizer = PatternRecognizer(
            min_support=self.config.get("min_support", 0.1),
            min_confidence=self.config.get("min_confidence", 0.5)
        )

        self.recommender = ToolRecommender(
            tool_system=tool_system,
            history=self.history,
            pattern_recognizer=self.pattern_recognizer
        )

        self.workflow_generator = WorkflowGenerator(
            tool_system=tool_system,
            recommender=self.recommender
        )

        self.predictive_analytics = PredictiveAnalytics(
            history=self.history,
            pattern_recognizer=self.pattern_recognizer
        )

        # Load existing history if available
        history_file = self.config.get("history_file")
        if history_file and os.path.exists(history_file):
            self.history.load_from_file(history_file)

        # Discover initial patterns
        self._discover_initial_patterns()

        logger.info("Intelligence Layer initialized")

    def _discover_initial_patterns(self) -> None:
        """Discover initial patterns from existing history."""
        if self.history.history:
            patterns = self.pattern_recognizer.discover_patterns(self.history)
            logger.info(f"Discovered {len(patterns)} initial patterns")

    def record_tool_usage(self, tool_name: str, user_id: Optional[str] = None,
                         context: Optional[Dict[str, Any]] = None,
                         parameters: Optional[Dict[str, Any]] = None,
                         result: Optional[Dict[str, Any]] = None,
                         execution_time: float = 0.0,
                         success: bool = True) -> None:
        """Record a tool usage event."""
        usage = ToolUsage(
            tool_name=tool_name,
            user_id=user_id,
            context=context,
            parameters=parameters,
            result=result,
            execution_time=execution_time,
            success=success
        )

        self.history.record_usage(usage)

        # Periodically rediscover patterns
        if len(self.history.history) % 100 == 0:
            self.pattern_recognizer.discover_patterns(self.history)

    def get_recommendations(self, context: Dict[str, Any], limit: int = 5) -> Dict[str, Any]:
        """
        Get tool recommendations for the given context.

        Args:
            context: Context dictionary
            limit: Maximum number of recommendations

        Returns:
            Recommendations with explanations
        """
        recommendations = self.recommender.recommend_tools(context, limit)

        return {
            "context": context,
            "recommendations": [rec.to_dict() for rec in recommendations],
            "generated_at": datetime.now().isoformat()
        }

    def generate_workflow_for_goal(self, goal: str, user_id: Optional[str] = None,
                                  max_steps: int = 10) -> Dict[str, Any]:
        """
        Generate a workflow to achieve a specific goal.

        Args:
            goal: Natural language description of the goal
            user_id: Optional user identifier for personalization
            max_steps: Maximum number of steps

        Returns:
            Generated workflow
        """
        # Add user context if available
        context = {"task_description": goal}
        if user_id:
            context["user_id"] = user_id
            # Add user's recent tools to context
            user_history = self.history.get_user_history(user_id, limit=5)
            if user_history:
                context["current_tools"] = [u.tool_name for u in user_history]

        # Generate workflow
        workflow_result = self.recommender.generate_workflow(goal, max_steps)

        # Create named workflow if successful
        if "workflow" in workflow_result and workflow_result["workflow"]:
            workflow_name = f"Auto-generated: {goal[:50]}..."
            workflow_id = self.workflow_generator.create_workflow(
                name=workflow_name,
                tool_sequence=workflow_result["workflow"]
            )

            workflow_result["workflow_id"] = workflow_id
            workflow_result["workflow_name"] = workflow_name

        return workflow_result

    def execute_smart_workflow(self, goal: str, user_id: Optional[str] = None,
                              parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Generate and execute a workflow for a goal in one step.

        Args:
            goal: Goal description
            user_id: Optional user identifier
            parameters: Optional execution parameters

        Returns:
            Execution results
        """
        # Generate workflow
        workflow_result = self.generate_workflow_for_goal(goal, user_id)

        if "error" in workflow_result:
            return workflow_result

        if "workflow_id" not in workflow_result:
            return {"error": "Failed to create workflow"}

        # Execute workflow
        execution_result = self.workflow_generator.execute_workflow(
            workflow_id=workflow_result["workflow_id"],
            context=parameters
        )

        # Record the execution
        if user_id and "results" in execution_result:
            for step_result in execution_result["results"]:
                if step_result.get("success"):
                    self.record_tool_usage(
                        tool_name=step_result["tool"],
                        user_id=user_id,
                        execution_time=step_result.get("result", {}).get("execution_time", 0.0),
                        success=True
                    )

        return {
            "goal": goal,
            "workflow_generation": workflow_result,
            "execution": execution_result
        }

    def get_insights(self) -> Dict[str, Any]:
        """Get insights and analytics about tool usage."""
        # Get popular tools
        popular_tools = self.history.get_popular_tools(limit=10)

        # Get bottlenecks
        bottlenecks = self.predictive_analytics.identify_bottlenecks()

        # Get pattern insights
        patterns = list(self.pattern_recognizer.patterns.values())
        patterns.sort(key=lambda x: x.frequency, reverse=True)

        # Get workflow stats
        workflow_stats = self.workflow_generator.get_workflow_stats()

        return {
            "popular_tools": [
                {"tool": tool, "count": count}
                for tool, count in popular_tools
            ],
            "bottlenecks": bottlenecks[:5],  # Top 5 bottlenecks
            "common_patterns": [
                {
                    "type": p.pattern_type.value,
                    "tools": p.tools,
                    "frequency": p.frequency,
                    "confidence": p.confidence
                }
                for p in patterns[:5]  # Top 5 patterns
            ],
            "workflow_analytics": workflow_stats,
            "total_tool_executions": len(self.history.history),
            "unique_users": len(self.history._user_history),
            "unique_tools": len(self.history._tool_stats),
            "generated_at": datetime.now().isoformat()
        }

    def optimize_system(self) -> Dict[str, Any]:
        """Run system optimization and return suggestions."""
        optimizations = []

        # Optimize all workflows
        for workflow_id in self.workflow_generator.workflows.keys():
            optimization = self.workflow_generator.optimize_workflow(workflow_id)
            if optimization.get("suggestions") or optimization.get("alternatives"):
                optimizations.append({
                    "workflow_id": workflow_id,
                    "optimization": optimization
                })

        # Get demand forecast
        forecast = self.predictive_analytics.forecast_tool_demand()

        # Get bottlenecks
        bottlenecks = self.predictive_analytics.identify_bottlenecks()

        return {
            "workflow_optimizations": optimizations,
            "demand_forecast": forecast,
            "bottlenecks": bottlenecks,
            "optimization_score": self._calculate_optimization_score(optimizations, bottlenecks),
            "generated_at": datetime.now().isoformat()
        }

    def _calculate_optimization_score(self, optimizations: List[Dict[str, Any]],
                                     bottlenecks: List[Dict[str, Any]]) -> float:
        """Calculate an overall optimization score."""
        if not optimizations and not bottlenecks:
            return 1.0

        # Start with perfect score
        score = 1.0

        # Deduct for each optimization suggestion
        for opt in optimizations:
            suggestions = opt["optimization"].get("suggestions", [])
            score -= len(suggestions) * 0.05

        # Deduct for bottlenecks
        severity_weights = {"high": 0.1, "medium": 0.05, "low": 0.02}
        for bottleneck in bottlenecks:
            score -= severity_weights.get(bottleneck.get("severity", "low"), 0.02)

        return max(0.0, min(1.0, score))

    def save_state(self, filepath: Optional[str] = None) -> None:
        """Save intelligence layer state to file."""
        if filepath is None:
            filepath = self.config.get("state_file", "intelligence_state.json")

        # Save history
        self.history.save_to_file(filepath)

        # Save patterns
        patterns_file = filepath.replace(".json", "_patterns.json")
        patterns_data = {
            "patterns": [p.to_dict() for p in self.pattern_recognizer.patterns.values()],
            "generated_at": datetime.now().isoformat()
        }

        with open(patterns_file, 'w') as f:
            json.dump(patterns_data, f, indent=2)

        logger.info(f"Intelligence Layer state saved to {filepath}")

    def load_state(self, filepath: Optional[str] = None) -> None:
        """Load intelligence layer state from file."""
        if filepath is None:
            filepath = self.config.get("state_file", "intelligence_state.json")

        # Load history
        self.history.load_from_file(filepath)

        # Load patterns
        patterns_file = filepath.replace(".json", "_patterns.json")
        if os.path.exists(patterns_file):
            with open(patterns_file, 'r') as f:
                patterns_data = json.load(f)

            for pattern_dict in patterns_data.get("patterns", []):
                pattern = ToolPattern(
                    pattern_id=pattern_dict["pattern_id"],
                    pattern_type=PatternType(pattern_dict["pattern_type"]),
                    tools=pattern_dict["tools"],
                    frequency=pattern_dict["frequency"],
                    confidence=pattern_dict["confidence"],
                    metadata=pattern_dict.get("metadata", {}),
                    last_observed=datetime.fromisoformat(pattern_dict["last_observed"])
                )
                self.pattern_recognizer.patterns[pattern.pattern_id] = pattern

        logger.info(f"Intelligence Layer state loaded from {filepath}")


# Factory function for easy creation
def create_intelligence_layer(tool_system: ToolSystem,
                             config: Optional[Dict[str, Any]] = None) -> IntelligenceLayer:
    """
    Create and initialize an Intelligence Layer.

    Args:
        tool_system: ToolSystem instance
        config: Optional configuration

    Returns:
        Initialized IntelligenceLayer instance
    """
    return IntelligenceLayer(tool_system, config)


# Integration with ToolSystem
def enhance_tool_system_with_intelligence(tool_system: ToolSystem,
                                         config: Optional[Dict[str, Any]] = None) -> Tuple[ToolSystem, IntelligenceLayer]:
    """
    Enhance an existing ToolSystem with intelligence capabilities.

    Args:
        tool_system: Existing ToolSystem
        config: Intelligence configuration

    Returns:
        Tuple of (enhanced_tool_system, intelligence_layer)
    """
    # Create intelligence layer
    intelligence = create_intelligence_layer(tool_system, config)

    # Wrap tool execution to record usage
    original_execute = tool_system.execute_tool

    def enhanced_execute(tool_name: str, **kwargs):
        # Record usage before execution
        user_id = kwargs.pop("_user_id", None)
        context = kwargs.pop("_context", None)

        start_time = time.time()
        result = original_execute(tool_name, **kwargs)
        execution_time = time.time() - start_time

        # Record usage
        intelligence.record_tool_usage(
            tool_name=tool_name,
            user_id=user_id,
            context=context,
            parameters=kwargs,
            result=result,
            execution_time=execution_time,
            success=result.get("success", False)
        )

        return result

    # Replace execute method
    tool_system.execute_tool = enhanced_execute

    # Add intelligence methods to tool system
    tool_system.get_recommendations = intelligence.get_recommendations
    tool_system.generate_workflow = intelligence.generate_workflow_for_goal
    tool_system.execute_smart_workflow = intelligence.execute_smart_workflow
    tool_system.get_insights = intelligence.get_insights
    tool_system.optimize_system = intelligence.optimize_system

    return tool_system, intelligence


# CLI interface for intelligence layer
def intelligence_cli():
    """Command-line interface for Intelligence Layer management."""
    import argparse

    parser = argparse.ArgumentParser(description="Intelligence Layer Management CLI")
    parser.add_argument("--recommend", type=str, help="Get recommendations for a task description")
    parser.add_argument("--generate-workflow", type=str, help="Generate workflow for a goal")
    parser.add_argument("--insights", action="store_true", help="Show usage insights")
    parser.add_argument("--bottlenecks", action="store_true", help="Show bottlenecks")
    parser.add_argument("--forecast", action="store_true", help="Show demand forecast")

    args = parser.parse_args()

    from .tool_system import create_tool_system
    system = create_tool_system()
    intelligence = create_intelligence_layer(system)

    if args.recommend:
        result = intelligence.get_recommendations({"task_description": args.recommend})
        print(json.dumps(result, indent=2))
    elif args.generate_workflow:
        result = intelligence.generate_workflow_for_goal(args.generate_workflow)
        print(json.dumps(result, indent=2))
    elif args.insights:
        result = intelligence.get_insights()
        print(json.dumps(result, indent=2))
    elif args.bottlenecks:
        result = intelligence.predictive_analytics.identify_bottlenecks()
        print(json.dumps(result, indent=2))
    elif args.forecast:
        result = intelligence.predictive_analytics.forecast_tool_demand()
        print(json.dumps(result, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    intelligence_cli()

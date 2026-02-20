"""
Centralized tool registry and execution engine.
Enables dynamic tool discovery, registration, and execution.
"""

from typing import Dict, Any, Callable, Optional, List, Tuple
from datetime import datetime
import inspect
import functools
from dataclasses import dataclass
from enum import Enum


@dataclass
class ToolMetadata:
    """Metadata for registered tools."""
    name: str
    function: Callable
    description: str
    parameters: Dict[str, Dict[str, Any]]
    required_params: List[str]
    returns: Dict[str, Any]
    category: str = "general"
    version: str = "1.0"
    requires_context: bool = False


class ToolCategory(Enum):
    """Categories for organizing tools."""
    GENERAL = "general"
    CODE_ANALYSIS = "code_analysis"
    UI_OPERATIONS = "ui_operations"
    DATA_QUERIES = "data_queries"
    WORKFLOW = "workflows"
    BOILERPLATE = "boilerplate"
    MIGRATION = "migration"
    EXTRACTION = "extraction"


class ToolRegistry:
    """
    Central registry for all available tools.
    Enables dynamic discovery, registration, and execution.
    """

    def __init__(self):
        self._tools: Dict[str, ToolMetadata] = {}
        self._categories: Dict[ToolCategory, List[str]] = {
            cat: [] for cat in ToolCategory
        }
        self._execution_history: List[Dict[str, Any]] = []

    def register(
        self,
        name: str,
        description: str,
        category: ToolCategory = ToolCategory.GENERAL,
        requires_context: bool = False
    ):
        """
        Decorator to register a tool function.

        Args:
            name: Unique tool identifier
            description: Human-readable description
            category: Tool category for organization
            requires_context: Whether tool needs execution context
        """
        def decorator(func: Callable):
            # Extract parameter information
            sig = inspect.signature(func)
            parameters = {}
            required_params = []

            for param_name, param in sig.parameters.items():
                if param_name in ['self', 'cls', 'context']:
                    continue

                param_info = {
                    "type": str(param.annotation) if param.annotation != inspect.Parameter.empty else "Any",
                    "description": "",
                    "default": param.default if param.default != inspect.Parameter.empty else None
                }

                parameters[param_name] = param_info

                if param.default == inspect.Parameter.empty and param_name not in ['self', 'cls']:
                    required_params.append(param_name)

            # Determine return type
            return_annotation = sig.return_annotation
            returns = {
                "type": str(return_annotation) if return_annotation != inspect.Signature.empty else "Any",
                "description": ""
            }

            # Create metadata
            metadata = ToolMetadata(
                name=name,
                function=func,
                description=description,
                parameters=parameters,
                required_params=required_params,
                returns=returns,
                category=category.value,
                requires_context=requires_context
            )

            # Register tool
            self._tools[name] = metadata
            self._categories[category].append(name)

            # Wrap function to maintain original behavior
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)

            return wrapper

        return decorator

    def get_tool(self, name: str) -> Optional[ToolMetadata]:
        """Get tool metadata by name."""
        return self._tools.get(name)

    def get_all_tools(self) -> Dict[str, ToolMetadata]:
        """Get all registered tools."""
        return self._tools.copy()

    def get_tools_by_category(self, category: ToolCategory) -> List[ToolMetadata]:
        """Get all tools in a specific category."""
        return [self._tools[name] for name in self._categories.get(category, [])]

    def execute(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[Any, Dict[str, Any]]:
        """
        Execute a tool with given arguments.

        Args:
            tool_name: Name of the tool to execute
            arguments: Dictionary of arguments for the tool
            context: Optional execution context

        Returns:
            Tuple of (result, execution_info)
        """
        if tool_name not in self._tools:
            raise ValueError(f"Tool '{tool_name}' not found")

        metadata = self._tools[tool_name]

        # Validate required parameters
        missing_params = [
            param for param in metadata.required_params
            if param not in arguments
        ]
        if missing_params:
            raise ValueError(
                f"Missing required parameters for '{tool_name}': {missing_params}"
            )

        # Prepare execution context if needed
        execution_info = {
            "tool": tool_name,
            "arguments": arguments.copy(),
            "timestamp": datetime.now().isoformat(),
            "success": False
        }

        try:
            # Execute the tool
            if metadata.requires_context and context:
                result = metadata.function(**arguments, context=context)
            else:
                result = metadata.function(**arguments)

            execution_info.update({
                "success": True,
                "result_type": type(result).__name__,
                "execution_time": None  # Would be calculated with time measurement
            })

            # Record execution
            self._execution_history.append(execution_info)

            return result, execution_info

        except Exception as e:
            execution_info.update({
                "error": str(e),
                "error_type": type(e).__name__
            })
            self._execution_history.append(execution_info)
            raise

    def get_execution_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent tool execution history."""
        return self._execution_history[-limit:] if self._execution_history else []

    def generate_openapi_schema(self) -> Dict[str, Any]:
        """Generate OpenAPI schema for all registered tools."""
        schema = {
            "openapi": "3.0.0",
            "info": {
                "title": "Code-Extract Tool API",
                "version": "1.0.0",
                "description": "API for code-extract tool system"
            },
            "paths": {},
            "components": {
                "schemas": {}
            }
        }

        for tool_name, metadata in self._tools.items():
            # Create schema for each tool
            path_schema = {
                "post": {
                    "summary": metadata.description,
                    "operationId": tool_name,
                    "parameters": [],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        param_name: {
                                            "type": param_info.get("type", "string").lower()
                                        }
                                        for param_name, param_info in metadata.parameters.items()
                                    },
                                    "required": metadata.required_params
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "Successful execution",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "result": {
                                                "type": metadata.returns.get("type", "any").lower()
                                            },
                                            "execution_info": {
                                                "type": "object"
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            schema["paths"][f"/tools/{tool_name}"] = path_schema

        return schema


# Global registry instance
registry = ToolRegistry()


# Example tool registration
@registry.register(
    name="search_items",
    description="Search for items in the codebase",
    category=ToolCategory.DATA_QUERIES,
    requires_context=True
)
def search_items_tool(query: str, limit: int = 10, context: Dict[str, Any] = None):
    """
    Search for code items matching the query.

    Args:
        query: Search query string
        limit: Maximum number of results
        context: Execution context with data access

    Returns:
        List of matching items
    """
    # Implementation would use context to access data layer
    return {"items": [], "count": 0}


@registry.register(
    name="get_item_code",
    description="Get source code for a specific item",
    category=ToolCategory.DATA_QUERIES,
    requires_context=True
)
def get_item_code_tool(item_name: str, context: Dict[str, Any] = None):
    """
    Retrieve source code for a code item.

    Args:
        item_name: Name or ID of the item
        context: Execution context

    Returns:
        Item code and metadata
    """
    return {"code": "", "metadata": {}}

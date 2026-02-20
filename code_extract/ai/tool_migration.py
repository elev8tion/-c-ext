"""
Tool migration and integration system.
Bridges existing tool infrastructure with the new registry.
"""

import importlib
import inspect
from typing import Dict, Any, List, Optional, Callable, Type
from pathlib import Path
from datetime import datetime
import sys
import json

from .tool_registry import ToolRegistry, ToolCategory, ToolMetadata


class ToolMigrationError(Exception):
    """Exception raised during tool migration."""
    pass


class ToolIntegrationLayer:
    """
    Integration layer that bridges existing tools with the new registry.
    Handles discovery, migration, and compatibility.
    """

    def __init__(self, registry: ToolRegistry):
        self.registry = registry
        self._migrated_tools: Dict[str, Dict[str, Any]] = {}
        self._compatibility_layer: Dict[str, Callable] = {}

    def discover_existing_tools(self, module_paths: List[str]) -> List[Dict[str, Any]]:
        """
        Discover tools in existing modules.

        Args:
            module_paths: List of module paths to scan for tools

        Returns:
            List of discovered tool metadata
        """
        discovered = []

        for module_path in module_paths:
            try:
                # Import the module
                module = importlib.import_module(module_path)

                # Scan for tool-like functions
                for name, obj in inspect.getmembers(module):
                    if self._is_tool_function(name, obj):
                        tool_info = self._extract_tool_info(name, obj, module_path)
                        discovered.append(tool_info)

            except ImportError as e:
                print(f"Warning: Could not import module {module_path}: {e}")
                continue

        return discovered

    def _is_tool_function(self, name: str, obj: Any) -> bool:
        """Determine if an object is a tool function."""
        return (
            callable(obj) and
            not name.startswith('_') and
            hasattr(obj, '__name__') and
            not inspect.isclass(obj)
        )

    def _extract_tool_info(self, name: str, func: Callable, module_path: str) -> Dict[str, Any]:
        """Extract metadata from a tool function."""
        sig = inspect.signature(func)

        # Extract parameters
        parameters = {}
        required_params = []

        for param_name, param in sig.parameters.items():
            if param_name in ['self', 'cls']:
                continue

            param_info = {
                "type": str(param.annotation) if param.annotation != inspect.Parameter.empty else "Any",
                "description": "",
                "default": param.default if param.default != inspect.Parameter.empty else None
            }

            parameters[param_name] = param_info

            if param.default == inspect.Parameter.empty:
                required_params.append(param_name)

        # Determine category based on name and module
        category = self._infer_category(name, module_path)

        return {
            "name": name,
            "function": func,
            "module": module_path,
            "description": func.__doc__ or f"Tool: {name}",
            "parameters": parameters,
            "required_params": required_params,
            "category": category,
            "signature": str(sig)
        }

    def _infer_category(self, tool_name: str, module_path: str) -> str:
        """Infer tool category based on name and module."""
        tool_name_lower = tool_name.lower()
        module_lower = module_path.lower()

        # Category inference logic
        if any(keyword in tool_name_lower for keyword in ['search', 'get', 'find', 'query']):
            return ToolCategory.DATA_QUERIES.value
        elif any(keyword in tool_name_lower for keyword in ['navigate', 'select', 'ui', 'tab']):
            return ToolCategory.UI_OPERATIONS.value
        elif any(keyword in tool_name_lower for keyword in ['clone', 'extract', 'remix', 'build']):
            return ToolCategory.WORKFLOW.value
        elif any(keyword in tool_name_lower for keyword in ['boilerplate', 'template', 'pattern']):
            return ToolCategory.BOILERPLATE.value
        elif any(keyword in tool_name_lower for keyword in ['migration', 'migrate']):
            return ToolCategory.MIGRATION.value
        elif 'tools' in module_lower:
            return ToolCategory.CODE_ANALYSIS.value
        else:
            return ToolCategory.GENERAL.value

    def migrate_tool(self, tool_info: Dict[str, Any]) -> str:
        """
        Migrate a discovered tool to the new registry.

        Args:
            tool_info: Tool metadata from discovery

        Returns:
            Registered tool name
        """
        tool_name = tool_info["name"]

        # Create wrapper for compatibility
        def tool_wrapper(**kwargs):
            """Wrapper for migrated tool."""
            try:
                # Call the original function
                result = tool_info["function"](**kwargs)
                return result
            except Exception as e:
                # Add migration context to error
                raise ToolMigrationError(
                    f"Error executing migrated tool '{tool_name}': {str(e)}"
                ) from e

        # Register with the new registry
        self.registry.register(
            name=tool_name,
            description=tool_info["description"],
            category=ToolCategory(tool_info["category"]),
            requires_context=False  # Legacy tools don't use context
        )(tool_wrapper)

        # Store migration info
        self._migrated_tools[tool_name] = {
            "original_module": tool_info["module"],
            "migration_timestamp": datetime.now().isoformat(),
            "parameters": tool_info["parameters"]
        }

        # Create compatibility wrapper for old-style calls
        self._compatibility_layer[tool_name] = tool_info["function"]

        print(f"Migrated tool: {tool_name} from {tool_info['module']}")
        return tool_name

    def migrate_all_discovered(self, module_paths: List[str]) -> List[str]:
        """
        Discover and migrate all tools from specified modules.

        Args:
            module_paths: Modules to scan for tools

        Returns:
            List of migrated tool names
        """
        discovered = self.discover_existing_tools(module_paths)
        migrated = []

        for tool_info in discovered:
            try:
                tool_name = self.migrate_tool(tool_info)
                migrated.append(tool_name)
            except Exception as e:
                print(f"Failed to migrate {tool_info['name']}: {e}")
                continue

        return migrated

    def create_compatibility_shim(self) -> Callable:
        """
        Create a compatibility shim that mimics the old execute_tool interface.

        Returns:
            Function that can replace old execute_tool calls
        """
        def execute_tool_shim(tool_name: str, **kwargs) -> Any:
            """
            Compatibility shim for execute_tool.

            Args:
                tool_name: Name of the tool to execute
                **kwargs: Tool arguments

            Returns:
                Tool execution result
            """
            # First try the new registry
            if tool_name in self.registry.get_all_tools():
                result, _ = self.registry.execute(tool_name, kwargs)
                return result

            # Fall back to compatibility layer
            if tool_name in self._compatibility_layer:
                return self._compatibility_layer[tool_name](**kwargs)

            # Try to discover and migrate on-the-fly
            try:
                # This is a simplified version - in reality would need module context
                raise ToolMigrationError(
                    f"Tool '{tool_name}' not found in registry or compatibility layer"
                )
            except ToolMigrationError:
                # Re-raise with better message
                raise ValueError(
                    f"Tool '{tool_name}' not available. "
                    f"Available tools: {list(self.registry.get_all_tools().keys())}"
                )

        return execute_tool_shim

    def generate_migration_report(self) -> Dict[str, Any]:
        """Generate a report of all migrated tools."""
        return {
            "migration_summary": {
                "total_migrated": len(self._migrated_tools),
                "migrated_tools": list(self._migrated_tools.keys()),
                "registry_tools": list(self.registry.get_all_tools().keys()),
                "compatibility_layer_size": len(self._compatibility_layer)
            },
            "detailed_migration": self._migrated_tools,
            "registry_categories": {
                category.value: len(self.registry.get_tools_by_category(category))
                for category in ToolCategory
            }
        }

    def export_migration_config(self, filepath: str) -> None:
        """
        Export migration configuration for persistence.

        Args:
            filepath: Path to save configuration
        """
        config = {
            "migrated_tools": self._migrated_tools,
            "registry_state": {
                "tool_count": len(self.registry.get_all_tools()),
                "categories": {
                    cat.value: [
                        tool.name for tool in self.registry.get_tools_by_category(cat)
                    ]
                    for cat in ToolCategory
                }
            },
            "export_timestamp": datetime.now().isoformat(),
            "version": "1.0"
        }

        with open(filepath, 'w') as f:
            json.dump(config, f, indent=2)

        print(f"Migration config exported to {filepath}")


# Factory function for easy integration
def create_tool_integration() -> ToolIntegrationLayer:
    """
    Factory function to create and configure tool integration.

    Returns:
        Configured ToolIntegrationLayer instance
    """
    from .tool_registry import registry

    integration = ToolIntegrationLayer(registry)

    # Auto-discover tools from common modules
    common_modules = [
        "code_extract.tools",
        "code_extract.ai.tools",
        "code_extract.ui.operations",
        "code_extract.workflows"
    ]

    # Filter to existing modules only
    existing_modules = []
    for module in common_modules:
        try:
            importlib.import_module(module)
            existing_modules.append(module)
        except ImportError:
            continue

    if existing_modules:
        print(f"Auto-discovering tools from: {existing_modules}")
        migrated = integration.migrate_all_discovered(existing_modules)
        print(f"Auto-migrated {len(migrated)} tools")

    return integration


# Global integration instance
_integration_instance: Optional[ToolIntegrationLayer] = None

def get_integration() -> ToolIntegrationLayer:
    """Get or create the global integration instance."""
    global _integration_instance
    if _integration_instance is None:
        _integration_instance = create_tool_integration()
    return _integration_instance


# Compatibility exports
def get_execute_tool_shim() -> Callable:
    """Get the compatibility shim for execute_tool."""
    return get_integration().create_compatibility_shim()


def migrate_tools_from_modules(module_paths: List[str]) -> List[str]:
    """Convenience function to migrate tools from modules."""
    return get_integration().migrate_all_discovered(module_paths)


def get_migration_report() -> Dict[str, Any]:
    """Get migration status report."""
    return get_integration().generate_migration_report()

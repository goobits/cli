"""
Component Registry for Universal Template System

This module provides enhanced component loading and management capabilities,
including template validation, dependency tracking, and hot-reloading support.

Features:
- Template discovery and loading
- Dependency tracking between components
- Hot-reloading support for development
- Template validation with Jinja2
- Component metadata management
- Custom Jinja2 filters for template processing
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import jinja2

logger = logging.getLogger(__name__)


class ComponentInfo:
    """Simple component info object with name attribute for list_components() return.

    Attributes:
        name: Component name (without .j2 extension)
        path: Optional path to the component file
    """

    def __init__(self, name: str, path: Optional[Path] = None) -> None:
        self.name = name
        self.path = path


class ComponentMetadata:
    """Metadata for a component template.

    Tracks component information including file system metadata,
    dependencies, and modification times for hot-reloading.

    Attributes:
        name: Component name
        path: Path to the component file
        dependencies: List of component dependencies
        last_modified: Last modification timestamp
        loaded_at: When the component was loaded
    """

    def __init__(
        self, name: str, path: Path, dependencies: Optional[List[str]] = None
    ) -> None:
        self.name = name
        self.path = path
        self.dependencies = dependencies or []
        self.last_modified = path.stat().st_mtime if path.exists() else 0
        self.loaded_at = datetime.now()

    def is_stale(self) -> bool:
        """Check if the component file has been modified since last load."""

        if not self.path.exists():
            return True

        return self.path.stat().st_mtime > self.last_modified

    def refresh_metadata(self) -> None:
        """Refresh metadata from file system."""

        if self.path.exists():
            self.last_modified = self.path.stat().st_mtime

        self.loaded_at = datetime.now()


class ComponentRegistry:
    """
    Enhanced registry for managing universal component templates.

    Features:
    - Template loading and caching
    - Dependency tracking between components
    - Hot-reloading support
    - Template validation
    - Component discovery

    This class serves as the central registry for all component templates
    used by the Universal Template System. It handles template discovery,
    loading, validation, and metadata management.
    """

    def __init__(
        self, components_dir: Optional[Path] = None, auto_reload: bool = False
    ) -> None:
        """
        Initialize the component registry.

        Args:
            components_dir: Path to components directory, defaults to built-in components
            auto_reload: Enable automatic reloading of modified templates
        """

        self.components_dir = components_dir or Path(__file__).parent / "components"

        self.auto_reload = auto_reload

        self.validation_enabled = True  # Enable template validation by default

        self._cleared = False  # Track if registry has been explicitly cleared

        # Component storage
        self._components: Dict[str, str] = {}
        self._metadata: Dict[str, ComponentMetadata] = {}
        self._dependencies: Dict[str, List[str]] = {}  # For test compatibility

        # Jinja2 environment for template validation
        self._loader = jinja2.FileSystemLoader(str(self.components_dir))
        self._env = jinja2.Environment(
            loader=self._loader, trim_blocks=True, lstrip_blocks=True
        )

        # Add custom filters that templates expect
        self._env.filters["snake_case"] = self._snake_case_filter
        self._env.filters["camelCase"] = self._camel_case_filter
        self._env.filters["PascalCase"] = self._pascal_case_filter
        self._env.filters["js_string"] = self._js_string_filter
        self._env.filters["ts_type"] = self._ts_type_filter
        self._env.filters["python_repr"] = repr

        logger.info(
            f"ComponentRegistry initialized with components_dir: {self.components_dir}"
        )

    def load_components(self, force_reload: bool = False) -> None:
        """

        Load all component templates from the components directory.

        Args:

            force_reload: Force reload all components even if cached

        """

        if not self.components_dir.exists():
            logger.warning(f"Components directory not found: {self.components_dir}")

            return

        # Reset cleared flag when loading components

        self._cleared = False

        logger.info(f"Loading components from: {self.components_dir}")

        for template_file in self.components_dir.rglob("*.j2"):
            # Create component name with path relative to components_dir

            relative_path = template_file.relative_to(self.components_dir)

            if relative_path.parent != Path("."):
                component_name = str(relative_path.with_suffix("")).replace("\\", "/")

            else:
                component_name = template_file.stem

            # Check if we need to load/reload this component

            if (
                force_reload
                or component_name not in self._components
                or (
                    component_name in self._metadata
                    and self._metadata[component_name].is_stale()
                )
            ):
                try:
                    content = template_file.read_text(encoding="utf-8")

                    self._components[component_name] = content

                    # Create/update metadata

                    dependencies = self._extract_template_dependencies(content)

                    self._metadata[component_name] = ComponentMetadata(
                        name=component_name,
                        path=template_file,
                        dependencies=dependencies,
                    )

                    # Validate template syntax

                    self._validate_template(component_name, content)

                    logger.debug(f"Loaded component: {component_name}")

                except Exception as e:
                    logger.error(f"Failed to load component {component_name}: {e}")

                    continue

        logger.info(f"Loaded {len(self._components)} components")

    def get_component(self, name: str, auto_reload: Optional[bool] = None) -> str:
        """

        Get a component template by name.

        Args:

            name: Component name (without .j2 extension)

            auto_reload: Override auto-reload setting for this request

        Returns:

            Template content as string

        Raises:

            KeyError: If component is not found

        """

        should_reload = auto_reload if auto_reload is not None else self.auto_reload

        # Check if component needs reloading

        if should_reload and name in self._metadata:
            if self._metadata[name].is_stale():
                logger.debug(f"Reloading stale component: {name}")

                self._load_single_component(name)

        # Load on-demand if not in cache

        if name not in self._components:
            self._load_single_component(name)

        if name not in self._components:
            raise KeyError(f"Component '{name}' not found")

        return self._components[name]

    def list_components(self) -> List[ComponentInfo]:
        """

        List all available components as ComponentInfo objects.

        Returns:

            List of ComponentInfo objects with .name attribute

        """

        # If registry has been cleared, only show loaded components

        if self._cleared:
            loaded = set(self._components.keys())

            all_components = loaded

        else:
            # Include both loaded and discoverable components

            loaded = set(self._components.keys())

            discoverable_files = {
                f for f in self.components_dir.rglob("*.j2") if f.is_file()
            }

            discoverable = set()

            for f in discoverable_files:
                relative_path = f.relative_to(self.components_dir)

                if relative_path.parent != Path("."):
                    component_name = str(relative_path.with_suffix("")).replace(
                        "\\", "/"
                    )

                else:
                    component_name = f.stem

                discoverable.add(component_name)

            all_components = loaded | discoverable

        component_infos = []

        for name in sorted(all_components):
            # Find the corresponding file path

            component_file = self.components_dir / f"{name}.j2"

            if component_file.exists():
                component_infos.append(ComponentInfo(name, component_file))

            else:
                component_infos.append(ComponentInfo(name))

        return component_infos

    def has_component(self, name: str) -> bool:
        """

        Check if a component exists.

        Args:

            name: Component name

        Returns:

            True if component exists, False otherwise

        """

        # If registry has been cleared, only check loaded components

        if self._cleared:
            return name in self._components

        else:
            return (
                name in self._components
                or (self.components_dir / f"{name}.j2").exists()
            )

    def get_component_metadata(self, name: str) -> Optional[ComponentMetadata]:
        """

        Get metadata for a component.

        Args:

            name: Component name

        Returns:

            ComponentMetadata if component exists, None otherwise

        """

        # If metadata is missing but component exists, regenerate it
        if name not in self._metadata and name in self._components:
            # Find the component file to recreate metadata
            component_file = self.components_dir / f"{name}.j2"
            if component_file.exists():
                content = self._components[name]
                dependencies = self._extract_template_dependencies(content)
                self._metadata[name] = ComponentMetadata(
                    name, component_file, dependencies
                )
                self._dependencies[name] = dependencies

        return self._metadata.get(name)

    def get_dependencies(self, name: str) -> List[str]:
        """

        Get dependencies for a component.

        Args:

            name: Component name

        Returns:

            List of dependency component names

        """

        metadata = self.get_component_metadata(name)

        return metadata.dependencies if metadata else []

    def validate_all_components(self) -> Dict[str, List[str]]:
        """

        Validate all loaded components.

        Returns:

            Dictionary mapping component names to lists of validation errors

        """

        errors = {}

        for name, content in self._components.items():
            try:
                component_errors = self._validate_template(name, content)

                if component_errors:
                    errors[name] = component_errors

            except Exception as e:
                errors[name] = [str(e)]

        return errors

    def reload_component(self, name: str) -> bool:
        """

        Force reload a specific component.

        Args:

            name: Component name to reload

        Returns:

            True if successfully reloaded, False otherwise

        """

        try:
            self._load_single_component(name)

            return True

        except Exception as e:
            logger.error(f"Failed to reload component {name}: {e}")

            return False

    def component_exists(self, name: str) -> bool:
        """

        Check if a component exists (alias for has_component for test compatibility).

        Args:

            name: Component name

        Returns:

            True if component exists, False otherwise

        """

        return self.has_component(name)

    def get_component_dependencies(self, name: str) -> List[str]:
        """

        Get dependencies for a component (alias for get_dependencies).

        Args:

            name: Component name

        Returns:

            List of dependency names

        """

        return self.get_dependencies(name)

    def clear_cache(self) -> None:
        """Clear all cached components and metadata."""

        self._components.clear()

        self._metadata.clear()

        self._dependencies.clear()

        logger.info("Component cache cleared")

    def clear(self) -> None:
        """Clear registry and hide components until explicitly reloaded."""

        self._components.clear()

        self._metadata.clear()

        self._dependencies.clear()

        self._cleared = True

        logger.info("Component registry cleared")

    def _snake_case_filter(self, name: str) -> str:
        """Convert name to snake_case.

        Args:
            name: Input name to convert

        Returns:
            Name converted to snake_case format
        """
        # Replace hyphens with underscores
        name = name.replace("-", "_")

        # Convert CamelCase to snake_case
        name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
        name = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", name)

        # Convert to lowercase and clean up
        name = name.lower()
        name = re.sub(r"_+", "_", name)  # Remove multiple underscores
        name = name.strip("_")  # Remove leading/trailing underscores

        return name

    def _camel_case_filter(self, text: str) -> str:
        """Convert text to camelCase.

        Args:
            text: Input text to convert

        Returns:
            Text converted to camelCase format
        """
        if not text:
            return text
        words = re.split(r"[-_\s]+", text.lower())
        return words[0] + "".join(word.capitalize() for word in words[1:])

    def _pascal_case_filter(self, text: str) -> str:
        """Convert text to PascalCase.

        Args:
            text: Input text to convert

        Returns:
            Text converted to PascalCase format
        """
        if not text:
            return text
        words = re.split(r"[-_\s]+", text.lower())
        return "".join(word.capitalize() for word in words)

    def _js_string_filter(self, value: Any) -> str:
        """Escape string for JavaScript and wrap in quotes.

        Args:
            value: Value to escape and quote

        Returns:
            JavaScript-escaped string wrapped in double quotes
        """
        if not isinstance(value, str):
            return f'"{str(value)}"'

        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'"{escaped}"'

    def _ts_type_filter(self, value: str) -> str:
        """Convert Python/CLI type to TypeScript type.

        Args:
            value: Type name to convert

        Returns:
            TypeScript type equivalent
        """
        type_mapping = {
            "str": "string",
            "string": "string",
            "int": "number",
            "integer": "number",
            "float": "number",
            "bool": "boolean",
            "boolean": "boolean",
            "list": "string[]",
            "array": "string[]",
        }
        return type_mapping.get(value.lower(), "any")

    def _load_single_component(self, name: str) -> None:
        """Load a single component by name."""

        # Handle nested components (e.g., "subdir/nested" -> "subdir/nested.j2")

        component_file = self.components_dir / f"{name}.j2"

        if not component_file.exists():
            # Check if this component was previously loaded (file was deleted)

            if name in self._components:
                raise FileNotFoundError(f"Component file was deleted: {component_file}")

            else:
                raise KeyError(f"Component '{name}' not found")

        try:
            content = component_file.read_text(encoding="utf-8")

            self._components[name] = content

            # Create/update metadata

            dependencies = self._extract_template_dependencies(content)

            self._metadata[name] = ComponentMetadata(
                name=name, path=component_file, dependencies=dependencies
            )

            # Validate template

            self._validate_template(name, content)

        except Exception as e:
            logger.error(f"Failed to load component {name}: {e}")

            raise

    def _extract_template_dependencies(self, template_content: str) -> List[str]:
        """

        Extract template dependencies from Jinja2 includes, extends, and dependency comments.

        Args:

            template_content: Template content to analyze

        Returns:

            List of dependency template names

        """

        dependencies = []

        # Simple regex-based extraction (could be enhanced with proper parsing)

        import re

        # Find {% include %} and {% extends %} statements

        include_pattern = r'{%\s*include\s+[\'"]([^\'"]+)[\'"]\s*%}'

        extends_pattern = r'{%\s*extends\s+[\'"]([^\'"]+)[\'"]\s*%}'

        for pattern in [include_pattern, extends_pattern]:
            matches = re.findall(pattern, template_content)

            for match in matches:
                # Remove .j2 extension if present

                dep_name = match.replace(".j2", "")

                if dep_name not in dependencies:
                    dependencies.append(dep_name)

        # Also check for dependency comments: {{# Dependencies: base.j2, utils.j2 #}}

        comment_pattern = r"\{\{#\s*Dependencies:\s*([^#]+)#\}\}"

        comment_matches = re.findall(comment_pattern, template_content)

        for match in comment_matches:
            # Split by comma and clean up each dependency name

            deps = [dep.strip() for dep in match.split(",")]

            for dep in deps:
                # Remove .j2 extension if present

                dep_name = dep.replace(".j2", "")

                if dep_name and dep_name not in dependencies:
                    dependencies.append(dep_name)

        return dependencies

    def _validate_template(self, name: str, content: str) -> List[str]:
        """

        Validate template syntax.

        Args:

            name: Template name

            content: Template content

        Returns:

            List of validation errors

        """

        errors = []

        try:
            # Parse template to check for syntax errors

            self._env.from_string(content)

            # Additional validation could be added here:

            # - Check for required variables

            # - Validate template structure

            # - Check for common patterns

        except jinja2.TemplateSyntaxError as e:
            errors.append(f"Syntax error at line {e.lineno}: {e.message}")

        except Exception as e:
            errors.append(f"Validation error: {str(e)}")

        if errors:
            logger.warning(f"Template validation errors in {name}: {errors}")

        return errors

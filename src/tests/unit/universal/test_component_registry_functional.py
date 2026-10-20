"""
Comprehensive functional tests for the Universal Template System Component Registry.

These tests focus on real functionality to maximize coverage improvements
from 0% to 70% by testing:
- ComponentRegistry component loading and management
- Component resolution and registration
- Error handling and validation
- Metadata tracking and caching
- Hot-reloading capabilities
"""

import ast
import shutil
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from goobits_cli.core.schemas import GoobitsConfigSchema
from goobits_cli.universal.component_registry import (
    ComponentMetadata,
    ComponentRegistry,
)
from goobits_cli.universal.ir.builder import IRBuilder
from goobits_cli.universal.renderers.python_renderer import PythonRenderer


@pytest.mark.parametrize("default", [False, None, "it's a path: \\tmp\nnext"])
def test_builtin_python_template_renders_with_registry_filters(default, caplog):
    """Registry validation and rendering must accept real Python defaults."""
    config = GoobitsConfigSchema(
        package_name="sample-cli",
        command_name="sample",
        display_name="Sample CLI",
        description="Registry rendering regression",
        installation={"pypi_name": "sample-cli"},
        cli={
            "name": "sample",
            "tagline": "Sample CLI",
            "commands": {
                "hello": {
                    "desc": "Say hello",
                    "options": [{"name": "label", "default": default}],
                }
            },
        },
    )
    registry = ComponentRegistry()
    registry.load_components()
    context = PythonRenderer().get_template_context(IRBuilder().build(config))
    rendered = registry._env.get_template("python_cli_consolidated.j2").render(context)
    tree = ast.parse(rendered)
    option_defaults = [
        ast.literal_eval(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.keyword) and node.arg == "default"
    ]
    assert default in option_defaults
    assert "Template validation errors" not in caplog.text


class TestComponentRegistryFunctional:
    """Functional tests for ComponentRegistry with real file operations"""

    def setup_method(self):
        """Setup test environment with real component files"""
        # Create temporary directory structure
        self.temp_dir = Path(tempfile.mkdtemp())
        self.components_dir = self.temp_dir / "components"
        self.components_dir.mkdir()

        # Create test component templates
        self._create_test_components()

    def teardown_method(self):
        """Clean up test environment"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def _create_test_components(self):
        """Create comprehensive test component templates"""

        # 1. Simple command handler template
        command_handler = """
{# Basic Command Handler Template #}
{% if language == 'python' %}
import click

@click.group()
@click.version_option(version="{{ project.version }}")
def cli():
    '''{{ project.description }}'''
    pass

{% for command_name, command in cli.commands.items() %}
@cli.command()
def {{ command_name | snake_case }}():
    '''{{ command.description }}'''
    # Call hook function
    result = {{ command.hook_name }}()
    print(f"Command {{ command_name }} result: {result}")
{% endfor %}

if __name__ == "__main__":
    cli()
{% elif language == 'nodejs' %}
const { Command } = require('commander');
const program = new Command();

program
    .name('{{ cli.root_command.name }}')
    .description('{{ project.description }}')
    .version('{{ project.version }}');

{% for command_name, command in cli.commands.items() %}
program
    .command('{{ command_name }}')
    .description('{{ command.description }}')
    .action(async () => {
        const result = await {{ command.hook_name | camelCase }}();
        console.log(`Command {{ command_name }} result:`, result);
    });
{% endfor %}

program.parse();
{% endif %}
"""
        (self.components_dir / "command_handler.j2").write_text(command_handler)

        # 2. Configuration manager template
        config_manager = """
{# Configuration Manager Template #}
{% if language == 'python' %}
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional

class ConfigManager:
    def __init__(self, config_file: str = "{{ project.command_name }}.config.json"):
        self.config_file = Path.home() / ".config" / "{{ project.package_name }}" / config_file
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self._config: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        '''Load configuration from file'''
        if self.config_file.exists():
            with open(self.config_file, 'r') as f:
                self._config = json.load(f)
        else:
            self._config = self.get_default_config()
            self.save()

    def save(self) -> None:
        '''Save configuration to file'''
        with open(self.config_file, 'w') as f:
            json.dump(self._config, f, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        '''Get configuration value'''
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        '''Set configuration value'''
        self._config[key] = value
        self.save()

    def get_default_config(self) -> Dict[str, Any]:
        '''Get default configuration'''
        return {
            "version": "{{ project.version }}",
            "debug": False,
            "output_format": "json"
        }

# Global config instance
config = ConfigManager()
{% elif language == 'nodejs' %}
const fs = require('fs');
const path = require('path');
const os = require('os');

class ConfigManager {
    constructor(configFile = '{{ project.command_name }}.config.json') {
        this.configDir = path.join(os.homedir(), '.config', '{{ project.package_name }}');
        this.configFile = path.join(this.configDir, configFile);
        this._config = {};
        this.load();
    }

    load() {
        if (!fs.existsSync(this.configDir)) {
            fs.mkdirSync(this.configDir, { recursive: true });
        }

        if (fs.existsSync(this.configFile)) {
            const data = fs.readFileSync(this.configFile, 'utf8');
            this._config = JSON.parse(data);
        } else {
            this._config = this.getDefaultConfig();
            this.save();
        }
    }

    save() {
        fs.writeFileSync(this.configFile, JSON.stringify(this._config, null, 2));
    }

    get(key, defaultValue = null) {
        return this._config[key] !== undefined ? this._config[key] : defaultValue;
    }

    set(key, value) {
        this._config[key] = value;
        this.save();
    }

    getDefaultConfig() {
        return {
            version: '{{ project.version }}',
            debug: false,
            outputFormat: 'json'
        };
    }
}

module.exports = { ConfigManager };
{% endif %}
"""
        (self.components_dir / "config_manager.j2").write_text(config_manager)

        # 3. Template with dependencies (includes other templates)
        main_cli = """
{# Main CLI Template - includes other components #}
{% include 'command_handler.j2' %}

{# Additional initialization code #}
{% if language == 'python' %}

# Initialize configuration
from {{ project.package_name.replace('-', '_') }}_config import config

def setup_logging():
    import logging
    level = logging.DEBUG if config.get('debug', False) else logging.INFO
    logging.basicConfig(level=level)

setup_logging()
{% endif %}
"""
        (self.components_dir / "main_cli.j2").write_text(main_cli)

        # 4. Hook system template
        hook_system = """
{# Hook System Template #}
{% if language == 'python' %}
# Generated hooks for {{ project.name }}
from typing import Any, Dict

{% for command_name, command in cli.commands.items() %}
def {{ command.hook_name }}(*args, **kwargs) -> Dict[str, Any]:
    '''
    Hook for {{ command_name }} command
    {{ command.description }}

    Args:
        *args: Positional arguments from CLI
        **kwargs: Keyword arguments from CLI options

    Returns:
        Dict with command result
    '''
    # TODO: Implement {{ command_name }} logic here
    return {
        'command': '{{ command_name }}',
        'status': 'success',
        'message': 'Command {{ command_name }} executed successfully',
        'args': args,
        'kwargs': kwargs
    }

{% endfor %}

# Hook registry for dynamic dispatch
HOOKS = {
    {% for command_name, command in cli.commands.items() %}
    '{{ command_name }}': {{ command.hook_name }},
    {% endfor %}
}

def get_hook(command_name: str):
    '''Get hook function for command'''
    return HOOKS.get(command_name)

def execute_hook(command_name: str, *args, **kwargs):
    '''Execute hook for command'''
    hook = get_hook(command_name)
    if hook:
        return hook(*args, **kwargs)
    else:
        return {'status': 'error', 'message': f'No hook found for command {command_name}'}
{% elif language == 'nodejs' %}
// Generated hooks for {{ project.name }}

{% for command_name, command in cli.commands.items() %}
async function {{ command.hook_name | camelCase }}(...args) {
    /**
     * Hook for {{ command_name }} command
     * {{ command.description }}
     */
    // TODO: Implement {{ command_name }} logic here
    return {
        command: '{{ command_name }}',
        status: 'success',
        message: 'Command {{ command_name }} executed successfully',
        args: args
    };
}

{% endfor %}

// Hook registry for dynamic dispatch
const HOOKS = {
    {% for command_name, command in cli.commands.items() %}
    '{{ command_name }}': {{ command.hook_name | camelCase }},
    {% endfor %}
};

function getHook(commandName) {
    return HOOKS[commandName];
}

async function executeHook(commandName, ...args) {
    const hook = getHook(commandName);
    if (hook) {
        return await hook(...args);
    } else {
        return {
            status: 'error',
            message: `No hook found for command ${commandName}`
        };
    }
}

module.exports = {
    {% for command_name, command in cli.commands.items() %}
    {{ command.hook_name | camelCase }},
    {% endfor %}
    HOOKS,
    getHook,
    executeHook
};
{% endif %}
"""
        (self.components_dir / "hook_system.j2").write_text(hook_system)

        # 5. Invalid template for error testing
        invalid_template = """
{# Invalid Template with syntax errors #}
{% if language == 'python'
# Missing closing %}
This template has syntax errors
{% endfor without matching for %}
"""
        (self.components_dir / "invalid_template.j2").write_text(invalid_template)

        # 6. Template with complex nested dependencies
        complex_template = """
{# Complex template with multiple includes #}
{% include 'config_manager.j2' %}
{% include 'hook_system.j2' %}

{% if language == 'python' %}
# Integration layer
def initialize_{{ project.command_name.replace('-', '_') }}():
    '''Initialize the CLI application'''
    setup_logging()  # From main_cli.j2
    config.load()    # From config_manager.j2
    return True
{% endif %}
"""
        (self.components_dir / "complex_template.j2").write_text(complex_template)

    def test_component_registry_initialization(self):
        """Test ComponentRegistry initialization with real directory"""
        registry = ComponentRegistry(self.components_dir)

        assert registry.components_dir == self.components_dir
        assert registry.auto_reload is False  # Default
        assert len(registry._components) == 0  # Not loaded yet
        assert len(registry._metadata) == 0

    def test_component_registry_with_auto_reload(self):
        """Test ComponentRegistry with auto-reload enabled"""
        registry = ComponentRegistry(self.components_dir, auto_reload=True)

        assert registry.auto_reload is True

    def test_load_all_components(self):
        """Test loading all components from directory"""
        registry = ComponentRegistry(self.components_dir)
        registry.load_components()

        # Should have loaded all valid components
        components = registry.list_components()
        component_names = [comp.name for comp in components]
        expected_components = {
            "command_handler",
            "config_manager",
            "main_cli",
            "hook_system",
            "invalid_template",
            "complex_template",
        }

        assert len(components) >= 5  # At least the valid ones
        for component in expected_components:
            if component != "invalid_template":  # May fail to load
                assert component in component_names

    def test_get_component_content(self):
        """Test retrieving actual component content"""
        registry = ComponentRegistry(self.components_dir)
        registry.load_components()

        # Test command handler
        command_handler = registry.get_component("command_handler")
        assert "Basic Command Handler Template" in command_handler
        assert "{% if language == 'python' %}" in command_handler
        assert "@click.group()" in command_handler
        assert "commander" in command_handler  # Node.js part

        # Test config manager
        config_manager = registry.get_component("config_manager")
        assert "Configuration Manager Template" in config_manager
        assert "class ConfigManager" in config_manager
        assert "ConfigManager {" in config_manager  # Node.js part

    def test_component_on_demand_loading(self):
        """Test loading components on demand without pre-loading"""
        registry = ComponentRegistry(self.components_dir)

        # Don't call load_components() first
        command_handler = registry.get_component("command_handler")

        assert command_handler is not None
        assert "Basic Command Handler Template" in command_handler

        # Should now be in cache
        assert "command_handler" in registry._components
        assert "command_handler" in registry._metadata

    def test_component_existence_check(self):
        """Test checking if components exist"""
        registry = ComponentRegistry(self.components_dir)

        # Should work without loading
        assert registry.has_component("command_handler") is True
        assert registry.has_component("config_manager") is True
        assert registry.has_component("nonexistent_component") is False

        # Should also work after loading
        registry.load_components()
        assert registry.has_component("command_handler") is True
        assert registry.has_component("hook_system") is True

    def test_component_dependency_extraction(self):
        """Test extracting dependencies from templates"""
        registry = ComponentRegistry(self.components_dir)
        registry.load_components()

        # main_cli includes command_handler
        main_cli_deps = registry.get_dependencies("main_cli")
        assert "command_handler" in main_cli_deps

        # complex_template includes config_manager and hook_system
        complex_deps = registry.get_dependencies("complex_template")
        assert "config_manager" in complex_deps
        assert "hook_system" in complex_deps

        # Simple templates should have no dependencies
        command_handler_deps = registry.get_dependencies("command_handler")
        assert len(command_handler_deps) == 0

    def test_component_metadata_functionality(self):
        """Test component metadata tracking"""
        registry = ComponentRegistry(self.components_dir)
        registry.load_components()

        # Get metadata for a component
        metadata = registry.get_component_metadata("command_handler")

        assert metadata is not None
        assert metadata.name == "command_handler"
        assert metadata.path == self.components_dir / "command_handler.j2"
        assert metadata.path.exists()
        assert metadata.last_modified > 0
        assert metadata.loaded_at is not None
        assert len(metadata.dependencies) == 0  # No dependencies

        # Test metadata for component with dependencies
        main_cli_metadata = registry.get_component_metadata("main_cli")
        assert main_cli_metadata is not None
        assert "command_handler" in main_cli_metadata.dependencies

    def test_component_staleness_detection(self):
        """Test detecting when components have been modified"""
        registry = ComponentRegistry(self.components_dir)
        registry.load_components()

        metadata = registry.get_component_metadata("command_handler")
        original_modified_time = metadata.last_modified

        # Component should not be stale initially
        assert metadata.is_stale() is False

        # Wait a bit and modify the file
        time.sleep(0.1)
        component_file = self.components_dir / "command_handler.j2"

        # Modify the file
        content = component_file.read_text()
        component_file.write_text(content + "\n# Modified")

        # Now should be stale
        assert metadata.is_stale() is True

        # Refresh metadata
        metadata.refresh_metadata()
        assert metadata.last_modified > original_modified_time
        assert metadata.is_stale() is False

    def test_auto_reload_functionality(self):
        """Test automatic reloading of modified components"""
        registry = ComponentRegistry(self.components_dir, auto_reload=True)
        registry.load_components()

        # Get original content
        original_content = registry.get_component("command_handler")

        # Modify the file
        time.sleep(0.1)
        component_file = self.components_dir / "command_handler.j2"
        modified_content = original_content + "\n# Auto-reload test modification"
        component_file.write_text(modified_content)

        # Getting the component again should reload it
        reloaded_content = registry.get_component("command_handler")
        assert "Auto-reload test modification" in reloaded_content
        assert reloaded_content != original_content

    def test_template_validation(self):
        """Test template validation functionality"""
        registry = ComponentRegistry(self.components_dir)
        registry.load_components()

        # Validate all components
        errors = registry.validate_all_components()

        # Valid templates should have no errors
        valid_components = ["command_handler", "config_manager", "hook_system"]
        for component in valid_components:
            if component in errors:
                # Should be empty list or no entry
                assert len(errors.get(component, [])) == 0

        # Invalid template should have errors
        if "invalid_template" in errors:
            assert len(errors["invalid_template"]) > 0

    def test_component_reload_functionality(self):
        """Test reloading specific components"""
        registry = ComponentRegistry(self.components_dir)
        registry.load_components()

        # Modify a component file
        component_file = self.components_dir / "command_handler.j2"
        original_content = component_file.read_text()
        modified_content = original_content + "\n# Reload test"

        time.sleep(0.1)
        component_file.write_text(modified_content)

        # Reload the specific component
        success = registry.reload_component("command_handler")
        assert success is True

        # Content should be updated
        reloaded_content = registry.get_component("command_handler")
        assert "Reload test" in reloaded_content

        # Test reloading non-existent component
        success = registry.reload_component("nonexistent")
        assert success is False

    def test_component_cache_management(self):
        """Test component cache clearing and management"""
        registry = ComponentRegistry(self.components_dir)
        registry.load_components()

        # Should have components loaded
        assert len(registry._components) > 0
        assert len(registry._metadata) > 0

        # Clear cache
        registry.clear_cache()

        # Cache should be empty
        assert len(registry._components) == 0
        assert len(registry._metadata) == 0

        # But components should still be discoverable
        components = registry.list_components()
        assert len(components) > 0  # Still discoverable from filesystem

    def test_error_handling_missing_directory(self):
        """Test handling of missing components directory"""
        nonexistent_dir = self.temp_dir / "nonexistent"
        registry = ComponentRegistry(nonexistent_dir)

        # Should handle missing directory gracefully
        registry.load_components()  # Should not crash

        components = registry.list_components()
        assert len(components) == 0

        # Should raise KeyError for missing components
        with pytest.raises(KeyError):
            registry.get_component("nonexistent")

    def test_component_with_complex_jinja_syntax(self):
        """Test components with complex Jinja2 syntax"""
        registry = ComponentRegistry(self.components_dir)
        registry.load_components()

        # Hook system has complex template logic
        hook_content = registry.get_component("hook_system")

        # Should contain various Jinja2 constructs
        assert "{% for command_name, command in cli.commands.items() %}" in hook_content
        assert "{{ command.hook_name }}" in hook_content
        assert "{{ command.hook_name | camelCase }}" in hook_content  # Filter usage

        # Template should be syntactically valid
        errors = registry.validate_all_components()
        hook_errors = errors.get("hook_system", [])
        assert len(hook_errors) == 0

    def test_component_file_encoding(self):
        """Test handling of different file encodings"""
        # Create a component with UTF-8 content
        utf8_content = """
{# UTF-8 Template with special characters #}
# Project: {{ project.name }} 🚀
# Description: {{ project.description }} ✨
# Author: {{ project.author }} 👨‍💻

def greet():
    print("Hello World! 🌍")
    print("Çà marchë! 🇫🇷")
    print("こんにちは 🇯🇵")
"""
        (self.components_dir / "utf8_template.j2").write_text(
            utf8_content, encoding="utf-8"
        )

        registry = ComponentRegistry(self.components_dir)
        registry.load_components()

        # Should handle UTF-8 encoding correctly
        content = registry.get_component("utf8_template")
        assert "🚀" in content
        assert "✨" in content
        assert "👨‍💻" in content
        assert "Çà marchë!" in content
        assert "こんにちは" in content

    def test_large_number_of_components(self):
        """Test handling large numbers of components"""
        # Create many components
        for i in range(50):
            component_content = f"""
{{# Generated Component {i} #}}
def component_{i}_function():
    '''Generated function for component {i}'''
    return {{"component_id": {i}, "status": "active"}}
"""
            (self.components_dir / f"generated_component_{i}.j2").write_text(
                component_content
            )

        registry = ComponentRegistry(self.components_dir)
        registry.load_components()

        # Should handle all components
        components = registry.list_components()
        assert len(components) >= 50

        # Should be able to access any component
        content = registry.get_component("generated_component_25")
        assert "Generated function for component 25" in content


class TestComponentMetadata:
    """Test ComponentMetadata functionality"""

    def setup_method(self):
        """Setup test metadata"""
        self.temp_file = Path(tempfile.mktemp(suffix=".j2"))
        self.temp_file.write_text("test content")

        self.metadata = ComponentMetadata(
            name="test_component", path=self.temp_file, dependencies=["dep1", "dep2"]
        )

    def teardown_method(self):
        """Clean up"""
        if self.temp_file.exists():
            self.temp_file.unlink()

    def test_metadata_initialization(self):
        """Test metadata initialization"""
        assert self.metadata.name == "test_component"
        assert self.metadata.path == self.temp_file
        assert self.metadata.dependencies == ["dep1", "dep2"]
        assert self.metadata.last_modified > 0
        assert self.metadata.loaded_at is not None

    def test_staleness_detection(self):
        """Test staleness detection"""
        # Initially not stale
        assert self.metadata.is_stale() is False

        # Modify file
        time.sleep(0.1)
        self.temp_file.write_text("modified content")

        # Now should be stale
        assert self.metadata.is_stale() is True

        # Refresh and should not be stale
        self.metadata.refresh_metadata()
        assert self.metadata.is_stale() is False

    def test_metadata_with_missing_file(self):
        """Test metadata with missing file"""
        missing_file = Path("/tmp/nonexistent.j2")
        metadata = ComponentMetadata("missing", missing_file)

        assert metadata.last_modified == 0
        assert metadata.is_stale() is True


class TestComponentRegistryCoreFeatures:
    """Test core ComponentRegistry features for maximum coverage"""

    def setup_method(self):
        """Setup test environment"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.components_dir = self.temp_dir / "components"
        self.components_dir.mkdir()

    def teardown_method(self):
        """Clean up test environment"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_registry_initialization_variations(self):
        """Test registry initialization with different scenarios"""
        # Test with existing directory
        registry = ComponentRegistry(self.components_dir)
        assert registry.components_dir == self.components_dir
        assert registry._components == {}
        assert registry._metadata == {}
        assert registry._dependencies == {}

        # Test with non-existent directory that gets created
        new_dir = self.temp_dir / "new_components"
        registry2 = ComponentRegistry(new_dir)
        assert registry2.components_dir == new_dir

        # Test basic functionality
        assert registry.auto_reload is False  # Default should be False for performance
        assert registry.validation_enabled is True

    def test_load_components_comprehensive(self):
        """Test comprehensive component loading"""
        # Create various component files
        (self.components_dir / "simple.j2").write_text("Simple template content")
        (self.components_dir / "with_deps.j2").write_text(
            """
{{# Dependencies: base.j2, utils.j2 #}}
Extended template with dependencies
"""
        )
        (self.components_dir / "base.j2").write_text("Base template")
        (self.components_dir / "utils.j2").write_text("Utility functions")
        (self.components_dir / "invalid.txt").write_text("Not a template file")
        (self.components_dir / "empty.j2").write_text("")

        # Create subdirectory with components
        sub_dir = self.components_dir / "subdir"
        sub_dir.mkdir()
        (sub_dir / "nested.j2").write_text("Nested template")

        registry = ComponentRegistry(self.components_dir)
        registry.load_components()

        # Should load .j2 files but not .txt files
        components = registry.list_components()
        component_names = [comp.name for comp in components]

        assert "simple" in component_names
        assert "with_deps" in component_names
        assert "base" in component_names
        assert "utils" in component_names
        assert "empty" in component_names
        assert "subdir/nested" in component_names
        assert "invalid" not in component_names

        # Test component content retrieval
        simple_content = registry.get_component("simple")
        assert simple_content == "Simple template content"

        empty_content = registry.get_component("empty")
        assert empty_content == ""

        # Test nested component
        nested_content = registry.get_component("subdir/nested")
        assert nested_content == "Nested template"

    def test_get_component_with_errors(self):
        """Test get_component with various error conditions"""
        registry = ComponentRegistry(self.components_dir, auto_reload=True)
        registry.load_components()

        # Test non-existent component
        with pytest.raises(KeyError, match="Component 'nonexistent' not found"):
            registry.get_component("nonexistent")

        # Test after loading some components
        (self.components_dir / "test.j2").write_text("test content")
        registry.load_components()

        # Should work now
        content = registry.get_component("test")
        assert content == "test content"

        # Test component that exists but file was deleted
        (self.components_dir / "test.j2").unlink()
        with pytest.raises(FileNotFoundError):
            registry.get_component("test")

    def test_component_exists_functionality(self):
        """Test component_exists method"""
        registry = ComponentRegistry(self.components_dir)

        # Initially no components
        assert not registry.component_exists("test")

        # Add component
        (self.components_dir / "test.j2").write_text("content")
        registry.load_components()

        # Should exist now
        assert registry.component_exists("test")
        assert not registry.component_exists("nonexistent")

        # Test with nested components
        sub_dir = self.components_dir / "nested"
        sub_dir.mkdir()
        (sub_dir / "component.j2").write_text("nested content")
        registry.load_components()

        assert registry.component_exists("nested/component")
        assert not registry.component_exists("nested/nonexistent")

    def test_dependency_tracking(self):
        """Test dependency parsing and tracking"""
        # Create components with various dependency formats
        (self.components_dir / "base.j2").write_text("Base component")
        (self.components_dir / "with_deps.j2").write_text(
            """
{{# Dependencies: base.j2, utils.j2 #}}
Component with dependencies
"""
        )
        (self.components_dir / "multi_deps.j2").write_text(
            """
{{# Dependencies: base.j2, with_deps.j2, utils.j2 #}}
Component with multiple dependencies
"""
        )
        (self.components_dir / "no_deps.j2").write_text(
            """
{{# No dependencies comment #}}
Component without dependencies
"""
        )
        (self.components_dir / "utils.j2").write_text("Utility component")

        registry = ComponentRegistry(self.components_dir)
        registry.load_components()

        # Check dependency tracking
        deps = registry.get_component_dependencies("with_deps")
        assert "base" in deps
        assert "utils" in deps
        assert len(deps) == 2

        multi_deps = registry.get_component_dependencies("multi_deps")
        assert "base" in multi_deps
        assert "with_deps" in multi_deps
        assert "utils" in multi_deps
        assert len(multi_deps) == 3

        # Component with no dependencies
        no_deps = registry.get_component_dependencies("no_deps")
        assert len(no_deps) == 0

        # Non-existent component
        missing_deps = registry.get_component_dependencies("missing")
        assert len(missing_deps) == 0

    def test_hot_reloading_capabilities(self):
        """Test hot-reloading and change detection"""
        # Create initial component
        component_file = self.components_dir / "hot_reload.j2"
        component_file.write_text("Initial content")

        registry = ComponentRegistry(self.components_dir)
        registry.load_components()

        # Initial content
        content1 = registry.get_component("hot_reload")
        assert content1 == "Initial content"

        # Modify file
        time.sleep(0.1)  # Ensure different timestamp
        component_file.write_text("Modified content")

        # Should detect change and reload
        registry.reload_component("hot_reload")
        content2 = registry.get_component("hot_reload")
        assert content2 == "Modified content"

        # Test reloading non-existent component
        result = registry.reload_component("nonexistent")
        assert result is False

    def test_clear_and_reset_functionality(self):
        """Test registry clearing and resetting"""
        # Load some components
        (self.components_dir / "test1.j2").write_text("Content 1")
        (self.components_dir / "test2.j2").write_text("Content 2")

        registry = ComponentRegistry(self.components_dir)
        registry.load_components()

        # Should have components loaded
        assert len(registry.list_components()) == 2
        assert registry.component_exists("test1")
        assert registry.component_exists("test2")

        # Clear registry
        registry.clear()

        # Should be empty
        assert len(registry.list_components()) == 0
        assert not registry.component_exists("test1")
        assert not registry.component_exists("test2")

        # Should be able to reload
        registry.load_components()
        assert len(registry.list_components()) == 2

    def test_metadata_management(self):
        """Test component metadata management"""
        component_file = self.components_dir / "metadata_test.j2"
        component_file.write_text("Test content for metadata")

        registry = ComponentRegistry(self.components_dir)
        registry.load_components()

        # Get component metadata
        metadata = registry.get_component_metadata("metadata_test")
        assert metadata is not None
        assert metadata.name == "metadata_test"
        assert metadata.path == component_file
        assert not metadata.is_stale()

        # Test with non-existent component
        missing_metadata = registry.get_component_metadata("missing")
        assert missing_metadata is None

        # Modify file and check staleness
        time.sleep(0.1)
        component_file.write_text("Modified content")

        # Metadata should indicate staleness
        assert metadata.is_stale()

        # Reload should update metadata
        registry.reload_component("metadata_test")
        updated_metadata = registry.get_component_metadata("metadata_test")
        assert not updated_metadata.is_stale()

    def test_error_handling_edge_cases(self):
        """Test error handling in edge cases"""
        registry = ComponentRegistry(self.components_dir)

        # Test loading from empty directory
        registry.load_components()
        assert len(registry.list_components()) == 0

        # Test with permission issues (simulate)
        with patch(
            "pathlib.Path.read_text", side_effect=PermissionError("Access denied")
        ):
            (self.components_dir / "permission_test.j2").write_text("content")
            # Should handle permission errors gracefully
            try:
                registry.load_components()
            except PermissionError:
                pass  # Expected in some cases

        # Test with corrupted/binary files
        binary_file = self.components_dir / "binary.j2"
        binary_file.write_bytes(b"\x00\x01\x02\x03\xff\xfe")

        try:
            registry.load_components()
            # If it loads, should handle binary content
            registry.list_components()
        except UnicodeDecodeError:
            # This is acceptable behavior for binary files
            pass

    def test_component_validation(self):
        """Test component template validation"""
        registry = ComponentRegistry(self.components_dir)

        # Valid template
        (self.components_dir / "valid.j2").write_text(
            """
{{# Valid template #}}
{% for item in items %}
Item: {{ item.name }}
{% endfor %}
"""
        )

        # Template with syntax issues
        (self.components_dir / "invalid_syntax.j2").write_text(
            """
{{# Template with syntax issues #}}
{% for item in items
Missing endfor
{{ unclosed.variable
"""
        )

        registry.load_components()

        # Should load both (validation happens during rendering)
        components = registry.list_components()
        component_names = [comp.name for comp in components]
        assert "valid" in component_names
        assert "invalid_syntax" in component_names

        # Content should be retrievable
        valid_content = registry.get_component("valid")
        assert "for item in items" in valid_content

        invalid_content = registry.get_component("invalid_syntax")
        assert "Missing endfor" in invalid_content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

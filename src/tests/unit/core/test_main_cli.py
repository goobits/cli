"""
Comprehensive tests for main CLI functionality in main.py

This unified test suite covers all main CLI functionality:
- CLI commands (build, init, upgrade)
- Configuration handling and validation
- Template generation and processing
- Utility functions and helpers
- Error conditions and edge cases

ORGANIZATION:
- Mock-based tests: Test business logic with controlled inputs/outputs
- Real generation tests: Test actual file generation and CLI execution
- Integration tests: Test end-to-end workflows

Merged from test_main_cli.py and test_main_cli_real.py to eliminate duplication
and provide comprehensive coverage in a single organized file.
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest
import typer
import yaml

from goobits_cli.commands.init import (
    generate_advanced_template,
    generate_api_client_template,
    generate_basic_template,
    generate_text_processor_template,
)
from goobits_cli.commands.utils import (
    backup_file,
    dependencies_to_json,
    dependency_to_dict,
    extract_version_from_pyproject,
    generate_setup_script,
    load_goobits_config,
    normalize_dependencies_for_template,
    update_pyproject_toml,
)
from goobits_cli.core.schemas import GoobitsConfigSchema
from goobits_cli.main import app, version_callback
from goobits_cli.universal.generator import UniversalGenerator

from .test_base import TestMainCLIBase

# ============================================================================
# CLI COMMANDS TESTS
# ============================================================================


class TestMainCLICommands(TestMainCLIBase):
    """Test the main CLI commands using CliRunner."""

    def test_cli_version_command(self):
        """Test --version command."""
        result = self.runner.invoke(app, ["--version"])

        assert result.exit_code == 0
        assert "goobits-cli" in result.stdout

    def test_cli_help_command(self):
        """Test --help command."""
        result = self.runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "build" in result.stdout
        assert "init" in result.stdout
        assert "upgrade" in result.stdout

    def test_build_command_basic(self):
        """Test basic build command functionality."""
        config_content = self.get_minimal_valid_config()
        config_path = self.create_test_config_file(config_content)

        # Mock the generator to return multiple files
        with patch.object(UniversalGenerator, "generate_all_files") as mock_gen:
            mock_gen.return_value = {
                "src/test_cli/generated_cli.py": "# Generated CLI code",
                "setup.sh": "#!/bin/bash\n# Setup script",
                "__executable__": ["setup.sh"],
            }

            result = self.runner.invoke(app, ["build", str(config_path)])

        assert result.exit_code == 0, f"Build failed: {result.stdout}\n{result.stdout}"
        assert "✅ Generated:" in result.stdout

    def test_build_command_config_not_found(self):
        """Test build command when config file doesn't exist."""
        non_existent_path = self.temp_dir / "nonexistent.yaml"

        result = self.runner.invoke(app, ["build", str(non_existent_path)])

        assert result.exit_code == 1
        # Exit code 1 indicates error occurred, output may be in stderr or empty

    def test_build_command_default_config_path(self):
        """Test build command using default config path."""
        config_content = self.get_minimal_valid_config()

        # Create config in current working directory
        original_cwd = Path.cwd()
        try:
            import os

            os.chdir(self.temp_dir)
            self.create_test_config_file(config_content)

            with patch.object(UniversalGenerator, "generate_all_files") as mock_gen:
                mock_gen.return_value = {
                    "src/test_cli/generated_cli.py": "# Generated CLI code",
                    "setup.sh": "#!/bin/bash\n# Setup script",
                }

                result = self.runner.invoke(app, ["build"])

            assert result.exit_code == 0
        finally:
            os.chdir(original_cwd)

    @patch("goobits_cli.universal.generator.UniversalGenerator.generate_all_files")
    def test_build_command_nodejs(self, mock_generate):
        """Test build command with Node.js language."""
        config_content = self.get_minimal_valid_config(
            package_name="node-test-cli", command_name="nodetestcli", language="nodejs"
        )
        config_path = self.create_test_config_file(config_content)

        mock_generate.return_value = {
            "cli.js": "// Generated Node.js CLI",
            "package.json": '{"name": "test"}',
            "setup.sh": "#!/bin/bash\n# Setup script",
        }

        result = self.runner.invoke(app, ["build", str(config_path)])

        assert result.exit_code == 0
        assert "Detected language: nodejs" in result.stdout

    @patch("goobits_cli.universal.generator.UniversalGenerator.generate_all_files")
    def test_build_command_typescript(self, mock_generate):
        """Test build command with TypeScript language."""
        config_content = self.get_minimal_valid_config(
            package_name="ts-test-cli", command_name="tstestcli", language="typescript"
        )
        config_path = self.create_test_config_file(config_content)

        mock_generate.return_value = {
            "cli.ts": "// Generated TypeScript CLI",
            "package.json": '{"name": "test"}',
            "setup.sh": "#!/bin/bash\n# Setup script",
        }

        result = self.runner.invoke(app, ["build", str(config_path)])

        assert result.exit_code == 0
        assert "Detected language: typescript" in result.stdout

    def test_build_command_default_templates(self):
        """Test build command with template system."""
        config_content = self.get_minimal_valid_config()
        config_path = self.create_test_config_file(config_content)

        with patch.object(UniversalGenerator, "generate_all_files") as mock_gen:
            mock_gen.return_value = {
                "src/test_cli/generated_cli.py": "# Generated CLI code",
                "setup.sh": "#!/bin/bash\n# Setup script",
            }

            result = self.runner.invoke(app, ["build", str(config_path)])

        assert result.exit_code == 0
        # Template system handles CLI generation

    def test_build_command_with_backup(self):
        """Test build command with --backup flag."""
        config_content = self.get_minimal_valid_config()
        config_path = self.create_test_config_file(config_content)

        with patch.object(UniversalGenerator, "generate_all_files") as mock_gen:
            mock_gen.return_value = {
                "src/test_cli/generated_cli.py": "# Generated CLI code",
                "setup.sh": "#!/bin/bash\n# Setup script",
            }

            result = self.runner.invoke(app, ["build", str(config_path), "--backup"])

        assert result.exit_code == 0
        # Should not show backup disabled message
        assert "💡 Backups disabled" not in result.stdout

    def test_build_command_handles_null_cli_hooks_path(self):
        """Regression: null cli_hooks_path must not crash template rendering."""
        config_content = """
package_name: test-cli
command_name: testcli
display_name: "Test CLI"
description: "A test CLI"
language: python
cli_hooks_path:

python:
  minimum_version: "3.8"

dependencies:
  required:
    - pipx

installation:
  pypi_name: "test-cli"

shell_integration:
  enabled: false
  alias: "testcli"

validation:
  check_api_keys: false
  check_disk_space: true
  minimum_disk_space_mb: 100

messages:
  install_success: "Installation completed successfully!"

cli:
  name: testcli
  tagline: "Test CLI tool"
  commands:
    hello:
      desc: "Say hello"
"""
        config_path = self.create_test_config_file(config_content)
        result = self.runner.invoke(app, ["build", str(config_path)])
        assert result.exit_code == 0

    def test_init_command_basic(self):
        """Test init command with basic template."""
        original_cwd = Path.cwd()
        try:
            import os

            os.chdir(self.temp_dir)

            result = self.runner.invoke(app, ["init", "my-test-project"])

            assert result.exit_code == 0
            assert "✅ Created goobits.yaml using 'basic' template" in result.stdout
            assert "my-test-project" in result.stdout

            # Check that file was created
            config_path = self.temp_dir / "goobits.yaml"
            assert config_path.exists()
            content = config_path.read_text()
            assert "my-test-project" in content
        finally:
            os.chdir(original_cwd)

    def test_init_command_with_template(self):
        """Test init command with specific template."""
        original_cwd = Path.cwd()
        try:
            import os

            os.chdir(self.temp_dir)

            result = self.runner.invoke(
                app, ["init", "--template", "advanced", "advanced-cli"]
            )

            assert result.exit_code == 0
            assert "✅ Created goobits.yaml using 'advanced' template" in result.stdout

            # Check that advanced template content is present
            config_path = self.temp_dir / "goobits.yaml"
            content = config_path.read_text()
            assert "advanced-cli" in content
            assert "command_groups:" in content
        finally:
            os.chdir(original_cwd)

    def test_init_command_project_name_from_directory(self):
        """Test init command using directory name for project name."""
        original_cwd = Path.cwd()
        try:
            import os

            os.chdir(self.temp_dir)

            result = self.runner.invoke(app, ["init"])

            assert result.exit_code == 0
            # Should use temp directory name as project name
            config_path = self.temp_dir / "goobits.yaml"
            content = config_path.read_text()
            assert self.temp_dir.name in content
        finally:
            os.chdir(original_cwd)

    def test_init_command_file_exists_no_force(self):
        """Test init command when file exists and no --force flag."""
        original_cwd = Path.cwd()
        try:
            import os

            os.chdir(self.temp_dir)

            # Create existing file
            config_path = self.temp_dir / "goobits.yaml"
            config_path.write_text("existing content")

            result = self.runner.invoke(app, ["init", "test-project"])

            assert result.exit_code == 1
            assert "already exists" in result.output
        finally:
            os.chdir(original_cwd)

    def test_init_command_file_exists_with_force(self):
        """Test init command when file exists with --force flag."""
        original_cwd = Path.cwd()
        try:
            import os

            os.chdir(self.temp_dir)

            # Create existing file
            config_path = self.temp_dir / "goobits.yaml"
            config_path.write_text("existing content")

            result = self.runner.invoke(app, ["init", "--force", "test-project"])

            assert result.exit_code == 0
            assert "✅ Created goobits.yaml using 'basic' template" in result.stdout
            # Should overwrite with new content
            content = config_path.read_text()
            assert "test-project" in content
            assert "existing content" not in content
        finally:
            os.chdir(original_cwd)

    def test_init_command_invalid_template(self):
        """Test init command with invalid template."""
        original_cwd = Path.cwd()
        try:
            import os

            os.chdir(self.temp_dir)

            result = self.runner.invoke(
                app, ["init", "--template", "invalid-template", "test-project"]
            )

            assert result.exit_code == 1
            assert "Unknown template" in result.output
        finally:
            os.chdir(original_cwd)

    @patch("goobits_cli.commands.upgrade.run_cached")
    def test_upgrade_command_basic(self, mock_subprocess):
        """Test basic upgrade command."""
        # Mock pipx --version check
        mock_subprocess.side_effect = [
            MagicMock(
                stdout="pipx 1.0.0", stderr="", returncode=0
            ),  # pipx version check
            MagicMock(
                stdout="Upgraded successfully", stderr="", returncode=0
            ),  # upgrade command
            MagicMock(
                stdout="goobits-cli 2.0.0", stderr="", returncode=0
            ),  # version check
        ]

        result = self.runner.invoke(app, ["upgrade"], input="y\n")

        assert result.exit_code == 0
        assert "Upgrade completed successfully" in result.stdout
        assert "Using pipx version" in result.stdout

    @patch("goobits_cli.commands.upgrade.run_cached")
    def test_upgrade_command_pipx_not_found(self, mock_subprocess):
        """Test upgrade command when pipx is not available."""
        # Simulate pipx not found
        mock_subprocess.side_effect = FileNotFoundError("pipx not found")

        result = self.runner.invoke(app, ["upgrade"])

        assert result.exit_code == 1
        assert "pipx is required" in result.output

    @patch("goobits_cli.commands.upgrade.run_cached")
    def test_upgrade_command_specific_version(self, mock_subprocess):
        """Test upgrade command with specific version."""
        mock_subprocess.side_effect = [
            MagicMock(stdout="pipx 1.0.0", stderr="", returncode=0),
            MagicMock(stdout="Installed successfully", stderr="", returncode=0),
            MagicMock(stdout="goobits-cli 1.5.0", stderr="", returncode=0),
        ]

        result = self.runner.invoke(app, ["upgrade", "--version", "1.5.0"], input="y\n")

        assert result.exit_code == 0
        assert "version 1.5.0 from PyPI" in result.stdout

    @patch("goobits_cli.commands.upgrade.run_cached")
    def test_upgrade_command_git_source(self, mock_subprocess):
        """Test upgrade command from git source."""
        mock_subprocess.side_effect = [
            MagicMock(stdout="pipx 1.0.0", stderr="", returncode=0),
            MagicMock(stdout="Installed successfully", stderr="", returncode=0),
            MagicMock(stdout="goobits-cli 2.0.0", stderr="", returncode=0),
        ]

        result = self.runner.invoke(app, ["upgrade", "--source", "git"], input="y\n")

        assert result.exit_code == 0
        assert "version latest from Git" in result.stdout

    @patch("goobits_cli.commands.upgrade.run_cached")
    def test_upgrade_command_local_source(self, mock_subprocess):
        """Test upgrade command from local source."""
        mock_subprocess.side_effect = [
            MagicMock(stdout="pipx 1.0.0", stderr="", returncode=0),
            MagicMock(stdout="Installed successfully", stderr="", returncode=0),
            MagicMock(stdout="goobits-cli 2.0.0", stderr="", returncode=0),
        ]

        result = self.runner.invoke(app, ["upgrade", "--source", "local"], input="y\n")

        assert result.exit_code == 0
        assert "local development version" in result.stdout

    @patch("goobits_cli.commands.upgrade.run_cached")
    def test_upgrade_command_dry_run(self, mock_subprocess):
        """Test upgrade command with dry run."""
        mock_subprocess.return_value = MagicMock(
            stdout="pipx 1.0.0", stderr="", returncode=0
        )

        result = self.runner.invoke(app, ["upgrade", "--dry-run"])

        assert result.exit_code == 0
        assert "Dry run - would execute:" in result.stdout
        # Should only call pipx version check, not actual upgrade
        assert len(mock_subprocess.call_args_list) == 1

    @patch("goobits_cli.commands.upgrade.run_cached")
    def test_upgrade_command_invalid_source(self, mock_subprocess):
        """Test upgrade command with invalid source."""
        mock_subprocess.return_value = MagicMock(
            stdout="pipx 1.0.0", stderr="", returncode=0
        )

        result = self.runner.invoke(app, ["upgrade", "--source", "invalid"])

        assert result.exit_code == 1
        assert "Unknown source" in result.output

    @patch("goobits_cli.commands.upgrade.run_cached")
    def test_upgrade_command_user_cancellation(self, mock_subprocess):
        """Test upgrade command when user cancels."""
        mock_subprocess.return_value = MagicMock(
            stdout="pipx 1.0.0", stderr="", returncode=0
        )

        result = self.runner.invoke(app, ["upgrade"], input="n\n")

        assert result.exit_code == 0
        assert "Upgrade cancelled" in result.stdout

    @patch("goobits_cli.commands.upgrade.run_cached")
    def test_upgrade_command_upgrade_failure(self, mock_subprocess):
        """Test upgrade command when upgrade fails."""
        mock_subprocess.side_effect = [
            MagicMock(stdout="pipx 1.0.0", stderr="", returncode=0),
            subprocess.CalledProcessError(1, "pipx upgrade", stderr="Upgrade failed"),
        ]

        result = self.runner.invoke(app, ["upgrade"], input="y\n")

        assert result.exit_code == 1
        assert "Upgrade failed" in result.output

    @patch("goobits_cli.commands.upgrade.run_cached")
    def test_upgrade_command_version_check_failure(self, mock_subprocess):
        """Test upgrade command when new version check fails."""
        mock_subprocess.side_effect = [
            MagicMock(
                stdout="pipx 1.0.0", stderr="", returncode=0
            ),  # pipx version check
            MagicMock(
                stdout="Upgraded successfully", stderr="", returncode=0
            ),  # upgrade command
            subprocess.CalledProcessError(
                1, "goobits --version"
            ),  # version check fails
        ]

        result = self.runner.invoke(app, ["upgrade"], input="y\n")

        assert result.exit_code == 0  # Should still succeed
        assert "New version information not available" in result.stdout

    @patch("goobits_cli.commands.upgrade.run_cached")
    def test_upgrade_command_unexpected_error(self, mock_subprocess):
        """Test upgrade command with unexpected error."""
        mock_subprocess.side_effect = [
            MagicMock(
                stdout="pipx 1.0.0", stderr="", returncode=0
            ),  # pipx version check
            Exception("Unexpected error"),  # Unexpected exception
        ]

        result = self.runner.invoke(app, ["upgrade"], input="y\n")

        assert result.exit_code == 1
        assert "Unexpected error during upgrade" in result.output

    @patch("goobits_cli.commands.upgrade.run_cached")
    def test_upgrade_command_pre_release_flag(self, mock_subprocess):
        """Test upgrade command with pre-release flag."""
        mock_subprocess.side_effect = [
            MagicMock(stdout="pipx 1.0.0", stderr="", returncode=0),
            MagicMock(stdout="Upgraded successfully", stderr="", returncode=0),
            MagicMock(stdout="goobits-cli 2.0.0b1", stderr="", returncode=0),
        ]

        result = self.runner.invoke(app, ["upgrade", "--pre"], input="y\n")

        assert result.exit_code == 0
        # Check that --pre flag was passed to pip
        upgrade_call = mock_subprocess.call_args_list[1]
        assert "--pip-args" in upgrade_call[0][0]
        assert "--pre" in upgrade_call[0][0]

    def test_init_all_template_types(self):
        """Test init command with all available template types."""
        original_cwd = Path.cwd()
        try:
            import os

            os.chdir(self.temp_dir)

            templates = ["basic", "advanced", "api-client", "text-processor"]

            for template in templates:
                # Clean up between iterations
                config_path = self.temp_dir / "goobits.yaml"
                if config_path.exists():
                    config_path.unlink()

                result = self.runner.invoke(
                    app, ["init", f"test-{template}", "--template", template]
                )

                assert result.exit_code == 0, f"Failed for template: {template}"
                assert (
                    config_path.exists()
                ), f"Config not created for template: {template}"

                content = config_path.read_text()
                assert f"test-{template}" in content

                # Verify template-specific content
                if template == "advanced":
                    assert "command_groups:" in content
                elif template == "api-client":
                    assert "api-key" in content
                elif template == "text-processor":
                    assert "uppercase" in content
        finally:
            os.chdir(original_cwd)

    @patch("goobits_cli.universal.engine.orchestrator.Orchestrator.generate_content")
    def test_build_command_generator_exception(self, mock_generate):
        """Test build command when generator raises an exception."""
        config_content = """
package_name: test-cli
command_name: testcli
display_name: "Test CLI"
description: "A test CLI"
language: python

python:
  minimum_version: "3.8"

dependencies:
  required:
    - pipx

installation:
  pypi_name: "test-cli"

shell_integration:
  enabled: false
  alias: "testcli"

validation:
  check_api_keys: false
  check_disk_space: true
  minimum_disk_space_mb: 100

messages:
  install_success: "Installation completed successfully!"

cli:
  name: testcli
  tagline: "Test CLI tool"
  commands:
    hello:
      desc: "Say hello"
      is_default: true
"""
        config_path = self.create_test_config_file(config_content)

        # Make generator raise an exception
        mock_generate.side_effect = Exception("Generator failed")

        result = self.runner.invoke(app, ["build", str(config_path)])

        # The CLI should catch the exception and exit with error code
        assert result.exit_code == 1

    def test_build_command_no_cli_section(self):
        """Test build command fails fast when CLI section is missing."""
        config_content = """
package_name: test-cli
command_name: testcli
display_name: "Test CLI"
description: "A test CLI"
language: python

python:
  minimum_version: "3.8"

dependencies:
  required:
    - pipx

installation:
  pypi_name: "test-cli"

shell_integration:
  enabled: false
  alias: "testcli"

validation:
  check_api_keys: false
  check_disk_space: true
  minimum_disk_space_mb: 100

messages:
  install_success: "Installation completed successfully!"
"""
        config_path = self.create_test_config_file(config_content)

        result = self.runner.invoke(app, ["build", str(config_path)])

        assert result.exit_code == 1
        assert "Configuration Validation Errors" in result.stderr
        assert "Field 'cli': Field required" in result.stderr
        assert "Generating CLI scripts..." not in result.stdout

    @patch("goobits_cli.commands.build.update_pyproject_toml")
    def test_build_command_pyproject_update_failure(self, mock_update):
        """Test build command when pyproject.toml update fails."""
        config_content = """
package_name: test-cli
command_name: testcli
display_name: "Test CLI"
description: "A test CLI"
language: python

python:
  minimum_version: "3.8"

dependencies:
  required:
    - pipx

installation:
  pypi_name: "test-cli"

shell_integration:
  enabled: false
  alias: "testcli"

validation:
  check_api_keys: false
  check_disk_space: true
  minimum_disk_space_mb: 100

messages:
  install_success: "Installation completed successfully!"

cli:
  name: testcli
  tagline: "Test CLI tool"
  commands:
    hello:
      desc: "Say hello"
      is_default: true
"""
        config_path = self.create_test_config_file(config_content)

        with patch.object(UniversalGenerator, "generate_all_files") as mock_gen:
            mock_gen.return_value = {
                "src/test_cli/generated_cli.py": "# Generated CLI code",
                "setup.sh": "#!/bin/bash\n# Setup script",
            }

            mock_update.return_value = False  # Simulate failure

            result = self.runner.invoke(app, ["build", str(config_path)])

        assert result.exit_code == 0  # Should still succeed
        assert "Could not update pyproject.toml automatically" in result.stdout

    def test_build_command_complex_package_structure(self):
        """Test build command with complex package structure."""
        config_content = """
package_name: complex-cli-tool
command_name: complex_cli
display_name: "Test CLI"
description: "A test CLI"
language: python

python:
  minimum_version: "3.8"

dependencies:
  required:
    - pipx

installation:
  pypi_name: "complex-cli-tool"

shell_integration:
  enabled: false
  alias: "complex_cli"

validation:
  check_api_keys: false
  check_disk_space: true
  minimum_disk_space_mb: 100

messages:
  install_success: "Installation completed successfully!"

cli:
  name: complex_cli
  tagline: "Test CLI tool"
  commands:
    hello:
      desc: "Say hello"
      is_default: true
"""
        config_path = self.create_test_config_file(config_content)

        with patch.object(UniversalGenerator, "generate_all_files") as mock_gen:
            mock_gen.return_value = {
                "src/complex_cli_tool/deep/nested/cli.py": "# Complex CLI code",
                "setup.sh": "#!/bin/bash\n# Setup script",
            }

            result = self.runner.invoke(app, ["build", str(config_path)])

        assert result.exit_code == 0
        assert "🎉 Build completed successfully!" in result.stdout


class TestFastVersionHelp(TestMainCLIBase):
    """Test the fast version and help check functionality."""

    @patch("sys.argv", ["goobits", "--version"])
    @patch("goobits_cli.main.__version__", "1.2.3")
    @patch("sys.exit")
    def test_fast_version_check(self, mock_exit):
        """Test fast version check before heavy imports."""
        # This is tricky to test since it modifies sys.argv
        # We'll test this indirectly through the CLI runner
        result = self.runner.invoke(app, ["--version"])

        assert result.exit_code == 0
        assert "goobits-cli" in result.stdout

    @patch("sys.argv", ["goobits", "--help"])
    @patch("sys.exit")
    def test_fast_help_check(self, mock_exit):
        """Test fast help check before heavy imports."""
        # Test through CLI runner
        result = self.runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "Commands" in result.stdout
        assert "build" in result.stdout


class TestYAMLConfigurationErrorConditions(TestMainCLIBase):
    """Test error conditions in YAML configuration parsing and validation."""

    def test_yaml_syntax_error_unclosed_quotes(self):
        """Test YAML parsing with unclosed quotes."""
        config_content = """
package_name: "test-cli
command_name: testcli
display_name: "Test CLI"
description: "A test CLI"
language: python
"""
        config_path = self.create_test_config_file(config_content)

        result = self.runner.invoke(app, ["build", str(config_path)])

        assert result.exit_code == 1
        # Should indicate YAML parsing error

    def test_yaml_syntax_error_invalid_indentation(self):
        """Test YAML parsing with invalid indentation."""
        config_content = """
package_name: test-cli
command_name: testcli
display_name: Test CLI
description: A test CLI
language: python
python:
minimum_version: "3.8"  # Wrong indentation
    maximum_version: "3.13"
"""
        config_path = self.create_test_config_file(config_content)

        result = self.runner.invoke(app, ["build", str(config_path)])

        assert result.exit_code == 1

    def test_yaml_syntax_error_mixed_tabs_spaces(self):
        """Test YAML parsing with mixed tabs and spaces."""
        # Create config with intentional tab/space mixing
        config_content = """package_name: test-cli
command_name: testcli
display_name: Test CLI
description: A test CLI
language: python
python:
\tminimum_version: "3.8"  # Tab character
    maximum_version: "3.13"  # Spaces
"""
        config_path = self.create_test_config_file(config_content)

        result = self.runner.invoke(app, ["build", str(config_path)])

        assert result.exit_code == 1

    def test_missing_required_root_fields(self):
        """Test configuration missing required root fields."""
        configs_missing_fields = [
            # Missing package_name
            """
command_name: testcli
display_name: Test CLI
description: A test CLI
language: python
""",
            # Missing command_name
            """
package_name: test-cli
display_name: Test CLI
description: A test CLI
language: python
""",
            # Missing display_name
            """
package_name: test-cli
command_name: testcli
description: A test CLI
language: python
""",
            # Missing description
            """
package_name: test-cli
command_name: testcli
display_name: Test CLI
language: python
""",
        ]

        for i, config_content in enumerate(configs_missing_fields):
            config_path = self.create_test_config_file(
                config_content, f"missing_field_{i}.yaml"
            )

            result = self.runner.invoke(app, ["build", str(config_path)])

            assert result.exit_code == 1, f"Config {i} should fail validation"

    def test_invalid_data_types_in_config(self):
        """Test configuration with invalid data types."""
        invalid_type_configs = [
            # package_name as number
            """
package_name: 123
command_name: testcli
display_name: Test CLI
description: A test CLI
language: python
""",
            # language as list
            """
package_name: test-cli
command_name: testcli
display_name: Test CLI
description: A test CLI
language: [python, nodejs]
""",
            # dependencies as string instead of object
            """
package_name: test-cli
command_name: testcli
display_name: Test CLI
description: A test CLI
language: python
dependencies: "click>=8.0"
""",
            # CLI commands as string instead of object
            """
package_name: test-cli
command_name: testcli
display_name: Test CLI
description: A test CLI
language: python
python:
  minimum_version: "3.8"
dependencies:
  required: []
installation:
  pypi_name: test-cli
shell_integration:
  enabled: false
validation:
  check_api_keys: false
  check_disk_space: true
  minimum_disk_space_mb: 100
messages:
  install_success: Success!
cli:
  name: testcli
  tagline: Test CLI
  commands: "hello world"
""",
        ]

        for i, config_content in enumerate(invalid_type_configs):
            config_path = self.create_test_config_file(
                config_content, f"invalid_type_{i}.yaml"
            )

            result = self.runner.invoke(app, ["build", str(config_path)])

            assert result.exit_code == 1, f"Config {i} should fail type validation"

    def test_yaml_with_duplicate_keys(self):
        """Test YAML configuration with duplicate keys."""
        config_content = """
package_name: test-cli
command_name: testcli
display_name: Test CLI
description: A test CLI
language: python
language: nodejs  # Duplicate key
"""
        config_path = self.create_test_config_file(config_content)

        result = self.runner.invoke(app, ["build", str(config_path)])

        # YAML parsers typically handle duplicate keys by using the last value
        # The validation should still work, but with the last value
        assert (
            result.exit_code == 1 or result.exit_code == 0
        )  # Depends on YAML parser behavior

    def test_yaml_with_invalid_unicode_characters(self):
        """Test YAML configuration with invalid unicode characters."""
        # Create file with invalid unicode byte sequences
        config_path = self.temp_dir / "invalid_unicode.yaml"
        with open(config_path, "wb") as f:
            f.write(
                b"""package_name: test-cli
command_name: testcli
display_name: Test CLI \xff\xfe
description: A test CLI
language: python
"""
            )

        result = self.runner.invoke(app, ["build", str(config_path)])

        assert result.exit_code == 1

    def test_extremely_large_yaml_file(self):
        """Test handling of extremely large YAML configuration files."""
        # Create a large configuration
        large_commands = {}
        for i in range(1000):
            large_commands[f"command_{i}"] = {
                "desc": f"Command {i} description",
                "args": [
                    {"name": f"arg_{j}", "desc": f"Argument {j}"} for j in range(10)
                ],
                "options": [
                    {"name": f"opt_{j}", "desc": f"Option {j}"} for j in range(10)
                ],
            }

        config_content = f"""
package_name: large-cli
command_name: largecli
display_name: Large CLI
description: A CLI with many commands
language: python
python:
  minimum_version: "3.8"
dependencies:
  required: []
installation:
  pypi_name: large-cli
shell_integration:
  enabled: false
validation:
  check_api_keys: false
  check_disk_space: true
  minimum_disk_space_mb: 100
messages:
  install_success: Success!
cli:
  name: largecli
  tagline: Large CLI
  commands: {yaml.dump(large_commands, default_flow_style=False)}
"""
        config_path = self.create_test_config_file(config_content)

        # Should handle large files without memory issues
        result = self.runner.invoke(app, ["build", str(config_path)])

        # Either succeeds or fails gracefully with appropriate error
        assert result.exit_code in [0, 1]

    def test_nested_yaml_structure_validation_errors(self):
        """Test validation errors in deeply nested YAML structures."""
        config_content = """
package_name: test-cli
command_name: testcli
display_name: Test CLI
description: A test CLI
language: python
python:
  minimum_version: "3.8"
dependencies:
  required: []
installation:
  pypi_name: test-cli
shell_integration:
  enabled: false
validation:
  check_api_keys: false
  check_disk_space: true
  minimum_disk_space_mb: 100
messages:
  install_success: Success!
cli:
  name: testcli
  tagline: Test CLI
  commands:
    hello:
      desc: Say hello
      args:
        - name: user
          desc: User to greet
          required: "invalid_boolean"  # Should be boolean
          type: invalid_type  # Invalid argument type
      options:
        - name: verbose
          desc: Verbose output
          type: invalid_option_type  # Invalid option type
          default: []  # Invalid default for string type
      subcommands:
        world:
          desc: 123  # Should be string
          invalid_field: value  # Unknown field
"""
        config_path = self.create_test_config_file(config_content)

        result = self.runner.invoke(app, ["build", str(config_path)])

        assert result.exit_code == 1

    def test_yaml_anchor_and_reference_errors(self):
        """Test YAML anchor and reference parsing errors."""
        config_content = """
package_name: test-cli
command_name: testcli
display_name: Test CLI
description: A test CLI
language: python

# Valid anchor
common_config: &common
  minimum_version: "3.8"
  maximum_version: "3.13"

python:
  <<: *common

# Invalid reference to non-existent anchor
nodejs:
  <<: *nonexistent_anchor
"""
        config_path = self.create_test_config_file(config_content)

        result = self.runner.invoke(app, ["build", str(config_path)])

        assert result.exit_code == 1

    def test_config_file_permission_denied(self):
        """Test handling of permission denied when reading config file."""
        config_content = """
package_name: test-cli
command_name: testcli
display_name: Test CLI
description: A test CLI
language: python
"""
        config_path = self.create_test_config_file(config_content)

        # Make file unreadable (may not work on all systems)
        import os

        try:
            os.chmod(str(config_path), 0o000)

            result = self.runner.invoke(app, ["build", str(config_path)])

            assert result.exit_code in [
                1,
                2,
            ]  # Accept either exit code for permission errors
        finally:
            # Restore permissions for cleanup
            try:
                os.chmod(str(config_path), 0o644)
            except (PermissionError, OSError):
                pass

    def test_config_file_is_directory(self):
        """Test error when config path points to a directory instead of file."""
        # Create a directory with the config name
        config_dir = self.temp_dir / "goobits.yaml"
        config_dir.mkdir()

        result = self.runner.invoke(app, ["build", str(config_dir)])

        assert result.exit_code == 1

    def test_config_file_empty(self):
        """Test handling of completely empty config file."""
        config_path = self.create_test_config_file("")

        result = self.runner.invoke(app, ["build", str(config_path)])

        assert result.exit_code == 1

    def test_config_file_only_comments(self):
        """Test handling of config file with only comments."""
        config_content = """
# This is a comment
# Another comment
# No actual configuration
"""
        config_path = self.create_test_config_file(config_content)

        result = self.runner.invoke(app, ["build", str(config_path)])

        assert result.exit_code == 1

    def test_invalid_enum_values(self):
        """Test configuration with invalid enum values."""
        config_content = """
package_name: test-cli
command_name: testcli
display_name: Test CLI
description: A test CLI
language: invalid_language  # Should be python, nodejs, or typescript
python:
  minimum_version: "3.8"
dependencies:
  required: []
installation:
  pypi_name: test-cli
shell_integration:
  enabled: false
validation:
  check_api_keys: false
  check_disk_space: true
  minimum_disk_space_mb: 100
messages:
  install_success: Success!
cli:
  name: testcli
  tagline: Test CLI
  commands:
    hello:
      desc: Say hello
      lifecycle: invalid_lifecycle  # Should be "simple" or "managed"
"""
        config_path = self.create_test_config_file(config_content)

        result = self.runner.invoke(app, ["build", str(config_path)])

        assert result.exit_code == 1

    def test_config_with_circular_references(self):
        """Test configuration with circular YAML references."""
        config_content = """
package_name: test-cli
command_name: testcli
display_name: Test CLI
description: A test CLI
language: python

# Create circular reference
a: &a
  b: *b
b: &b
  a: *a

python: *a  # Use circular reference
"""
        config_path = self.create_test_config_file(config_content)

        result = self.runner.invoke(app, ["build", str(config_path)])

        # Should either handle gracefully or fail with appropriate error
        assert result.exit_code == 1

    def test_config_exceeding_nesting_limits(self):
        """Test configuration with excessive nesting depth."""
        # Create deeply nested structure
        nested_structure = "value"
        for i in range(100):  # Very deep nesting
            nested_structure = {"level_" + str(i): nested_structure}

        config_content = f"""
package_name: test-cli
command_name: testcli
display_name: Test CLI
description: A test CLI
language: python
python:
  minimum_version: "3.8"
dependencies:
  required: []
installation:
  pypi_name: test-cli
shell_integration:
  enabled: false
validation:
  check_api_keys: false
  check_disk_space: true
  minimum_disk_space_mb: 100
messages:
  install_success: Success!
deep_nested: {yaml.dump(nested_structure, default_flow_style=False)}
"""
        config_path = self.create_test_config_file(config_content)

        result = self.runner.invoke(app, ["build", str(config_path)])

        # Should handle deep nesting or fail gracefully
        assert result.exit_code in [0, 1]

    def test_config_with_conflicting_field_values(self):
        """Test configuration with conflicting field values."""
        config_content = """
package_name: test-cli
command_name: testcli
display_name: Test CLI
description: A test CLI
language: python
python:
  minimum_version: "3.10"
  maximum_version: "3.8"  # Maximum less than minimum
dependencies:
  required: []
installation:
  pypi_name: test-cli
shell_integration:
  enabled: false
validation:
  check_api_keys: false
  check_disk_space: true
  minimum_disk_space_mb: -100  # Negative value
messages:
  install_success: Success!
cli:
  name: testcli
  tagline: Test CLI
  commands:
    hello:
      desc: Say hello
      args:
        - name: ""  # Empty name
          desc: Empty name argument
"""
        config_path = self.create_test_config_file(config_content)

        result = self.runner.invoke(app, ["build", str(config_path)])

        assert result.exit_code == 1


# ============================================================================
# CONFIGURATION TESTS
# ============================================================================


class TestMainCLIConfig(TestMainCLIBase):
    """Test suite for main CLI configuration functionality."""

    def test_load_goobits_config_success(self, basic_config_content):
        """Test successful loading of goobits configuration."""
        config_path = self.create_test_config_file(basic_config_content)

        config = load_goobits_config(config_path)

        assert isinstance(config, GoobitsConfigSchema)
        assert config.package_name == "test-cli"
        assert config.command_name == "testcli"
        assert config.language == "python"

    def test_load_goobits_config_file_not_found(self):
        """Test loading config when file doesn't exist."""
        non_existent_path = self.temp_dir / "nonexistent.yaml"

        with pytest.raises(typer.Exit):
            load_goobits_config(non_existent_path)

    def test_load_goobits_config_invalid_yaml(self):
        """Test loading config with invalid YAML."""
        config_path = self.create_test_config_file("invalid: yaml: content: [")

        with pytest.raises(typer.Exit):
            load_goobits_config(config_path)

    def test_load_goobits_config_validation_error(self):
        """Test loading config that fails validation."""
        invalid_config = "package_name: ''"  # Empty package name should fail validation
        config_path = self.create_test_config_file(invalid_config)

        with pytest.raises(typer.Exit):
            load_goobits_config(config_path)

    def test_normalize_dependencies_for_template(self, basic_config_content):
        """Test dependency normalization for templates."""
        config_path = self.create_test_config_file(basic_config_content)
        config = load_goobits_config(config_path)

        normalized = normalize_dependencies_for_template(config)

        assert isinstance(normalized, GoobitsConfigSchema)
        # Should be a deep copy, not the same object
        assert normalized is not config
        assert normalized.package_name == config.package_name

    def test_build_command_invalid_yaml_syntax(self):
        """Test build command with invalid YAML syntax."""
        invalid_config = "package_name: test\ninvalid: yaml: content: ["
        config_path = self.create_test_config_file(invalid_config)

        result = self.runner.invoke(app, ["build", str(config_path)])

        assert result.exit_code == 1
        assert "invalid: yaml: content: [" in result.output

    def test_build_command_missing_required_fields(self):
        """Test build command with missing required fields."""
        incomplete_config = "package_name: test-cli\n# Missing other required fields"
        config_path = self.create_test_config_file(incomplete_config)

        result = self.runner.invoke(app, ["build", str(config_path)])

        assert result.exit_code == 1
        assert "this required field to your configuration" in result.output

    def test_empty_and_whitespace_only_configs(self):
        """Test handling of empty and whitespace-only configs."""
        # Empty file
        empty_config_path = self.create_test_config_file("")
        result = self.runner.invoke(app, ["build", str(empty_config_path)])
        assert result.exit_code == 1

        # Whitespace only
        whitespace_config_path = self.create_test_config_file("   \n\t\n   ")
        result = self.runner.invoke(app, ["build", str(whitespace_config_path)])
        assert result.exit_code == 1


# ============================================================================
# TEMPLATE TESTS
# ============================================================================


class TestMainCLITemplates(TestMainCLIBase):
    """Test suite for template generation functionality."""

    def test_generate_basic_template(self):
        """Test generation of basic template."""
        template = generate_basic_template("my-awesome-cli")

        assert "package_name: my-awesome-cli" in template
        assert "command_name: my_awesome_cli" in template
        assert "language: python" in template
        assert "hello:" in template

    def test_generate_advanced_template(self):
        """Test generation of advanced template."""
        template = generate_advanced_template("advanced-cli")

        assert "package_name: advanced-cli" in template
        assert "command_name: advanced_cli" in template
        assert "process:" in template
        assert "convert:" in template
        assert "command_groups:" in template

    def test_generate_api_client_template(self):
        """Test generation of API client template."""
        template = generate_api_client_template("api-client")

        assert "package_name: api-client" in template
        assert "get:" in template
        assert "post:" in template
        assert "api-key" in template

    def test_generate_text_processor_template(self):
        """Test generation of text processor template."""
        template = generate_text_processor_template("text-tool")

        assert "package_name: text-tool" in template
        assert "process:" in template
        assert "count:" in template
        assert "uppercase" in template


class TestGenerateSetupScript(TestMainCLIBase):
    """Test setup script generation functionality."""

    @patch("goobits_cli.commands.utils.Environment")
    @patch("goobits_cli.commands.utils.FileSystemLoader")
    def test_generate_setup_script_basic(self, mock_loader, mock_env):
        """Test basic setup script generation."""
        # Create a mock config
        from goobits_cli.core.schemas import GoobitsConfigSchema

        config_data = {
            "package_name": "test-cli",
            "command_name": "testcli",
            "display_name": "Test CLI",
            "description": "A test CLI",
            "language": "python",
            "python": {"minimum_version": "3.8"},
            "dependencies": {"required": ["pipx"]},
            "installation": {"pypi_name": "test-cli"},
            "shell_integration": {"enabled": False, "alias": "testcli"},
            "validation": {
                "check_api_keys": False,
                "check_disk_space": True,
                "minimum_disk_space_mb": 100,
            },
            "messages": {"install_success": "Installation completed successfully!"},
            "cli": {"name": "testcli", "tagline": "Test CLI tool", "commands": {}},
        }
        config = GoobitsConfigSchema(**config_data)

        # Mock the template rendering
        mock_template = MagicMock()
        mock_template.render.return_value = "#!/bin/bash\n# Generated setup script"
        mock_env_instance = MagicMock()
        mock_env_instance.get_template.return_value = mock_template
        mock_env.return_value = mock_env_instance

        # Create a pyproject.toml for version extraction
        pyproject_path = self.temp_dir / "pyproject.toml"
        pyproject_path.write_text('[project]\nversion = "1.0.0"')

        result = generate_setup_script(config, self.temp_dir)

        assert result == "#!/bin/bash\n# Generated setup script"
        mock_template.render.assert_called_once()
        # Check that template variables include expected keys
        call_args = mock_template.render.call_args[1]
        assert "package_name" in call_args
        assert "version" in call_args
        assert call_args["package_name"] == "test-cli"


# ============================================================================
# UTILITY TESTS
# ============================================================================


class TestMainCLIUtils(TestMainCLIBase):
    """Test suite for utility functions in main CLI."""

    def test_version_callback_triggers_exit(self):
        """Test that version_callback triggers typer.Exit when True."""
        with pytest.raises(typer.Exit):
            version_callback(True)

    def test_version_callback_no_action_when_false(self):
        """Test that version_callback does nothing when False."""
        # Should not raise any exception
        result = version_callback(False)
        assert result is None

    def test_dependency_to_dict_string(self):
        """Test converting string dependency to dict."""
        result = dependency_to_dict("pipx")
        assert result == {"name": "pipx", "type": "command"}

    def test_dependency_to_dict_dict(self):
        """Test converting dict dependency to dict."""
        dep_dict = {"name": "python", "version": ">=3.8"}
        result = dependency_to_dict(dep_dict)
        assert result == dep_dict

    def test_dependency_to_dict_object_with_model_dump(self):
        """Test converting object with model_dump to dict."""
        mock_dep = MagicMock()
        mock_dep.model_dump.return_value = {"name": "test", "version": "1.0"}

        result = dependency_to_dict(mock_dep)
        assert result == {"name": "test", "version": "1.0"}

    def test_dependency_to_dict_fallback(self):
        """Test dependency_to_dict fallback for unknown types."""
        result = dependency_to_dict(123)
        assert result == {"name": "123", "type": "command"}

    def test_dependency_to_dict_with_dict_method(self):
        """Test dependency_to_dict with object that has dict method."""
        mock_dep = MagicMock()
        mock_dep.dict.return_value = {"name": "test", "version": "1.0"}
        # Remove model_dump to force dict method usage
        del mock_dep.model_dump

        result = dependency_to_dict(mock_dep)
        assert result == {"name": "test", "version": "1.0"}

    def test_dependencies_to_json(self):
        """Test converting dependencies list to JSON."""
        deps = ["pipx", {"name": "python", "version": ">=3.8"}]
        result = dependencies_to_json(deps)

        import json

        parsed = json.loads(result)
        assert len(parsed) == 2
        assert parsed[0] == {"name": "pipx", "type": "command"}
        assert parsed[1] == {"name": "python", "version": ">=3.8"}

    def test_extract_version_from_pyproject_not_found(self):
        """Test version extraction when pyproject.toml doesn't exist."""
        result = extract_version_from_pyproject(self.temp_dir)
        assert result == "unknown"

    def test_extract_version_from_pyproject_poetry_format(self):
        """Test version extraction from Poetry format."""
        pyproject_content = """
[tool.poetry]
name = "test-package"
version = "1.2.3"
"""
        pyproject_path = self.temp_dir / "pyproject.toml"
        with open(pyproject_path, "w") as f:
            f.write(pyproject_content)

        result = extract_version_from_pyproject(self.temp_dir)
        assert result == "1.2.3"

    def test_extract_version_from_pyproject_pep621_format(self):
        """Test version extraction from PEP 621 format."""
        pyproject_content = """
[project]
name = "test-package"
version = "3.0.0"
"""
        pyproject_path = self.temp_dir / "pyproject.toml"
        with open(pyproject_path, "w") as f:
            f.write(pyproject_content)

        result = extract_version_from_pyproject(self.temp_dir)
        assert result == "3.0.0"

    def test_extract_version_from_pyproject_parse_error(self):
        """Test version extraction with invalid TOML."""
        pyproject_path = self.temp_dir / "pyproject.toml"
        with open(pyproject_path, "w") as f:
            f.write("invalid toml content [")

        result = extract_version_from_pyproject(self.temp_dir)
        assert result == "unknown"

    def test_extract_version_from_pyproject_no_version(self):
        """Test version extraction when version field is missing."""
        pyproject_content = """
[project]
name = "test-package"
description = "A test package"
"""
        pyproject_path = self.temp_dir / "pyproject.toml"
        with open(pyproject_path, "w") as f:
            f.write(pyproject_content)

        result = extract_version_from_pyproject(self.temp_dir)
        assert result == "unknown"

    def test_backup_file_creates_backup(self):
        """Test that backup_file creates a backup when requested."""
        test_file = self.temp_dir / "test.txt"
        test_file.write_text("original content")

        backup_path = backup_file(test_file, create_backup=True)

        assert backup_path is not None
        assert backup_path.exists()
        assert backup_path.name == "test.txt.bak"
        assert backup_path.read_text() == "original content"

    def test_backup_file_no_backup_when_disabled(self):
        """Test that backup_file doesn't create backup when disabled."""
        test_file = self.temp_dir / "test.txt"
        test_file.write_text("original content")

        backup_path = backup_file(test_file, create_backup=False)

        assert backup_path is None

    def test_backup_file_nonexistent_file(self):
        """Test backup_file with non-existent file."""
        non_existent = self.temp_dir / "nonexistent.txt"

        backup_path = backup_file(non_existent, create_backup=True)

        assert backup_path is None

    @patch("shutil.copy2")
    def test_backup_file_copy_failure(self, mock_copy):
        """Test backup_file when copy operation fails."""
        test_file = self.temp_dir / "test.txt"
        test_file.write_text("original content")

        mock_copy.side_effect = PermissionError("Copy failed")

        # Should raise exception since copy2 failed
        with pytest.raises(PermissionError):
            backup_file(test_file, create_backup=True)

    @patch("toml.load")
    @patch("toml.dump")
    def test_update_pyproject_toml_poetry_format(self, mock_load, mock_dump):
        """Test updating pyproject.toml in Poetry format."""
        pyproject_path = self.temp_dir / "pyproject.toml"
        pyproject_path.touch()

        mock_load.return_value = {"tool": {"poetry": {"scripts": {}}}}

        with patch("builtins.open", mock_open()):
            result = update_pyproject_toml(
                self.temp_dir, "test_package", "testcli", "generated_cli.py"
            )

        assert result is True
        mock_load.assert_called_once()
        mock_dump.assert_called_once()

    def test_update_pyproject_toml_no_file(self):
        """Test updating pyproject.toml when file doesn't exist."""
        result = update_pyproject_toml(
            self.temp_dir, "test_package", "testcli", "generated_cli.py"
        )

        assert result is False

    def test_update_pyproject_toml_exception_handling(self):
        """Test update_pyproject_toml with various exceptions."""
        pyproject_path = self.temp_dir / "pyproject.toml"
        pyproject_path.write_text('[project]\nversion = "1.0.0"')

        # Test with file read error
        with patch("builtins.open", side_effect=PermissionError("Access denied")):
            result = update_pyproject_toml(
                self.temp_dir, "test_package", "testcli", "generated_cli.py"
            )
            assert result is False

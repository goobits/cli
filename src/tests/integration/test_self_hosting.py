"""Keep committed self-hosting outputs in sync with the documented build."""

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def self_hosted_build(tmp_path_factory):
    root = Path(__file__).resolve().parents[3]
    output = tmp_path_factory.mktemp("self-hosting")
    # The setup generator reads the project version from the output directory.
    (output / "pyproject.toml").write_bytes((root / "pyproject.toml").read_bytes())
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "goobits_cli.main",
            "build",
            str(root / "goobits.yaml"),
            "--output-dir",
            str(output),
        ],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return root, output


@pytest.mark.parametrize(
    "path", ["src/goobits_cli/generated_cli.py", "scripts/setup.sh"]
)
def test_committed_self_hosting_output_matches_build(self_hosted_build, path):
    root, output = self_hosted_build
    assert (root / path).read_bytes() == (output / path).read_bytes(), (
        f"{path} is stale; run goobits build goobits.yaml"
    )

"""Test that examples in our documentation have correct matching outputs."""
import os
import sys
import subprocess
import fileinput
from pathlib import Path

import pytest


@pytest.fixture()
def example_name():
    """Name of the example - used for both the code and output text file."""
    return None


def run_script(script_path):
    """Run python script and return output as a string."""
    proc = subprocess.Popen([sys.executable, script_path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        out_str, _ = proc.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        out_str, _ = proc.communicate()

    return out_str


@pytest.mark.parametrize("example_name", ["example_adapter", "example_as_needed", "example_default"])
def test_examples(example_name):
    """Test that examples used in our documentation have expected output."""
    cur_dir = Path(os.path.dirname(os.path.realpath(__file__)))
    script_path = cur_dir / f"{example_name}.py"

    logs = run_script(script_path)
    script_output = logs.decode().splitlines()

    expected_lines = [line.rstrip() for line in fileinput.input(cur_dir / f"{example_name}.txt")]
    assert script_output == expected_lines

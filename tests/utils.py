"""Utility functions used in the tests."""


def generate_lines(count):
    """Generate multiple lines of "log output" for test comparisons."""
    lines = []
    for i in range(count):
        lines.append(f"Line {i + 1}")
    return lines

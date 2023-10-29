"""Utility functions used in the tests."""
import inspect


def generate_lines(count):
    lines = []
    for i in range(count):
        lines.append(f"Line {i + 1}")
    return lines

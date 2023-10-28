"""Utility functions used in the tests."""
import inspect


def get_test_name():
    """Return the function name of the test that called this function."""
    # Stack[0] refers to this function, while stack[1] refers to the function (one higher in the stack) that called it.
    return inspect.stack()[1].function


def generate_lines(count):
    lines = []
    for i in range(count):
        lines.append(f"Line {i + 1}")
    return lines

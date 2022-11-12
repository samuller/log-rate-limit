import time
import inspect
import logging

from log_rate_limit import RateLimitFilter, rate_limit


def get_test_name():
    """Return the function name of the test that called this function."""
    # Stack[0] refers to this function, while stack[1] refers to the function (one higher in the stack) that called it.
    return inspect.stack()[1].function


def generate_lines(count):
    lines = []
    for i in range(count):
        lines.append(f"Line {i+1}")
    return lines


def test_log_limit_all_unaffected(caplog) -> None:
    """Test that all "normal" logs (no stream_id) are, by default, unaffected by log limiting."""
    # Setup logging for this test.
    _log = logging.getLogger(get_test_name())
    _log.setLevel(logging.INFO)
    # Setup filter 1-second limit which should only affect logs with stream_ids.
    _log.addFilter(RateLimitFilter(1))

    _log.info("Line 1")
    _log.info("Line 2")
    _log.info("Line 3", extra=rate_limit(stream_id=None))
    time.sleep(1.1)
    _log.info("Line 4")
    assert "___" not in caplog.text
    assert all([line in caplog.text for line in generate_lines(3)])


def test_log_limit_filter_all(caplog) -> None:
    """Test log limiting applied to all logs."""
    # Setup logging for this test.
    _log = logging.getLogger(get_test_name())
    _log.setLevel(logging.INFO)
    # Setup filter so all logs have a 1-second limit.
    _log.addFilter(RateLimitFilter(1, filter_all=True))

    # All logs containing "___" are expected to be skipped.
    _log.info("Line 1")
    _log.info("___")
    # Example: all logs default to stream_id=None.
    _log.info("___", extra=rate_limit(stream_id=None))
    # Example: rate_limit() is just a short-hand for creating an dict for the "extra" parameter.
    _log.info("___", extra={"stream_id": None})
    # Example: how to combine out rate_limit() with other extra values.
    _log.info("___", extra={**rate_limit(stream_id=None), "other_field": "other_value"})
    time.sleep(1.1)
    _log.info("Line 2")
    _log.info("___")
    assert "___" not in caplog.text
    assert all([line in caplog.text for line in generate_lines(2)])


def test_log_limit_streams(caplog) -> None:
    """Test that log limiting applies separately to different streams."""
    # Setup logging.
    _log = logging.getLogger(get_test_name())
    _log.setLevel(logging.INFO)

    # Setup filter so logs with stream-ids have a 1-second limit.
    _log.addFilter(RateLimitFilter(1))

    # All logs containing "___" are expected to be skipped.
    _log.info("Line 1", extra=rate_limit(stream_id="stream1"))
    _log.info("Line 2", extra=rate_limit(stream_id="stream2"))
    _log.info("stream1 ___", extra=rate_limit(stream_id="stream1"))
    _log.info("stream2 ___", extra=rate_limit(stream_id="stream2"))
    time.sleep(1.1)
    _log.info("Line 3", extra=rate_limit(stream_id="stream1"))
    _log.info("stream1 ___", extra=rate_limit(stream_id="stream1"))
    _log.info("Line 4", extra=rate_limit(stream_id="stream2"))
    _log.info("stream2 ___", extra=rate_limit(stream_id="stream2"))
    assert "___" not in caplog.text
    assert all([line in caplog.text for line in generate_lines(4)])


def test_log_limit_dynamic_min_time_sec(caplog):
    """Test that the min_time_sec value can be dynamically changed per-stream."""
    # Setup logging.
    _log = logging.getLogger(get_test_name())
    _log.setLevel(logging.INFO)

    # Setup filter so logs with stream-ids have a 1-second limit.
    _log.addFilter(RateLimitFilter(1))

    # All logs containing "___" are expected to be skipped.
    _log.info("Line 1", extra=rate_limit(stream_id="stream1"))
    # Test default limit first.
    _log.info("___", extra=rate_limit(stream_id="stream1"))
    time.sleep(1.1)
    _log.info("Line 2", extra=rate_limit(stream_id="stream2"))
    # Dynamically change min_time_sec.
    _log.info("Line 3", extra=rate_limit(stream_id="stream1", min_time_sec=3))
    _log.info("___", extra=rate_limit(stream_id="stream1"))
    time.sleep(1.1)
    # Second stream remains unaffected.
    _log.info("Line 4", extra=rate_limit(stream_id="stream2"))
    _log.info("___", extra=rate_limit(stream_id="stream1"))
    time.sleep(2)  # Already had 1.1 second wait, so this totals 3.1.
    _log.info("Line 5", extra=rate_limit(stream_id="stream1"))
    time.sleep(1.1)
    # Test that change to min_time_sec only applied in one instance.
    _log.info("Line 6", extra=rate_limit(stream_id="stream1"))

    assert "___" not in caplog.text
    assert all([line in caplog.text for line in generate_lines(6)])


def test_log_limit_summary(caplog):
    """Test the summary functionality."""
    # Setup logging.
    _log = logging.getLogger(get_test_name())
    _log.setLevel(logging.INFO)

    # Setup to filter all logs with 1-second limit.
    _log.addFilter(RateLimitFilter(1, filter_all=True, summary=True))

    _log.info("Line 1")
    # 3 skipped logs.
    _log.info("___")
    _log.info("___")
    _log.info("___")
    time.sleep(1.1)
    _log.info("Line 2")
    _log.info("___")
    assert "___" not in caplog.text
    assert all([line in caplog.text for line in generate_lines(2)])
    assert "\n+ skipped 3 logs due to rate-limiting" in caplog.text


def test_log_limit_allow_next_n(caplog):
    """Test the summary functionality."""
    # Setup logging.
    _log = logging.getLogger(get_test_name())
    _log.setLevel(logging.INFO)

    # Setup to filter all logs with 1-second limit.
    _log.addFilter(RateLimitFilter(1, filter_all=True, allow_next_n=2))

    _log.info("Line 1")
    _log.info("Line 2")
    _log.info("Line 3")
    _log.info("___")
    _log.info("___")
    time.sleep(1.1)
    _log.info("Line 4")
    _log.info("Line 5")
    _log.info("Line 6")
    _log.info("___")
    assert "___" not in caplog.text
    assert all([line in caplog.text for line in generate_lines(6)])

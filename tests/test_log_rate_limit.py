import time
import logging
from unittest.mock import patch

from log_rate_limit import StreamRateLimitFilter, RateLimit, DefaultSID

from utils import get_test_name, generate_lines


def test_log_limit_default_unaffected(caplog) -> None:
    """Test that by default most "normal" logs (no stream_id, not in a loop) are unaffected by log limiting."""
    # Setup logging for this test.
    _log = logging.getLogger(get_test_name())
    _log.setLevel(logging.INFO)
    # Setup filter 1-second limit which should only affect logs with stream_ids.
    _log.addFilter(StreamRateLimitFilter(1))

    _log.info("Line 1")
    _log.info("Line 2")
    _log.info("Line 3")
    for _ in range(5):
        _log.info("Line 4")
    time.sleep(1.1)
    _log.info("Line 5")
    # Check that filtering is disabled when stream_id is None.
    for i in range(2):
        # Changing message to avoid duplicate check from failing (and we know, from the implementation, that the
        # message itself has no affect on filtering).
        _log.info(f"Line {6+i}", extra=RateLimit(stream_id=None))

    assert "___" not in caplog.text
    assert all([line in caplog.text for line in generate_lines(7)])
    # Confirm there are no duplicated log lines at all.
    log_lines = caplog.text.splitlines()
    assert len(log_lines) == len(set(log_lines))


def test_log_limit_filter_line_no(caplog) -> None:
    """Test log limiting applied separately to each unique log on a different line."""
    # Setup logging for this test.
    _log = logging.getLogger(get_test_name())
    _log.setLevel(logging.INFO)
    # Setup filter so all logs have a 1-second limit.
    _log.addFilter(StreamRateLimitFilter(1, default_stream_id=DefaultSID.FILE_LINE_NO))

    for _ in range(5):
        _log.info("Line 1")
    for _ in range(5):
        _log.info("Line 2")
    for _ in range(5):
        _log.info("Line 3")

    assert all([line in caplog.text for line in generate_lines(3)])
    log_lines = caplog.text.splitlines()
    # Confirm there are no duplicated log lines at all.
    assert len(log_lines) == len(set(log_lines))


def test_log_limit_filter_log_message(capsys) -> None:
    """Test log limiting applied separately to each unique log message (but ignoring timestamps, etc.)."""
    # Setup logging for this test.
    _log = logging.getLogger(get_test_name())
    # logging.Formatter
    _log.setLevel(logging.INFO)
    formatter = logging.Formatter("[%(asctime)s %(levelname)s %(filename)s.%(name)s:%(lineno)s] %(message)s")
    # StreamHandler defaults output to stderr.
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    # Add filter specifically to formatted handler so we can confirm continuously changing timestamps have no effect
    # on rate-limiting of log messages.
    console_handler.addFilter(StreamRateLimitFilter(1, default_stream_id=DefaultSID.LOG_MESSAGE))
    _log.addHandler(console_handler)

    for _ in range(5):
        _log.info("Line %d", 1)
        _log.info("Line 1")
    for _ in range(5):
        _log.info("Line 2")
    for i in range(3):
        # Check that changed messages are not rate-limited.
        _log.info(f"Line {3 + i}")

    # Fetch console_handler's output to stderr.
    log_full = capsys.readouterr().err
    # We print the same output again since fetching it actually wipes the buffer and we still want it to appear
    # whenever pytest would usually show it (when tests fail or the "-rP" argument is added). However, this will put
    # it on stdout instead of stderr.
    print(log_full)

    assert all([line in log_full for line in generate_lines(5)])
    log_lines = log_full.splitlines()
    # Ignore everything before the closing bracket so we only look at the actual message (as the rate-limiting
    # should have done).
    log_lines = [" ".join(line.split("]")[1:]) for line in log_lines]
    # Confirm there are no duplicated log lines at all.
    assert len(log_lines) == len(set(log_lines))


# We add this patch to every test that uses "extra=RateLimit(...)" so that we can expand meaningfulness of code
# coverage. See _test_default_overrides() function in log_rate_limit.py for more details.
@patch("log_rate_limit.log_rate_limit.TEST_MODE", True)
def test_log_limit_filter_undefined(caplog) -> None:
    """Test log limiting applied to all logs without stream_ids."""
    # Setup logging for this test.
    _log = logging.getLogger(get_test_name())
    _log.setLevel(logging.INFO)
    # Setup to filter all logs in the same stream without needing to define a stream_id each time.
    _log.addFilter(StreamRateLimitFilter(1, default_stream_id=DefaultSID.NONE, filter_undefined=True))

    # All logs containing "___" are expected to be skipped.
    _log.info("Line 1")
    _log.info("___")
    # Example: all logs default to stream_id=None.
    _log.info("___", extra=RateLimit(stream_id=None))
    # Example: RateLimit() is just a short-hand for creating a dict for the "extra" parameter.
    _log.info("___", extra={"stream_id": None})
    # Example: how to combine our RateLimit() with other extra values.
    _log.info("___", extra={**RateLimit(stream_id=None), "other_field": "other_value"})
    time.sleep(1.1)
    _log.info("Line 2")
    _log.info("___")

    assert "___" not in caplog.text
    assert all([line in caplog.text for line in generate_lines(2)])


@patch("log_rate_limit.log_rate_limit.TEST_MODE", True)
def test_log_limit_streams(caplog) -> None:
    """Test that log limiting applies separately to different streams."""
    # Setup logging.
    _log = logging.getLogger(get_test_name())
    _log.setLevel(logging.INFO)

    # Setup filter so logs with stream-ids have a 1-second limit.
    _log.addFilter(StreamRateLimitFilter(1, default_stream_id=DefaultSID.NONE))

    # All logs containing "___" are expected to be skipped.
    _log.info("Line 1", extra=RateLimit(stream_id="stream1"))
    _log.info("Line 2", extra=RateLimit(stream_id="stream2"))
    _log.info("stream1 ___", extra=RateLimit(stream_id="stream1"))
    _log.info("stream2 ___", extra=RateLimit(stream_id="stream2"))
    time.sleep(1.1)
    _log.info("Line 3", extra=RateLimit(stream_id="stream1"))
    _log.info("stream1 ___", extra=RateLimit(stream_id="stream1"))
    _log.info("Line 4", extra=RateLimit(stream_id="stream2"))
    _log.info("stream2 ___", extra=RateLimit(stream_id="stream2"))

    assert "___" not in caplog.text
    assert all([line in caplog.text for line in generate_lines(4)])


@patch("log_rate_limit.log_rate_limit.TEST_MODE", True)
def test_log_limit_dynamic_period_sec(caplog):
    """Test that the period_sec value can be dynamically changed per-stream."""
    # Setup logging.
    _log = logging.getLogger(get_test_name())
    _log.setLevel(logging.INFO)

    # Setup filter so logs with stream-ids have a 1-second limit.
    _log.addFilter(StreamRateLimitFilter(1, default_stream_id=DefaultSID.NONE))

    # All logs containing "___" are expected to be skipped.
    _log.info("Line 1", extra=RateLimit(stream_id="stream1"))
    # Test default limit first.
    _log.info("___", extra=RateLimit(stream_id="stream1"))
    time.sleep(1.1)
    _log.info("Line 2", extra=RateLimit(stream_id="stream2"))
    # Dynamically change period_sec.
    _log.info("Line 3", extra=RateLimit(stream_id="stream1", period_sec=3))
    _log.info("___", extra=RateLimit(stream_id="stream1"))
    time.sleep(1.1)
    # Second stream remains unaffected.
    _log.info("Line 4", extra=RateLimit(stream_id="stream2"))
    _log.info("___", extra=RateLimit(stream_id="stream1"))
    time.sleep(2)  # Already had 1.1 second wait, so this totals 3.1.
    _log.info("Line 5", extra=RateLimit(stream_id="stream1"))
    time.sleep(1.1)
    # Test that change to period_sec only applied in one instance.
    _log.info("Line 6", extra=RateLimit(stream_id="stream1"))

    assert "___" not in caplog.text
    assert all([line in caplog.text for line in generate_lines(6)])


@patch("log_rate_limit.log_rate_limit.TEST_MODE", True)
def test_log_limit_summary(caplog):
    """Test the summary functionality."""
    # Setup logging.
    _log = logging.getLogger(get_test_name())
    _log.setLevel(logging.INFO)

    # Setup to filter all logs in the same stream without needing to define a stream_id each time.
    _log.addFilter(StreamRateLimitFilter(1, default_stream_id=DefaultSID.NONE, filter_undefined=True, summary=True))

    _log.info("Line 1")
    # 3 skipped logs.
    _log.info("___")
    _log.info("___")
    _log.info("___")
    time.sleep(1.1)
    _log.info("Line 2")
    # 2 skipped logs.
    _log.info("___")
    _log.info("___")
    time.sleep(1.1)
    # Dynamically override summary so we don't print it.
    _log.info("Line 3", extra=RateLimit(summary=False))
    _log.info("___")
    time.sleep(1.1)
    # Dynamically override summary message.
    _log.info("Line 4", extra=RateLimit(summary_msg="Some logs missed"))

    assert "___" not in caplog.text
    assert all([line in caplog.text for line in generate_lines(3)])
    assert "\n + skipped 3 logs due to rate-limiting" in caplog.text
    assert "skipped 2 logs" not in caplog.text
    assert "Some logs missed" in caplog.text


@patch("log_rate_limit.log_rate_limit.TEST_MODE", True)
def test_log_limit_allow_next_n(caplog):
    """Test the summary functionality."""
    # Setup logging.
    _log = logging.getLogger(get_test_name())
    _log.setLevel(logging.INFO)

    # Setup to filter all logs in the same stream without needing to define a stream_id each time.
    _log.addFilter(StreamRateLimitFilter(1, default_stream_id=DefaultSID.NONE, filter_undefined=True, allow_next_n=2))

    _log.info("Line 1")
    _log.info("Line 2")
    _log.info("Line 3")
    _log.info("___")
    _log.info("___")
    time.sleep(1.1)
    # Dynamically override value in this instance.
    _log.info("Line 4", extra=RateLimit(allow_next_n=1))
    _log.info("Line 5")
    _log.info("___")

    assert "___" not in caplog.text
    assert all([line in caplog.text for line in generate_lines(5)])


def test_log_non_strings():
    """Test that our logging filter and stream IDs work when not logging string messages."""
    # Setup logging for this test.
    _log = logging.getLogger(get_test_name())
    _log.setLevel(logging.INFO)
    # Setup filter 1-second limit which should only affect logs with stream_ids.
    _log.addFilter(StreamRateLimitFilter(1))

    _log.info("Line 1")
    # Use non-string types for message.
    _log.info({"a": "b"})
    _log.info(["a", "b"])
    _log.info({"a", "b"})
    _log.info(("a", "b"))
    # Test with formatting args.
    _log.info("%s vs %s ", "a", "b")

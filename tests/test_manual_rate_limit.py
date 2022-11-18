import time
from unittest.mock import patch

from log_rate_limit import StreamRateLimitFilter


@patch("log_rate_limit.log_rate_limit.TEST_MODE", True)
def test_manual_limit_streams(caplog) -> None:
    """Test that manual rate limiting applies separately to different streams."""
    # Create filter without any logs.
    limiter = StreamRateLimitFilter(1, all_unique=False)
    start = time.time()
    # The first event is always allowed to fire for new streams.
    assert limiter.should_trigger("stream2", current_time=start)
    assert limiter.should_trigger("stream2", current_time=start + 1.1)
    assert limiter.should_trigger("stream1", current_time=start)
    limiter.reset_trigger("stream1", current_time=start)
    # After triggering/resetting events can only trigger if enough time has passed.
    assert not limiter.should_trigger("stream1", current_time=start)
    assert limiter.should_trigger("stream1", current_time=start + 1.1)
    # Second stream should be unaffected about trigger events in stream1.
    assert limiter.should_trigger("stream2", current_time=start)

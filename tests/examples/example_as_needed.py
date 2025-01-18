"""Example code used in the docs."""

import logging
from log_rate_limit import StreamRateLimitFilter, RateLimit, DefaultSID

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# Don't consider all logs unique by default
logger.addFilter(StreamRateLimitFilter(period_sec=1, default_stream_id=DefaultSID.NONE))
# Normal logs are not rate-limited
for i in range(3):
    logger.info(f"Status update: {i}")
# Only those we manually assign a stream will be rate-limited
for _ in range(3):
    logger.warning("Issue!", extra=RateLimit(stream_id="issue"))

"""Example code used in the docs."""

import logging
from log_rate_limit import StreamRateLimitFilter, RateLimit

logging.basicConfig(level=logging.INFO)
_logger = logging.getLogger(__name__)
# Add our filter
_logger.addFilter(StreamRateLimitFilter(period_sec=1))

# Use LoggerAdapter to assign additional "extra" parameters to all calls using this logger
global_extra = RateLimit(stream_id="custom_stream", period_sec=20)
logger = logging.LoggerAdapter(_logger, global_extra)
# Log many warnings
for _ in range(100):
    logger.warning("Wolf!")
for i in range(100):
    logger.warning("No really, a wolf!")

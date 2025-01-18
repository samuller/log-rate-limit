"""Example code used in the docs."""

import logging
import time

from log_rate_limit import RateLimit, StreamRateLimitFilter

# Setup logging
logging.basicConfig()
logger = logging.getLogger(__name__)
# Add our filter
logger.addFilter(StreamRateLimitFilter(period_sec=1))
# Log many warnings
for _ in range(100):
    logger.warning("Wolf!")
for i in range(100):
    logger.warning("No really, a wolf!")
    if i == 98:
        time.sleep(1)
# Override stream to set it as undefined (None) to prevent rate-limiting
for _ in range(3):
    logger.warning("Sheep!", extra=RateLimit(stream_id=None))

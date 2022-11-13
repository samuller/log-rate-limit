# log-rate-limit - limit excessive log output

[![Build Status](https://github.com/samuller/log-rate-limit/actions/workflows/tests.yml/badge.svg)](https://github.com/samuller/log-rate-limit/actions/workflows/tests.yml)
[![Code Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)](https://github.com/samuller/pgmerge/actions)
[![Checked with mypy](https://img.shields.io/badge/mypy-strict-blue)](http://mypy-lang.org/)
[![Formatted with black](https://img.shields.io/badge/code%20style-black-black)](https://black.readthedocs.io/en/stable/)

A logging filter that can be used with Python's standard logging mechanism to rate-limit logs - i.e. suppress logs when they are being output too fast.

Log commands are grouped into separate **streams** that will each have their own rate limitation applied without affecting the logs in other streams. By default every log is assigned a unique stream so that only "repeated" logs will be suppressed - in this case "repeated" logs doesn't mean identical log messages, but rather logs output from the same line of code. However, logs can also be assigned streams manually to achieve various outcomes:
- A dynamic stream id based on the message content can be used so that different messages from the same log command can also be rate-limited separately.
- A log can be assigned to an undefined/`None` stream so that rate-limiting doesn't apply to it.
- Logs in different parts of the code can be grouped into the same stream so that they share a rate-limit, e.g. when they all trigger due to the same issue and only some are needed to indicate it.

## Usage

### Rate-limiting by default

Example of rate-limiting with default options where each log is assigned to it's own stream:
```python
import time
import logging
from log_rate_limit import StreamRateLimitFilter, RateLimit
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
# Override stream as undefined to prevent rate-limiting
for _ in range(3):
    logger.warning("Sheep!", extra=RateLimit(stream_id=None))
``` 
Which only outputs the following:
```log
WARNING:__main__:Wolf!
WARNING:__main__:No really, a wolf!
WARNING:__main__:No really, a wolf!
+ skipped 98 logs due to rate-limiting
WARNING:__main__:Sheep!
WARNING:__main__:Sheep!
WARNING:__main__:Sheep!
```
Note that (unless overridden) logs were only repeated after the `sleep()` call, and the repeated log also included an extra summary message added afterwards.

When we override rate-limiting above, you'll see our filter reads dynamic configs from logging's `extra` parameter.

> Be very careful not to forget the `extra=` name part of the argument, as then the logging framework will assume you're passing arguments meant for formatting in the logging message and your options will silently be ignored!

### Rate-limit only when specified

If you want most of your logs to be unaffected and you only have some you want to specifically rate-limit, then you can do the following:
```python
import logging
from log_rate_limit import StreamRateLimitFilter, RateLimit
# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add our filter, but don't assign unique streams to logs by default
logger.addFilter(StreamRateLimitFilter(period_sec=1, all_unique=False))
# Normal logs are now not rate-limited
for i in range(3):
    logger.info(f"Status update: {i}")
# Only those we manually assign a stream will be rate-limited
for _ in range(3):
    logger.warning("Issue!", extra=RateLimit(stream_id="issue"))
```
Which only outputs the following:
```log
INFO:__main__:Status update: 0
INFO:__main__:Status update: 1
INFO:__main__:Status update: 2
WARNING:__main__:Issue!
```

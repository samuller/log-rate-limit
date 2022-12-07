# log-rate-limit - limit excessive log output

[![PyPI Version](https://img.shields.io/pypi/v/log-rate-limit)](https://pypi.org/project/log-rate-limit/)
[![Build Status](https://github.com/samuller/log-rate-limit/actions/workflows/tests.yml/badge.svg)](https://github.com/samuller/log-rate-limit/actions/workflows/tests.yml)
[![Code Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)](https://github.com/samuller/pgmerge/actions)
[![Checked with mypy](https://img.shields.io/badge/mypy-strict-blue)](http://mypy-lang.org/)
[![Formatted with black](https://img.shields.io/badge/code%20style-black-black)](https://black.readthedocs.io/en/stable/)

A [logging filter](https://docs.python.org/3/library/logging.html#filter-objects) using Python's standard logging mechanisms to rate-limit logs - i.e. suppress logs when they are being output too fast.

Log commands are grouped into separate **streams** that will each have their own rate limitation applied without affecting the logs in other streams. By default every log message is assigned a unique stream so that only repeated log messages will be suppressed.

However, logs can also be assigned streams manually to achieve various outcomes:
- A log can be assigned to an undefined/`None` stream so that rate-limiting doesn't apply to it.
- Logs in different parts of the code can be grouped into the same stream so that they share a rate-limit, e.g. when they all trigger due to the same issue and only some are needed to indicate it.

The default can also be changed so that rate-limiting is disabled by default and only applies to logs for which a `stream_id` has been manually set.

## Quick usage

Import the filter:

```python
from log_rate_limit import StreamRateLimitFilter, RateLimit
```

Use the filter with your `logger`. With default parameters it will rate limit all repetitive log message:

```python
logger.addFilter(StreamRateLimitFilter(period_sec=30))
```

All logs on `logger` will now be rate limited, but this can be disabled per-log by setting the `stream_id` to `None`:

```python
logger.warning("Something went wrong!", extra=RateLimit(stream_id=None))
```

## Usage examples

### Rate-limiting by default

Example of rate-limiting with default options where each log message is assigned to its own stream:
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
# Prevent rate-limited by setting/overriding the stream to be undefined (None)
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
logger.addFilter(StreamRateLimitFilter(period_sec=1, default_stream_id=None))
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

### Dynamically override configuration options

Some options set during creation of the initial filter can be overridden for individual log calls. This is done by adding the `extra` parameter to any specific log call, e.g.:
```python
# Override the rate limit period for this specific log call
logger.warning("Test1", extra=RateLimit(stream_id="stream1", period_sec=30))
# Override the allow_next_n value for a set of logs in the same stream so that this group of logs don't restrict one
# another from occuring consecutively
logger.warning("Test", extra=RateLimit(stream_id="stream2", allow_next_n=2))
logger.info("Extra", extra=RateLimit(stream_id="stream2"))
logger.debug("Info", extra=RateLimit(stream_id="stream2"))
```

If you want to set custom options for a large group of log calls without repeatedly adding the `extra` parameter, it's possible to use a [LoggerAdapter](https://docs.python.org/3/library/logging.html#loggeradapter-objects):
```python
import logging
from log_rate_limit import StreamRateLimitFilter, RateLimit

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# Add our filter
logger.addFilter(StreamRateLimitFilter(period_sec=1))

# Use LoggerAdapter to assign additional "extra" parameters to all calls using this logger
global_extra = RateLimit(stream_id="custom_stream", period_sec=20)
logger = logging.LoggerAdapter(logger, global_extra)
# Log many warnings
for _ in range(100):
    logger.warning("Wolf!")
for i in range(100):
    logger.warning("No really, a wolf!")
```
Which merely outputs:
```log
WARNING:__main__:Wolf!
```
Since both log calls are in the same stream.

Alternatively (to a LoggerAdapter), custom options can also be added by writing your own [logging.Filter](https://docs.python.org/3.8/howto/logging-cookbook.html#using-filters-to-impart-contextual-information).

### Dynamic stream ID

Dynamic stream IDs can be assigned based on any criteria you want, e.g.:

```python
logger.warning(f"Error occured on device {device_id}!", extra=RateLimit(stream_id=f"error_on_{device_id}"))
```

## Installation

### Install from PyPI

With `Python 3` installed on your system, you can run:

    pip install log-rate-limit

To test that installation worked, you can run:

    python -c "import log_rate_limit"

and you can uninstall at any time with:

    pip uninstall log-rate-limit

To install with poetry:

    poetry add log-rate-limit

### Install from Github

To install the newest code directly from Github:

    pip install git+https://github.com/samuller/log-rate-limit

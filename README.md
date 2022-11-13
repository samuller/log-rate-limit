# log-rate-limit - limit excessive log output

[![Build Status](https://github.com/samuller/log-rate-limit/actions/workflows/tests.yml/badge.svg)](https://github.com/samuller/log-rate-limit/actions/workflows/tests.yml)
[![Code Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)](https://github.com/samuller/pgmerge/actions)
[![Checked with mypy](https://img.shields.io/badge/mypy-strict-blue)](http://mypy-lang.org/)

A logging filter that can be used with Python's standard logging mechanism to rate-limit logs - i.e. suppress logs when they are being output too fast.

Log commands can also be grouped into separate **streams** that will each have their own rate limitation applied without affecting the logs in other streams. This can be used to avoid a few excessive logs from triggering suppression of other crucial logs.

## Usage

Basic example:
```python
import time
import logging
from log_rate_limit import StreamRateLimitFilter

# Setup logging
logging.basicConfig()
logger = logging.getLogger(__name__)
logger.addFilter(StreamRateLimitFilter(period_sec=1))
# Log many warnings
for _ in range(100):
    logger.warning("Wolf!")
for i in range(100):
    logger.warning("No really, a wolf!")
    if i == 98:
        time.sleep(1)
``` 
Which only outputs the following:
```
WARNING:__main__:Wolf!
WARNING:__main__:No really, a wolf!
WARNING:__main__:No really, a wolf!
+ skipped 98 logs due to rate-limiting
```
Note that logs were only repeated after the `sleep()` call, and the repeated log also included an extra summary message added afterwards.
    pip install git+https://github.com/samuller/log-rate-limit

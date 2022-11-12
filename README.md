# log-rate-limit - library to help with rate limiting log output

[![Build Status](https://github.com/samuller/log-rate-limit/actions/workflows/tests.yml/badge.svg)](https://github.com/samuller/log-rate-limit/actions/workflows/tests.yml)
[![Code Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)](https://github.com/samuller/pgmerge/actions)
[![Checked with mypy](http://www.mypy-lang.org/static/mypy_badge.svg)](http://mypy-lang.org/)

This library provides a logging filter that can be used with Python's standard logging mechanism to rate-limit logs, i.e. suppress logs when they are being output too fast. To avoid excessive logs from preventing other crucial logs from being shown, log commands can also be grouped into separate *streams* that will each have their own rate limitation applied without affecting the logs in other streams.

## Usage

Basic example:
```python
import time
import logging
from log_rate_limit import RateLimitFilter

# Setup logging
logging.basicConfig()
logger = logging.getLogger(__name__)
logger.addFilter(RateLimitFilter(min_time_sec=1, filter_all=True))
# Log many warnings
logger.warning("Wolf!")
logger.warning("Be aware, wolf!")
logger.warning("Loop there, a wolf!")
time.sleep(1)
logger.warning("Ah, no really, a wolf!")
``` 
Which outputs the following:
```
WARNING:__main__:Wolf!
WARNING:__main__:Ah, no really, a wolf!
+ skipped 2 logs due to rate-limiting
```
Note the 2nd and 3rd logs have been supressed.

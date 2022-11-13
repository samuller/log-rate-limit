"""Module for the StreamRateLimitFilter class."""
import time
import logging
from collections import defaultdict
from typing import Any, Dict, TypedDict, Optional

TEST_MODE = False


class StreamRateLimitFilter(logging.Filter):
    """Filter out each "stream" of logs so they don't happen too fast within a given period of time.

    Logs can be separated into "streams" so that the rate-limit only applies to logs in the same stream.
    """

    def __init__(
        self,
        period_sec: float,
        allow_next_n: int = 0,
        all_unique: bool = True,
        filter_undefined: bool = False,
        summary: bool = True,
        summary_msg: str = " + skipped {numskip} logs due to rate-limiting",
        name: str = "",
    ):
        """Construct a logging filter that will limit rate of logs.

        Parameters
        ----------
        period_sec
            The minimum time period (in seconds) allowed between log messages of the same stream.
        allow_next_n
            After each allowed log, also allow the immediate next `allow_next_n` count of logs (within the same stream)
            to ignore the rate-limit and be allowed. Can also be used to approximate allowing a burst of logs every now
            and then.
        all_unique
            If all logs should have unique `stream_id`s assigned to them by default. The default `stream_id` of a log
            is thus determined as follows:
            - If `all_unique=True` then a unique `stream_id` will be auto-assigned to all logs (by using `filename` and
              `line_no`). This will in-effect rate-limit all repeated logs (excluding dynamic changes in the specific
              log message itself, e.g. through formatting args).
            - If `all_unique=False` then all logs will be default assigned `stream_id=None` and other `stream_id`
              values will need to be manually specified on a case-by-case basis.
        filter_undefined
            If logs without defined `stream_id`s should be filtered:
            - If `filter_undefined=True` then even logs without any stream_id (i.e. `stream_id=None`) will also be
              rate-limited. (Note that if `all_unique=True` then logs will only have `stream_id=None` when manually
              specified.)
            - If `filter_undefined=False`, then all logs with `stream_id=None` will not have any rate-limit applied to
              them.
        summary
            If a summary message should be shown along with allowed logs to summarise/mention logs that were
            suppressed/skipped.
        summary_msg
            The summary message used to summarise logs that were suppressed/skipped.
        name
            Filter names form a logger hierarchical where they apply only to current or lower levels, e.g. with name
            "A.B" it will apply to "A.B" and also "A.B.C", "A.B.C.D", etc. but not to "A". See Python docs:
            https://docs.python.org/3/library/logging.html#filter-objects
        """
        super().__init__(name)
        # These values are all defaults that can be temporarily overriden on-the-fly.
        self._period_sec = period_sec
        self._allow_next_n = allow_next_n
        self._filter_undefined = filter_undefined
        self._all_unique = all_unique
        self._summary = summary
        self._summary_msg = summary_msg
        # All these dictionaries are per-stream with stream_ids as their key.
        self._next_valid_time: Dict[str, float] = {}
        self._skipped_log_count: Dict[str, int] = defaultdict(int)
        # Count of extra logs left that can ignore rate-limit based on allow_next_n.
        self._count_logs_left: Dict[str, int] = defaultdict(int)

    def _reset_timer(self, stream_id: str, period_sec: float) -> None:
        self._next_valid_time[stream_id] = time.time() + period_sec

    def _get(self, record: logging.LogRecord, attribute: str, default_val: Any = None) -> Any:
        if hasattr(record, attribute):
            return getattr(record, attribute)
        return default_val

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter function that determines if given log message will be displayed.

        Returns
        -------
        True if log should be shown or else False if log should be skipped/hidden/filtered out.
        """
        global TEST_MODE
        if TEST_MODE:
            _test_default_overrides(record)

        default_stream_id = None
        if self._all_unique:
            # Assign unique default stream_ids.
            default_stream_id = f"{record.filename}:{record.lineno}"
        # Get variables that can be dynamically overridden, or else will use init-defaults.
        stream_id = self._get(record, "stream_id", default_stream_id)
        period_sec = self._get(record, "period_sec", self._period_sec)
        allow_next_n = self._get(record, "allow_next_n", self._allow_next_n)
        summary = self._get(record, "summary", self._summary)
        summary_msg = self._get(record, "summary_msg", self._summary_msg)

        skip_count = self._skipped_log_count[stream_id]
        count_left = self._count_logs_left[stream_id]

        if stream_id is None and not self._filter_undefined:
            return True

        # Inner function to prevent code duplication.
        def prep_to_allow_msg(reset_all: bool = True) -> None:
            # This value might be reset momentarily.
            self._count_logs_left[stream_id] -= 1
            if summary and skip_count > 0:
                # Change message to indicate a summary of skipped logs.
                added_msg = summary_msg.format(numskip=skip_count)
                record.msg = f"{record.msg}\n{added_msg}"
            # Reset counters and timers.
            if reset_all:
                self._skipped_log_count[stream_id] = 0
                self._count_logs_left[stream_id] = allow_next_n
                self._reset_timer(stream_id, period_sec)

        # Allow if this is the first message for this stream.
        if stream_id not in self._next_valid_time:
            prep_to_allow_msg()
            return True

        next_valid_time = self._next_valid_time[stream_id]
        # Allow if enough time has passed since the last log message for this stream.
        if time.time() >= next_valid_time:
            prep_to_allow_msg()
            return True

        # Allow if the "allow next N" option applies and this message is within a count of N of the last allowed
        # message (and previous criteria were not met).
        if count_left > 0:
            prep_to_allow_msg(reset_all=False)
            return True

        # Once we've reached here, we'll definitely skip this log message.
        self._skipped_log_count[stream_id] += 1
        return False


class RateLimit(TypedDict, total=False):
    """Easily construct a logging "extra" dict with rate-limiting parameters."""

    # Manually define a stream_id for this logging record. A value of `None` is valid and has specific meaning based on
    # the filter's configuration options.
    stream_id: Optional[str]
    # The following values allow dynamic configurability by overriding the defaults (for only this record) that were
    # set when initializing the filter.
    period_sec: float
    allow_next_n: int
    summary: bool
    summary_msg: str


def _test_default_overrides(record: logging.LogRecord) -> None:
    """(Only used during testing) Checks default-override parameter values to improve value of code coverage.

    A 100% statement coverage of our code isn't always sufficient as it can miss specific variable states (also because
    the branching caused by those states happens in Python library code which is excluded from our code coverage). In
    our case, it's specifically easy to miss if there aren't tests for each variable that can override the default
    values. We therefore add statements/lines of code here for variables states we're interested in also covering.
    """
    do_something = None
    if hasattr(record, "stream_id"):
        do_something = None
    if hasattr(record, "period_sec"):
        do_something = None
    if hasattr(record, "allow_next_n"):
        do_something = None
    if hasattr(record, "summary"):
        do_something = None
    if hasattr(record, "summary_msg"):
        do_something = None
    return do_something

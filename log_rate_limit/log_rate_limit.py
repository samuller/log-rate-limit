"""Module for the RateLimitFilter class."""
import time
import logging
from collections import defaultdict
from typing import Any, Dict, Optional


class RateLimitFilter(logging.Filter):
    """Filter out logs so they don't happen too fast within a given period of time.

    Logs can be separated into "streams" so that the rate-limit only applies to logs in the same stream. By default
    all logs will be assigned to the `None` stream and will not have the rate-limit applied to them.
    """

    def __init__(
        self,
        min_time_sec: float,
        allow_next_n: int = 0,
        filter_all: bool = False,
        all_unique: bool = False,
        summary: bool = True,
        summary_msg: str = "+ skipped {numskip} logs due to rate-limiting",
        name: str = "",
    ):
        """Construct a logging filter that will limit rate of logs.

        Parameters
        ----------
        min_time_sec
            The minimum time in seconds allowed between log messages of the same stream.
        allow_next_n
            After each allowed log, also allow the immediate next `allow_next_n` count of logs to ignore the rate-limit
            and be allowed. Can also be used to approximate allowing a burst of logs every now and then.
        filter_all
            If true then even logs without any stream_id (i.e. `None` stream_id) will also be rate limited.
        all_unique
            By default, auto-assign unique stream_id's to all logs by using filename and line_no. This will in-effect
            rate-limit all repeated logs (excluding dynamic changes in the specific log message itself, e.g. through
            formatting args).
        summary
            If a summary message should be shown along with allowed logs to summarise logs that were suppressed/skipped.
        summary_msg
            The summary message used to summarise logs that were suppressed/skipped.
        name
            Filter names form a logger hierarchical where they apply only to current or lower levels, e.g. with name
            "A.B" it will apply to "A.B" and also "A.B.C", "A.B.C.D", etc. but not to "A". See Python docs:
            https://docs.python.org/3/library/logging.html#filter-objects
        """
        super().__init__(name)
        # These values are all defaults that can be temporarily overriden on-the-fly.
        self._min_time_sec = min_time_sec
        self._allow_next_n = allow_next_n
        self._filter_all = filter_all
        self._all_unique = all_unique
        self._summary = summary
        self._summary_msg = summary_msg
        # All these dictionaries are per-stream with stream_ids as their key.
        self._next_valid_time: Dict[str, float] = {}
        self._skipped_log_count: Dict[str, int] = defaultdict(int)
        # Count of log attempts since last allowed log that reset timer.
        self._count_since_reset_log: Dict[str, int] = defaultdict(int)

    def _reset_timer(self, stream_id: str, min_time_sec: float) -> None:
        self._next_valid_time[stream_id] = time.time() + min_time_sec

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
        # Get variables that can be dynamically overridden, or else will use init-defaults.
        stream_id = self._get(record, "stream_id", None)
        if self._all_unique and stream_id is None:
            stream_id = f"{record.filename}:{record.lineno}"
        min_time_sec = self._get(record, "min_time_sec", self._min_time_sec)
        allow_next_n = self._get(record, "allow_next_n", self._allow_next_n)
        summary = self._get(record, "summary", self._summary)
        summary_msg = self._get(record, "summary_msg", self._summary_msg)
        skip_count = self._skipped_log_count[stream_id]
        since_count = self._count_since_reset_log[stream_id]

        if stream_id is None and not self._filter_all:
            return True

        # Inner function to prevent code duplication.
        def prep_to_allow_msg(reset_all: bool = True) -> None:
            if summary and skip_count > 0:
                # Change message to indicate a summary of skipped logs.
                added_msg = summary_msg.format(numskip=skip_count)
                record.msg = f"{record.msg}\n{added_msg}"
            # Reset counters and timers.
            if reset_all:
                self._skipped_log_count[stream_id] = 0
                self._count_since_reset_log[stream_id] = 0
                self._reset_timer(stream_id, min_time_sec)

        # Allow if this is the first message for this stream.
        if stream_id not in self._next_valid_time:
            prep_to_allow_msg()
            return True

        next_valid_time = self._next_valid_time[stream_id]
        # Allow if enough time has passed since the last log message for this stream.
        if time.time() >= next_valid_time:
            prep_to_allow_msg()
            return True

        # Logs after this point don't fully reset the timer.
        self._count_since_reset_log[stream_id] += 1
        # Allow if the "allow next N" option applies and this message is within a count of N of the last allowed
        # message.
        if since_count < allow_next_n:
            prep_to_allow_msg(reset_all=False)
            return True

        # Once we've reached here, we'll definitely skip this log message.
        self._skipped_log_count[stream_id] += 1
        return False


def rate_limit(
    stream_id: Optional[str] = None,
    min_time_sec: Optional[float] = None,
    summary: Optional[bool] = None,
    summary_msg: Optional[str] = None,
) -> Dict[str, Any]:
    """Easily construct a logging "extra" dict with rate-limiting parameters."""
    extra: Dict[str, Any] = {}
    if stream_id is not None:
        extra["stream_id"] = stream_id
    if min_time_sec is not None:
        extra["min_time_sec"] = min_time_sec
    if summary is not None:
        extra["summary"] = summary
    if summary_msg is not None:
        extra["summary_msg"] = summary_msg
    return extra

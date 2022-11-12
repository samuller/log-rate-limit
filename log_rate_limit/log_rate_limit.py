"""Module for the RateLimitFilter class."""
import time
import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional


class RateLimitFilter(logging.Filter):
    """Filter out logs so they don't happen too fast within a given period of time.

    Logs can be separated into "streams" so that the rate-limit only applies to logs in the same stream. By default
    all logs will be assigned to the `None` stream and will not have the rate-limit applied to them.
    """

    def __init__(
        self,
        min_time_sec: float,
        allow_next_n: int = 0,  # TODO
        filter_all: bool = False,
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
            After each allowed log, also allow the immediate next `allow_next_n` logs through, ignoring the rate-limit.
        filter_all
            If true then even logs without any stream_id (i.e. `None` stream_id) will also be rate limited.
        name
            Filters are hierarchical and those with name "A.B" will only apply to "A.B" and "A.B.C", etc. but not "A".
        """
        super().__init__(name)
        # These values are all defaults that can be temporarily overriden on-the-fly.
        self._min_time_sec = min_time_sec
        self._allow_next_n = allow_next_n
        self._filter_all = filter_all
        self._summary = summary
        self._summary_msg = summary_msg
        # All these dictionaries are per-stream with stream_ids as their key.
        self._next_valid_time: Dict[str, float] = {}
        self._skipped_log_count: Dict[str, int] = defaultdict(int)

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
        stream_id = self._get(record, "stream_id")
        min_time_sec = self._get(record, "min_time_sec", self._min_time_sec)
        summary = self._summary

        if not self._filter_all and stream_id is None:
            return True

        # Inner function to prevent code duplication.
        def prep_to_allow_msg() -> None:
            skiplen = self._skipped_log_count[stream_id]
            if summary and skiplen > 0:
                # Change message to indicate a summary of skipped logs.
                added_msg = self._summary_msg.format(numskip=skiplen)
                record.msg = f"{record.msg}\n{added_msg}"
            self._skipped_log_count[stream_id] = 0
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

        # Once we've reached here, we'll definitely skip this log message.
        if summary:
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


if __name__ == "__main__":
    # Get root log
    # _log = logging.getLogger()
    _log = logging.getLogger(__name__)

    _log.addHandler(logging.StreamHandler())
    _log.setLevel(logging.INFO)

    # Default per stream?
    # _log.addFilter(RateLimitFilter({None: 5, biggest: 30}, filter_all=True))
    _log.addFilter(RateLimitFilter(5, filter_all=True))
    _log.info("Line 1")
    _log.info("Skip")
    _log.info("Skip", extra=rate_limit(stream_id=None))
    _log.info("Other Line 1", extra=rate_limit(stream_id="other"))
    _log.info("Other Skip", extra=rate_limit(stream_id="other"))
    _log.info("BIG Log Line 1", extra=rate_limit(stream_id="big", min_time_sec=30))
    _log.info("BIG Skip", extra=rate_limit(stream_id="big"))
    _log.info("BIGGEST Log Line 1", extra=rate_limit(stream_id="biggest"))
    time.sleep(5.1)
    _log.info("Line 2")
    _log.info("Skip", extra={**rate_limit(stream_id=None), "other_field": "other_value"})
    _log.info("Other Line 2", extra=rate_limit(stream_id="other"))
    _log.info("BIG skip", extra={"stream_id": "big", "min_time_sec": 30})
    _log.info("BIGGEST skip", extra=rate_limit(stream_id="biggest"))

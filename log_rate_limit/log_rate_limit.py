"""Module for the StreamRateLimitFilter class."""
import time
import logging
from collections import defaultdict
from typing import Any, Dict, TypedDict, Optional, Literal

# Used to enable extra code paths/checks during testing.
TEST_MODE = False

# Type for possible values of a stream_id.
StreamID = Optional[str]
# Type for defining how default stream_id values are assigned.
DefaultStreamID = Literal[None, "file_line_no", "log_message"]


# We don't use an Enum because we want to support direct string values and enums with string values are only properly
# supported in Python 3.11+.
class DefaultSID:
    """Default Stream ID constants to choose how an undefined stream ID is determined."""

    # Default stream ID to None.
    NONE: DefaultStreamID = None
    # Default stream ID to the log's file and line number location.
    FILE_LINE_NO: DefaultStreamID = "file_line_no"
    # Default stream ID to the log message.
    LOG_MESSAGE: DefaultStreamID = "log_message"


class StreamRateLimitFilter(logging.Filter):
    """Filter out each "stream" of logs so they don't happen too fast within a given period of time.

    Logs can be separated into "streams" so that the rate-limit only applies to logs in the same stream. Also, the
    trigger times for each stream can be accessed and controlled (read or written) in case there are other non-logging
    events that you want to rate-limit in a similar fasion (or possibly even in the same stream as some other logs).
    """

    def __init__(
        self,
        period_sec: float,
        allow_next_n: int = 0,
        default_stream_id: DefaultStreamID = DefaultSID.LOG_MESSAGE,
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
        default_stream_id
            Define how the default value for each log's `stream_id` is determined when it isn't manually specified:
            - `None`: Stream ID's default to `None` which might mean they won't be rate-limited or that they will all
                      share the same rate-limit (depending on `filter_undefined`).
            - `'file_line_no'`: Each log is given a Stream ID based on the file and line number where it's located.
            - `'log_message'`: The exact log message (after formatting) is used as a unique stream ID. This means that
               all unique messages will be rate-limited.
            Regardless of the default, it's always possible to manually specify `stream_id`s on a per-log basis by
            setting it in the `extra` args, e.g. `logging.info(msg, extra=RateLimit(stream_id="custom"))`.
        filter_undefined
            If logs without defined `stream_id`s should be filtered:
            - If `filter_undefined=True` then even logs without any stream_id (i.e. `stream_id=None`) will also be
              rate-limited.
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
        self._default_stream_id = default_stream_id
        self._summary = summary
        self._summary_msg = summary_msg
        # Next time at which rate-limiting no longer applies to each stream. Initial default of 0 will always fire
        # since it specifies the Unix epoch timestamp.
        self._next_valid_time: Dict[StreamID, float] = defaultdict(float)
        # Count of the number of logs suppressed/skipped in each stream.
        self._skipped_log_count: Dict[StreamID, int] = defaultdict(int)
        # Count of extra logs left that can ignore rate-limit based on allow_next_n.
        self._count_logs_left: Dict[StreamID, int] = defaultdict(int)

    def _get(self, record: logging.LogRecord, attribute: str, default_val: Any = None) -> Any:
        if hasattr(record, attribute):
            return getattr(record, attribute)
        return default_val

    def trigger(
        self, stream_id: str, override_period_sec: Optional[float] = None, current_time: Optional[float] = None
    ) -> bool:
        """Trigger a specific stream and then also resets its rate-limit timer - but only if rate-limiting allows.

        Parameters
        ----------
        stream_id
            Unique stream identifier.
        override_period_sec
            Optional parameter to override the minimum time period between triggers (period_sec) instead of using the
            default value defined when this class was instantiated.
        current_time
            Optional parameter that can be used to call this function for different points in time.

        Return
        ------
        True if the trigger was allowed to fire (enough time has passed) and has been reset.
        """
        if self.should_trigger(stream_id, current_time):
            self.reset_trigger(stream_id, override_period_sec, current_time)
            return True
        return False

    def should_trigger(self, stream_id: StreamID, current_time: Optional[float] = None) -> bool:
        """Whether a stream can trigger as enough time has passed since a stream previously triggered.

        Parameters
        ----------
        stream_id
            Unique stream identifier.
        current_time
            Optional parameter that can be used to call this function for different points in time.

        Return
        ------
        True if enough time has passed that this stream is able to trigger.
        """
        if current_time is None:
            current_time = time.time()
        # Allow if enough time has passed since the last log message for this stream (or if this is the first message
        # for this stream - in which case next_valid_time should get the default value of 0).
        next_valid_time = self._next_valid_time[stream_id]
        return current_time >= next_valid_time

    def reset_trigger(
        self,
        stream_id: StreamID,
        override_period_sec: Optional[float] = None,
        current_time: Optional[float] = None,
    ) -> None:
        """Reset a stream's trigger timer - should happen whenever it triggers.

        Parameters
        ----------
        stream_id
            Unique stream identifier.
        override_period_sec
            Optional parameter to override the minimum time period between triggers (period_sec) instead of using the
            default value defined when this class was instantiated.
        current_time
            Optional parameter that can be used to call this function for different points in time.
        """
        if override_period_sec is None:
            override_period_sec = self._period_sec
        if current_time is None:
            current_time = time.time()
        self._next_valid_time[stream_id] = current_time + override_period_sec

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
        if self._default_stream_id == DefaultSID.FILE_LINE_NO:
            # Assign unique default stream_ids.
            default_stream_id = f"{record.filename}:{record.lineno}"
        if self._default_stream_id == DefaultSID.LOG_MESSAGE:
            default_stream_id = record.getMessage()
        # Get variables that can be dynamically overridden, or else use init-defaults.
        stream_id = self._get(record, "stream_id", default_stream_id)
        period_sec = self._get(record, "period_sec", self._period_sec)
        allow_next_n = self._get(record, "allow_next_n", self._allow_next_n)
        summary = self._get(record, "summary", self._summary)
        summary_msg = self._get(record, "summary_msg", self._summary_msg)

        skip_count = self._skipped_log_count[stream_id]
        count_left = self._count_logs_left[stream_id]

        # Add any extra attributes we might add to record.
        record.srl_summary_note = ""

        if stream_id is None and not self._filter_undefined:
            return True

        # Inner function to prevent code duplication.
        def prep_to_allow_msg(reset_all: bool = True) -> None:
            # This value might be reset momentarily.
            self._count_logs_left[stream_id] -= 1
            # See if we should generate a summary note.
            if skip_count > 0:
                # Change message to indicate a summary of skipped logs.
                # NOTE: period_sec might be incorrect if it is, or has been, overridden (either currently or recently).
                added_msg = summary_msg.format(numskip=skip_count, stream_id=stream_id, period_sec=period_sec)
                summary_note = f"\n{added_msg}"
                # Always add summary_note attribute.
                record.srl_summary_note = summary_note
                # Only append summary to log message if summary option is set.
                if summary:
                    record.msg = f"{record.msg}{summary_note}"
            # Reset counters and timers.
            if reset_all:
                self._skipped_log_count[stream_id] = 0
                self._count_logs_left[stream_id] = allow_next_n
                self.reset_trigger(stream_id, period_sec)

        # Allow if enough time has passed since the last log message for this stream was triggered.
        if self.should_trigger(stream_id):
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
    stream_id: StreamID
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

"""Module for the StreamRateLimitFilter class."""

import logging
import time
from typing import Any, Literal, Optional, TypedDict

from log_rate_limit.streams import StreamID, StreamsCache, StreamsCacheDict, StreamsCacheRedis

# Used to enable extra code paths/checks during testing.
TEST_MODE = False

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

    def __init__(  # noqa: PLR0913
        self,
        # Rate-limiting.
        period_sec: float,
        allow_next_n: int = 0,
        *,
        # Default behaviour.
        default_stream_id: DefaultStreamID = DefaultSID.LOG_MESSAGE,
        filter_undefined: bool = False,
        # Summary messages.
        summary: bool = True,
        summary_msg: str = " + skipped {numskip} logs due to rate-limiting",
        # Where to apply this filter.
        name: str = "",  # Inherited from parent.
        # Managing memory usage.
        expire_check_sec: int = 60,
        expire_offset_sec: int = 900,
        expire_msg: str = " [Previous logs] {numskip} logs were skipped"
        ' (and expired after {expire_time_sec}s) for stream: "{stream_id}"',
        stream_id_max_len: Optional[int] = None,
        # Using Redis for storage.
        redis_url: Optional[str] = None,
        redis_key_prefix: str = "log-rate-cache",
        # Debugging.
        print_config: bool = False,
    ) -> None:
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
            Filter names form a logger hierarchy where they apply only to current or lower levels, e.g. with name
            "A.B" it will apply to "A.B" and also "A.B.C", "A.B.C.D", etc. but not to "A". See Python docs:
            https://docs.python.org/3/library/logging.html#filter-objects
        expire_check_sec
            We expire log stream information after some time to decrease memory usage. This value determines how
            regularly we check for expired data (which might rarely have some performance impact). Default is set to
            once per minute.
        expire_offset_sec
            This offset is the number of seconds after the log rate limit has been reached for a specific stream
            before any info we store about the stream will expire. Due to the fact that we only check at specific
            time intervals, this expiry offset could be delayed by as long as the `expire_check_sec` parameter as well.
            Default is set to 15 minutes.
        expire_msg
            The message used to summarise logs that were expired.
        stream_id_max_len
            If set, this defines a maximum length for the stream names (stream_id strings). If set to None (the
            default) then there is no limit. Be aware that while setting this would help limit memory usage, it will
            also make it very easy for similar log messages to get assigned to the same stream and get unintentionally
            confused with one another (which is behaviour that should rather be controlled by correctly defining
            stream_id strings to determine how you want to define uniqueness).
        redis_url
            If a Redis database URL is provided then per-stream details will be cached in a the given Redis database
            rather than in a dictionary in the current process's memory. Using Redis allows multiple processes with a
            single output stream to share their rate-limiting, and it also allows cache to be monitored externally.
        redis_key_prefix
            A prefix string to add to all keys used in Redis. This can be used to determine whether separate instances
            of the cache are separate or whether their stream info is shared. Has to be less than 64 characters in
            length to limit total length of Redis keys.
        print_config
            At initialisation, print the configuration options provided to this class.

        """
        super().__init__(name)
        if period_sec < 0:
            raise ValueError("period_sec has to be positive")
        if allow_next_n < 0:
            raise ValueError("allow_next_n has to be positive")
        if expire_check_sec < 0:
            raise ValueError("expire_check_sec has to be positive")
        if stream_id_max_len is not None and stream_id_max_len <= 0:
            raise ValueError("stream_id_max_len has to be positive")
        # These values are all defaults that can be temporarily overriden on-the-fly.
        self._period_sec = period_sec
        self._allow_next_n = allow_next_n
        self._filter_undefined = filter_undefined
        self._default_stream_id = default_stream_id
        self._summary = summary
        self._summary_msg = summary_msg
        self._expire_check_sec = expire_check_sec
        self._expire_offset_sec = expire_offset_sec
        self._expire_msg = expire_msg
        self._stream_id_max_len = stream_id_max_len

        # Global counter of when next to check expired streams.
        self._next_expire_check_time: Optional[float] = None
        # All data kept in memory for each stream.
        if redis_url is not None:
            self._streams: StreamsCache = StreamsCacheRedis(redis_url=redis_url, redis_prefix=redis_key_prefix)
        else:
            self._streams = StreamsCacheDict()
        if print_config:
            self._print_config()

    def _print_config(self) -> None:
        print("StreamRateLimitFilter configuration:", self.__dict__)

    def _get(self, record: logging.LogRecord, attribute: str, default_val: Any = None) -> Any:  # noqa: ANN401
        if hasattr(record, attribute):
            return getattr(record, attribute)
        return default_val

    def trigger(
        self, stream_id: str, override_period_sec: Optional[float] = None, current_time: Optional[float] = None
    ) -> bool:
        """Trigger and reset rate-limit timer of specific stream if rate-limiting allows.

        This allows you to use StreamRateLimitFilter for non-logging use-cases to rate-limit anything. See "manual"
        example in tests.

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
        next_valid_time = self._streams[stream_id].next_valid_time
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
        self._streams[stream_id].next_valid_time = current_time + override_period_sec

    def _get_default_stream_id(self, record: logging.LogRecord) -> StreamID:
        default_stream_id = None
        if self._default_stream_id == DefaultSID.FILE_LINE_NO:
            # Assign unique default stream_ids.
            default_stream_id = f"{record.filename}:{record.lineno}"
        if self._default_stream_id == DefaultSID.LOG_MESSAGE:
            default_stream_id = record.getMessage()
        return default_stream_id

    def _check_expiry(self, expire_offset_sec: float, expire_msg: str) -> str:
        current_time = time.time()
        # Global check - not specifically related to the current stream being processed, and could affect other
        # streams.
        srl_expire_note = ""
        if self._next_expire_check_time is None or current_time > self._next_expire_check_time:
            # Check and clear from memory any stream data that has expired.
            srl_expire_note = self._streams.clear_old(expire_offset_sec, expire_msg=expire_msg)
            self._next_expire_check_time = current_time + self._expire_check_sec
        return srl_expire_note

    def _limit_stream_id_length(self, stream_id: StreamID) -> StreamID:
        # If configured, limit the length of stream_id.
        if stream_id is not None:
            # string[0:None] will just select the whole string.
            stream_id = stream_id[0 : self._stream_id_max_len]
        return stream_id

    def _skip_log_or_add_note(self, srl_expire_note: str, record: logging.LogRecord) -> bool:
        # We introduce our own log message if current message was skipped, but other messages were expired during
        # this processing.
        if srl_expire_note != "":
            record.msg = srl_expire_note
            return True
        return False

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter function that determines if given log message will be displayed.

        Returns
        -------
        True if log should be shown or else False if log should be skipped/hidden/filtered out.

        """
        global TEST_MODE
        if TEST_MODE:
            _test_default_overrides(record)

        default_stream_id = self._get_default_stream_id(record)
        # Get variables that can be dynamically overridden, or else use init-defaults.
        stream_id = self._get(record, "stream_id", default_stream_id)
        period_sec = self._get(record, "period_sec", self._period_sec)
        allow_next_n = self._get(record, "allow_next_n", self._allow_next_n)
        summary = self._get(record, "summary", self._summary)
        summary_msg = self._get(record, "summary_msg", self._summary_msg)
        expire_offset_sec = self._get(record, "expire_offset_sec", self._expire_offset_sec)
        expire_msg = self._get(record, "expire_msg", self._expire_msg)

        stream_id = self._limit_stream_id_length(stream_id)

        # Run expiry checks before accessing any fields from the current stream.
        # TODO: with a Redis cache, streams could get expired by other processes at any possible time.
        srl_expire_note = self._check_expiry(expire_offset_sec, expire_msg)

        # Add any extra attributes we might add to record as this allows user's own log formatting to use it (if
        # they're only sometimes present, then string formatting will fail when attributes aren't found). All
        # attributes added by this filter will be prepended with "srl_" (for Stream Rate Limit).
        record.srl_summary_note = ""
        record.srl_expire_note = srl_expire_note
        # Log any expired messages after the current log message.
        record.msg = f"{record.msg}{srl_expire_note}"
        if stream_id is None and not self._filter_undefined:
            return True

        # Fetch stream that we'll use for this log message.
        # TODO: with Redis cache, the value read here could immediately expire after being fetched (or any other time).
        stream = self._streams[stream_id]

        # Inner function to prevent code duplication.
        def prep_to_allow_msg() -> None:
            skip_count = stream.skipped_log_count
            # This value might be reset momentarily.
            stream.count_logs_left -= 1
            # See if we should generate a summary note.
            if skip_count > 0:
                # Change message to indicate a summary of skipped logs.
                # NOTE: period_sec might be incorrect if it is, or has been, overridden (either currently or
                # recently).
                added_msg = summary_msg.format(numskip=skip_count, stream_id=stream_id, period_sec=period_sec)
                summary_note = f"\n{added_msg}"
                # Always add summary_note attribute.
                record.srl_summary_note = summary_note
                # Only append summary to log message if summary option is set.
                if summary:
                    record.msg = f"{record.msg}{summary_note}"

        # Allow if enough time has passed since the last log message for this stream was triggered.
        if self.should_trigger(stream_id):
            prep_to_allow_msg()
            # Reset all counters and timers.
            stream.skipped_log_count = 0
            stream.count_logs_left = allow_next_n
            self.reset_trigger(stream_id, period_sec)
            return True

        # Allow if the "allow next N" option applies and this message is within a count of N of the last allowed
        # message (and previous criteria were not met).
        count_left = stream.count_logs_left
        if count_left > 0:
            prep_to_allow_msg()
            return True

        # Once we've reached here, we'll definitely skip the current log message.
        stream.skipped_log_count += 1
        return self._skip_log_or_add_note(srl_expire_note, record)

    def _key_size(self) -> int:
        """Get an estimate of the number of keys stored in memory."""
        return len(self._streams)


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

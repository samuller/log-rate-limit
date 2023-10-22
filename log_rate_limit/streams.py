"""Module for the types and abstractions related to Streams."""
# Postponed annotations will be automatic starting with Python 3.11.
# https://stackoverflow.com/questions/44640479/type-annotation-for-classmethod-returning-instance
from __future__ import annotations
from typing import Dict, Optional
from dataclasses import dataclass
from collections import defaultdict


# Type for possible values of a stream_id.
StreamID = Optional[str]


@dataclass
class StreamInfo:
    """All information kept per-stream."""

    # Next time at which rate-limiting no longer applies to each stream. Initial default of 0 will always fire
    # since it specifies the Unix epoch timestamp.
    next_valid_time: float = 0.0
    # Count of the number of logs suppressed/skipped in each stream.
    skipped_log_count: int = 0
    # Count of extra logs left that can ignore rate-limit based on allow_next_n.
    count_logs_left: int = 0


class StreamsCache(defaultdict):  # type: ignore
    """The StreamsCache class maps stream IDs to stream info.

    This class provides an abstraction over how the data is stored. The default is to just store it in-memory as a
    Python dictionary.
    """

    def __init__(
        self,
        built_dict: Optional[Dict[StreamID, StreamInfo]] = None,
    ) -> None:
        """Construct object with default values."""
        default_factory = StreamInfo
        if built_dict is None:
            built_dict = {}
        super().__init__(default_factory, built_dict)

    def __repr__(self) -> str:
        """Override repr."""
        return f"{self.__class__.__name__}({dict(self)})"

"""Module for the types and abstractions related to Streams."""
# Postponed annotations will be automatic starting with Python 3.11.
# https://stackoverflow.com/questions/44640479/type-annotation-for-classmethod-returning-instance
from __future__ import annotations

import time
import hashlib
import dataclasses
from dataclasses import dataclass
from collections import defaultdict
from typing import Dict, Optional, Protocol, Set, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from redis import Redis


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


class StreamsCache(Protocol):  # pragma: no cover
    """Interface for StreamsCache that maps stream IDs to stream info.

    This interface mainly matches that of a dictionary and allow us to abstract away how the data is stored. The
    default is to just store it in-memory as a Python dictionary with StreamsCacheDict, but it's also possible to store
    it externally (out-of-process) in a Redis storage with StreamsCacheRedis (where the cache could even be shared with
    other processes).
    """

    def __setitem__(self, key: StreamID, value: StreamInfo) -> None:
        """Set stream info object."""
        ...

    def __getitem__(self, key: StreamID) -> StreamInfo:
        """Get or create a stream info object."""
        ...

    def __delitem__(self, key: StreamID) -> None:
        """Remove stream info object."""
        ...

    def __len__(self) -> int:
        """Get length of mapped StreamIDs."""
        ...

    def keys(self) -> Any:  # Set[StreamID]:
        """Get an iterator of all streams cached under this prefix."""
        ...

    def clear_old(self, expire_time_sec: float, current_time: Optional[float] = None, expire_msg: str = "") -> str:
        """Clear old stream IDs to free up memory (in case of many large stream ID strings).

        Parameters
        ----------
        expire_time_sec
            Only clear out streams that haven't been reset in this period of time (in seconds). This is an amount of
            time added after rate-limiting no longer applies anyway. Highly recommended to be a positive number.
            Default is the expire offset configured at initialisation.
        current_time
            Optional parameter that can be used to call this function for different points in time.
        expire_msg
            Message format of logs used to report expired streams.
        """
        if current_time is None:
            current_time = time.time()

        # We build a string of keys to remove first since the alternative of looping through the dictionary and
        # removing keys will require that we iterate through a copy of the dictionary's keys which is exactly
        # the part which might be using excessive memory.
        keys_to_remove = []
        for stream_id in self.keys():
            next_valid_time = self[stream_id].next_valid_time
            # Daylight savings or other time changes might break or trigger this check during the transition period?
            if (next_valid_time + expire_time_sec) < current_time:
                keys_to_remove.append(stream_id)

        expire_note = ""
        for stream_id in keys_to_remove:
            skip_count = self[stream_id].skipped_log_count
            # If any logs were skipped, then we log it before clearing the cache.
            if skip_count > 0:
                added_msg = expire_msg.format(numskip=skip_count, stream_id=stream_id, expire_time_sec=expire_time_sec)
                expire_note += f"\n{added_msg}"
            # Remove keys
            del self[stream_id]

        return expire_note


class StreamsCacheDict(defaultdict, StreamsCache):  # type: ignore
    """An implementation of StreamsCache that uses a DefaultDict to store the stream info in-memory of the process."""

    def __init__(
        self,
        built_dict: Optional[Dict[StreamID, StreamInfo]] = None,
    ) -> None:
        """Construct default dictionary with only our specific types.

        Parameters
        ----------
        built_dict
            Optional argument to initialise this cache with a pre-defined dictionary.
        """
        default_factory = StreamInfo
        if built_dict is None:
            built_dict = {}
        super().__init__(default_factory, built_dict)

    def __repr__(self) -> str:
        """Generate printable representation of object."""
        return f"{self.__class__.__name__}({dict(self)})"


class StreamInfoRedisProxy(StreamInfo):
    """An extension/wrapper of the StreamInfo object that sets values in Redis when attributes are updated."""

    def __init__(self, redis: "Redis[Any]", redis_key: str, **kwargs: Any) -> None:
        """Construct stream info redis proxy object."""
        self.redis = redis
        self.redis_key = redis_key
        super().__init__(**kwargs)

    def __setattr__(self, prop: str, value: Any) -> None:
        """Update values locally and in redis."""
        super().__setattr__(prop, value)
        if prop not in ["redis", "redis_key"]:
            # Instead of only setting the property that was updated, we specifically set all the values together to
            # ensure the object stays synchronized and has all properties. In case of synchronization issues where the
            # key was already deleted, setting only a single property will create half-a-object without all the keys.
            self.redis.hset(name=self.redis_key, mapping=dataclasses.asdict(self))  # type: ignore

    @staticmethod
    def from_stream_info(redis: "Redis[Any]", redis_key: str, stream_info: StreamInfo) -> StreamInfoRedisProxy:
        """Create a StreamInfoRedisProxy initialised with the values from a StreamInfo object."""
        return StreamInfoRedisProxy(redis=redis, redis_key=redis_key, **dataclasses.asdict(stream_info))


class StreamsCacheRedis(StreamsCache):
    """An implementation of StreamsCache that stores the stream info in a Redis database."""

    def __init__(
        self,
        redis_url: str,
        redis_prefix: str = "StreamsCache",
    ) -> None:
        """Construct object and setup access to use Redis as a cache.

        Parameters
        ----------
        redis_url
            URL for the Redis database.
        redis_prefix
            A prefix string to add to all keys used in Redis. This can be used to determine whether separate instances
            of the cache are separate or whether their stream info is shared. Has to be less than 64 characters in
            length to limit total length of Redis keys.
        """
        from redis import Redis

        # Redis keys should not be too long. See: https://redis.io/docs/manual/keyspace/.
        if len(redis_prefix) > 64:
            raise ValueError("redis_prefix string should be shorter than 64 characters.")
        super().__init__()
        self.redis_url = redis_url
        self.redis_prefix = redis_prefix
        # We try to follow general format of "app:feature:key" for our Redis keys. In this specific case that means our
        # keys are of the form: "log_rate_limit:streams:stream_id".
        self._prefix = f"{self.redis_prefix}:streams:"
        self.redis = Redis.from_url(url=redis_url, decode_responses=True)

    def _key(self, key: StreamID) -> str:
        # Redis keys should not be too long. See: https://redis.io/docs/manual/keyspace/.
        full_key = f"{self._prefix}{key}"
        # Hash long stream IDs. 192 limit chosen as half-way between 128 & 256. 128 is too short as it's shorter than
        # our max hashed length.
        if len(full_key) > 192 and key is not None:
            # We use MD5 as we want a hash that's fast, short and doesn't need to be very secure. We don't use Python's
            # string __hash__() function as it specifically randomizes the hash between Python process instances.
            hash = hashlib.md5(key.encode(errors="backslashreplace")).hexdigest()
            short_key = key[0:32] + "..."
            # Expected max. length of new key is: 64+9+35+2+32 = 142.
            full_key = f"{self._prefix}{short_key}({hash})"
        return full_key

    def _set_stream(self, rkey: str, value: StreamInfo) -> None:
        self.redis.hset(rkey, mapping=dataclasses.asdict(value))  # type: ignore

    def __setitem__(self, key: StreamID, value: StreamInfo) -> None:
        """Set stream info object."""
        rkey = self._key(key)
        self._set_stream(rkey, value)

    def __getitem__(self, key: StreamID) -> StreamInfo:
        """Get or create a stream info object."""
        rkey = self._key(key)
        hash_value = self.redis.hgetall(rkey)
        if hash_value == {}:
            self._set_stream(rkey, StreamInfo())
            return StreamInfoRedisProxy(redis=self.redis, redis_key=rkey)

        si = StreamInfo(
            next_valid_time=float(hash_value["next_valid_time"]),
            skipped_log_count=int(hash_value["skipped_log_count"]),
            count_logs_left=int(hash_value["count_logs_left"]),
        )
        return StreamInfoRedisProxy.from_stream_info(redis=self.redis, redis_key=rkey, stream_info=si)

    def __delitem__(self, key: StreamID) -> None:
        """Remove stream info object."""
        rkey = self._key(key)
        self.redis.delete(rkey)

    def __len__(self) -> int:
        """Get length of mapped StreamIDs."""
        return len(self.keys())

    def keys(self) -> Set[StreamID]:
        """Get list of all streams cached under this prefix."""
        cursor = 0
        new_cursor = 1
        # Use a set as SCAN might return duplicates.
        all_keys: Set[StreamID] = set()
        while new_cursor != 0:
            new_cursor, new_keys = self.redis.scan(cursor, match=f"{self._prefix}*")
            cursor = new_cursor
            # Remove prefixes that are used internally and aren't part of public interface (StreamIDs).
            new_keys = [key[len(self._prefix) :] for key in new_keys]
            all_keys = all_keys.union(new_keys)
        return all_keys

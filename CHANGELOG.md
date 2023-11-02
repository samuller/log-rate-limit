# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.4.1] - 2023-11-02

### Fixed

- Redis sync issue that causes `KeyError: 'next_valid_time'` error in rare (or high load) situations.

## [1.4.0] - 2023-11-01

### Added

- Per-stream rate-limiting data (cache) can now be stored in a Redis database if a `redis_url` is provided to the `StreamRateLimitFilter` constructor.
  - Using Redis allows multiple processes with a single output stream to share their rate-limiting, and it also allows cache to be monitored and controlled externally (e.g. if memory usage of rate-limiting cache becomes a concern for long-running processes).

## [1.3.0] - 2023-07-29

### Added

- Tracked streams are now expired after some time.
  - When expired, they'll report any skipped messages that haven't been reported before.
  - This should help with long-running processes that could use increasing amounts of memory in the rare case that they continually generate both large and unique log messages (actually unique `stream_ids`).
  - The new configurable parameters introduced for this feature are: `expire_check_sec` (default: 1min), `expire_offset_sec` (default: 15min) and `expire_msg`.
    - The default values mean that a stream is considered expired 15 minutes after end of rate-limiting and that the check for expired streams will occur (at most) once a minute.
- New `stream_id_max_len` option can be used to limit `stream_id` strings to a maximum length.
- Added `print_config` option to print provided configs at start-up. Useful for debugging.
- Added complexity check to CI and refactored code to simplify it.

## [1.2.2] - 2022-12-22

### Added

- `srl_summary_note` now gets added to all log records that pass through filter:
  - Is only set whenever a message is printed and previous messages in the same stream were suppressed.

### Changed

- Simplified default unique message to use `LogRecord`'s `getMessage()` function.

## [1.2.1] - 2022-12-07

### Fixed

- Fix bug when not logging string messages

## [1.2.0] - 2022-12-04

### Changed

- Default rate-limiting now applies to identical log messages (instead of to logs originating from the same line of code).
- Replaced boolean `all_unique` parameter with `default_stream_id` which can have multiple options, including ones that achieve the same functionality as before:
  - `default_stream_id=None` (or `default_stream_id=DefaultSID.NONE`) is equivalent to `all_unique=False`.
  - `default_stream_id="file_line_no"` (or `default_stream_id=DefaultSID.FILE_LINE_NO`) is equivalent to `all_unique=True`.

# Added

- New `default_stream_id` parameter includes a third option that wasn't previously available:
  - `default_stream_id="log_message"` (or `default_stream_id=DefaultSID.LOG_MESSAGE`) which will set the default stream ID such that repeated log messages will be rate limited.

## [1.1.0] - 2022-11-19

### Added

- Add methods `trigger()`, `should_trigger()` and `reset_trigger()` that are used to evaluate rate-limiting and trigger logs. These functions can also be used separately from logging for other purposes, e.g. to trigger custom rate-limited events.

## [1.0.1] - 2022-11-13

### Changed

- Expanded usage examples in documentation, as well as other small improvements.
- Slight spacing change to default summary message.

### Added

- Allow summary message to contain `stream_id` and `period_sec`.

### Fixed

- Set PyPI package description.

## [1.0.0] - 2022-11-13

Initial release to PyPI.

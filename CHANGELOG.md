# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

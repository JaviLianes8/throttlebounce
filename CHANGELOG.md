# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0]

- `debounce` gains `leading` and `trailing` edge options and `max_wait`, so a
  debouncer can fire on the first call of a burst, on the last, or both, and is
  never starved by an unbroken stream of calls.
- `throttle` gains a `trailing` edge so the final call in a busy window is not
  dropped, plus `cancel`, `flush`, `pending` and `result` to match `debounce`.
- `Debounced` gains a `result` property.
- New async decorators `async_debounce` and `async_throttle` for coroutine
  functions, scheduled on the running event loop with an injectable scheduler.
- New `throttlebounce` command line that debounces or throttles a command driven
  by trigger lines on stdin.
- All additions are backward compatible; existing defaults are unchanged.

## [0.1.0]

- First release: `debounce` and `throttle` decorators, thread-safe, with an
  injectable clock and timer so tests never wait on real time.

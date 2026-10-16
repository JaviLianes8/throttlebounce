# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-10-16

The public API is now stable: `debounce`, `throttle`, `async_debounce`,
`async_throttle`, their wrapper classes `Debounced`, `Throttled`, `AsyncDebounced` and
`AsyncThrottled` (`flush`, `cancel`, `pending`, `result`, and `reset` on throttles),
and the injectable `Clock`, `TimerFactory` and `Scheduler`. Names, signatures and
defaults will not change before 2.0. Code that uses the decorators upgrades from 0.1.0
with no change.

Breaking against 0.1.0: `Debounced` and `Throttled` built directly take
`timer_factory` and `clock` by keyword only (0.1.0 also took them as the third
positional argument).

Changed since 0.2.0 (which was never published to PyPI):

- `max_wait` now behaves as in lodash: the deadline counts from the start of the burst
  and then from each run, and the burst carries on after a deadline run, so the leading
  edge does not fire again in the middle of it. `max_wait` below `wait` is refused.
- With the trailing edge off, nothing is kept pending: `pending` stays False and
  `flush()` returns None.
- A timer that fires after it was replaced or cancelled is ignored, so a late timer
  thread can no longer run a call early.
- Decorated methods get a separate wrapper per instance.
- The async wrappers keep their tasks until they finish, so the garbage collector can
  no longer drop a run halfway.
- Durations must be finite real numbers from 0 to `threading.TIMEOUT_MAX`; anything
  else raises `ValueError` or `TypeError` when the decorator is built.
- Attributes of the wrapped callable can no longer overwrite the wrapper's state.
- `Clock`, `TimerFactory` and `Scheduler` are callback protocols with documented
  call signatures; public names report `throttlebounce` as their module.
- The async wrappers raise `RuntimeError` before changing any state when no event loop
  is running, on every Python version, and report a failing timed run through the
  loop's exception handler.
- Decorated methods keep their argument types for type checkers.
- A clock reading that is not finite no longer freezes a throttle, attributes of the
  wrapped function no longer hide the wrapper's methods, and an async wrapper called
  from a new event loop drops what the old loop's dead timers held.
- Command line: the command gets no standard input, and the end of input waits for a
  run a timer has already started.
- Command line: the exit status is that of the last run (0 if none, 127 if the command
  cannot start, 130 on Ctrl+C), runs never overlap, a pending run happens before exit,
  and bad values give a usage error instead of a traceback.
- The public `dev` extra is gone; development tools are listed in
  `requirements-dev.txt`.

## [0.2.0] - not published

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

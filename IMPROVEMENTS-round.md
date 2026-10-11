# Improvements round: throttlebounce

This round takes `throttlebounce` from a minimal pair of decorators (trailing-edge
debounce, leading-edge throttle) toward a complete, lodash-grade timing toolkit
while staying typed, zero-dependency, thread-safe and testable without real time.

Everything below is additive. Existing behaviour and signatures are preserved:
`debounce(wait)` still debounces on the trailing edge and returns `None`;
`throttle(interval)` still runs on the leading edge. New behaviour is opt-in
through new keyword arguments and new objects.

## Ranked improvements

### 1. Leading and trailing edges for `debounce` (high value)
Today `debounce` only fires on the trailing edge. Real debouncers (lodash,
underscore) let you choose: `leading=True` runs on the first call of a burst,
`trailing=True` runs after the burst goes quiet, and both together run on the
first call and again at the end only if more than one call arrived. This is the
single most requested debounce feature. Added as `debounce(wait, *, leading=...,
trailing=...)`, trailing defaulting to `True` so existing code is unchanged.

### 2. `max_wait` for `debounce` (high value)
A pure trailing debounce can be starved forever by a continuous stream of calls
and never run. `max_wait` guarantees the function runs at least once per
`max_wait` seconds during a sustained burst (the lodash `maxWait`). This turns a
debouncer into something usable for progress updates and autosave under constant
input. Added as `debounce(wait, *, max_wait=...)`.

### 3. Trailing edge for `throttle` (high value)
Leading-only throttle drops the last call in a window, which loses the final
state (the last keystroke, the final scroll position). `trailing=True` schedules
the most recent skipped call to run when the window closes, so the final value is
never lost. Added as `throttle(interval, *, trailing=..., timer_factory=...)`,
defaulting to the current leading-only behaviour.

### 4. `cancel`, `flush`, `pending`, `result` on `throttle` (medium value)
Trailing throttle introduces a pending call, so `Throttled` gains the same
control surface `Debounced` already has: `cancel()` drops the pending trailing
call, `flush()` runs it now and returns its result, `pending` reports whether one
is waiting, and `result` exposes the last value produced. This makes the two
decorators symmetric and predictable.

### 5. `result` property on `debounce` (low cost, high symmetry)
`Debounced` already stores the last result internally for `flush`; exposing it as
a read-only `result` property lets callers read the most recent value without
forcing a run. Symmetric with throttle.

### 6. Async support: `async_debounce` and `async_throttle` (high value)
Debouncing and throttling coroutine functions is a common need in asyncio apps
(websocket handlers, UI event streams, API fan-in). This round adds
`async_debounce` and `async_throttle` that wrap coroutine functions, schedule
runs on the running event loop (no threads, no real sleeps in tests via an
injectable `call_later`), and expose async `flush`, `cancel`, `pending` and
`result`. Leading/trailing/max_wait parity with the sync side.

### 7. A real CLI: `throttlebounce` (medium value, genuinely meaningful)
A debouncer does have a meaningful command line: debouncing or throttling a shell
command driven by a stream of trigger lines on stdin, the same job `entr` and
`watchexec` do internally. `throttlebounce debounce --wait 0.5 -- make build`
reads trigger lines from stdin and runs the command once input goes quiet;
`throttlebounce throttle --interval 1 -- ./deploy.sh` runs it at most once per
interval. Added via argparse and `[project.scripts]`, with `--help` examples in
the README and a real end-to-end subprocess test that drives the installed
console script.

### 8. Typed overloads and richer docstrings (polish)
Tighten the public signatures and docstrings so editors show the full option set
and the return-type story (debounced call returns `None`; read results via
`result`/`flush`). Keep `py.typed` honest under `mypy --strict`.

### 9. A GUIDE.md (polish)
A task-oriented guide covering debounce vs throttle, the edge options, `max_wait`,
cancel/flush, thread-safety, testing with fake clocks and timers, the async API
and the CLI, with runnable examples.

## Explicitly out of scope (no overreach)
- Distributed or cross-process rate limiting (this is an in-process primitive).
- A full file-watcher (the CLI consumes triggers from stdin; pairing with a
  watcher is left to the user and documented).
- Changing any existing default or return type (strictly additive).

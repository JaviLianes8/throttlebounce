# throttlebounce guide

When to debounce and when to throttle, every option, the control methods, threads,
async, methods, testing without real time, the command line, how the rules compare
with lodash and Underscore, and what changed since 0.1.0.

## Debounce or throttle

- **Debounce** waits for calls to go quiet, then runs once: autosave after typing,
  search as you type, rebuild after a burst of file edits, a resize handler.
- **Throttle** runs at a steady maximum rate while calls keep coming: progress bars,
  scroll and mouse handlers, heartbeats, polite polling of an API.

## Debounce

A *burst* is a run of calls less than `wait` seconds apart. The quiet timer restarts
on every call and ends the burst when it fires.

```python
from throttlebounce import debounce

seen = []


@debounce(0.3)
def save(text: str) -> None:
    seen.append(text)


save("h")
save("he")
save("hello")
assert save.pending
save.flush()
assert seen == ["hello"]
```

Edges:

- `trailing=True` (the default): run once, `wait` seconds after the last call of the
  burst, with that call's arguments.
- `leading=True, trailing=False`: run on the first call of a burst and ignore the
  rest of it. The next call after `wait` seconds of quiet opens a new burst.
- `leading=True` with the trailing edge on: run on the first call, and again at the
  end of the burst only if another call came after the first.

```python
from throttlebounce import debounce

opened = []


@debounce(1.0, leading=True, trailing=False)
def open_file(path: str) -> None:
    opened.append(path)


open_file("a.txt")  # runs at once
open_file("a.txt")  # same burst: ignored
assert opened == ["a.txt"]
assert open_file.pending is False  # with the trailing edge off nothing waits
```

Both edges off is refused with `ValueError`, since nothing would ever run.

### max_wait

Under a non-stop stream of calls the quiet timer never fires, so a plain debounce
never runs. `max_wait` (at least `wait`) is a deadline: during an unbroken burst the
latest call runs `max_wait` seconds after the burst began, and again `max_wait`
seconds after each such run, until the burst ends.

```python
from throttlebounce import debounce

updates = []


@debounce(0.2, max_wait=2.0)
def show(progress: float) -> None:
    updates.append(progress)  # 0.2 s after a pause, and at least every 2 s
```

When the deadline passes with nothing waiting (only possible with the trailing edge
off), the next call opens a new burst, so with `leading=True` it runs at once.

## Throttle

The first call runs at once and opens a window of `interval` seconds, measured from
the start of that run. Calls inside the window are skipped and return the latest
result (None before the first run).

```python
from throttlebounce import throttle

now = 0.0


@throttle(1.0, trailing=True, clock=lambda: now)
def render(position: int) -> int:
    return position


assert render(10) == 10
assert render(20) == 10  # skipped, waits for the window to close
assert render.pending
assert render.flush() == 20  # or let the window close on its own
```

With `trailing=True` the most recent skipped call runs when the window closes, and
that run opens the next window, so the final value of a busy stretch is never lost.
A clock reading earlier than the last run (a clock that jumped back) counts as a
closed window rather than a stuck one.

## Control methods

| Member | Debounce | Throttle |
| --- | --- | --- |
| `flush()` | runs the pending call now and returns its result (None if none); ends the burst | runs the pending trailing call now; that run opens a new window |
| `cancel()` | drops the pending call and ends the burst | drops the pending trailing call; the window stays |
| `reset()` | (none) | forgets the last run, so the next call runs at once |
| `pending` | a call waits for the trailing edge or the deadline | a trailing call waits for the window to close |
| `result` | what the latest run returned | the same |

Calling a debounced function returns None, even when the leading edge runs it, since
most of its runs happen later; read `result` for the value. Calling a throttled
function returns the new result when it runs and the latest result when skipped.

If the wrapped function raises, the exception reaches whoever triggered the run: the
caller for a leading run or `flush()`, the timer thread for a trailing run (where
Python reports it through `threading.excepthook`). The wrapper stays usable and
`result` keeps the last value that was returned.

## Threads

The sync wrappers are safe to call from any thread. State changes happen under a lock;
the function always runs outside it, so a slow or re-entrant function never blocks
other callers or deadlocks. Trailing runs and deadlines happen on daemon
`threading.Timer` threads, so a pending call never keeps the process alive. A timer
that fires after being replaced or cancelled is recognised and ignored.

Durations must be finite, non-negative and at most `threading.TIMEOUT_MAX` seconds
(about 49 days on Windows), the longest a `threading.Timer` can wait. Anything else
raises `ValueError` (or `TypeError` if it is not a real number) when the decorator is
built.

## Async

`async_debounce` and `async_throttle` take the same options and run each call as a
task on the running event loop, with no threads. Call the wrappers from the loop's
thread while it runs. `flush()` is a coroutine that awaits the run; `result` is the
value of the most recently finished run. The wrappers keep a reference to every task
until it finishes, so a run is never garbage-collected halfway.

```python
import asyncio

from throttlebounce import async_throttle

beats = []


@async_throttle(5.0)
async def heartbeat(n: int) -> None:
    beats.append(n)


async def main() -> None:
    heartbeat(1)
    heartbeat(2)  # inside the interval: skipped
    await asyncio.sleep(0)


asyncio.run(main())
assert beats == [1]
```

## Methods

Read through an instance, a decorated method gives that instance its own wrapper,
created on first use and cached in the instance `__dict__` (as
`functools.cached_property` does). Read through the class, it gives the shared
wrapper. Classes whose instances have no `__dict__` (`__slots__` without it) get a
`TypeError` saying so.

## Testing without real time

Inject the time source: `clock` for the throttles, `timer_factory` for `debounce`
and `throttle(trailing=True)`, `scheduler` for the async pair. A timer factory is
called as `factory(delay, action)` and returns an object with `start()` and
`cancel()`; a scheduler is called the same way and returns an object with `cancel()`.

```python
from throttlebounce import debounce


class ManualTimer:
    def __init__(self, delay: float, action) -> None:
        self.delay, self.action, self.live = delay, action, False

    def start(self) -> None:
        self.live = True

    def cancel(self) -> None:
        self.live = False


timers = []


def factory(delay, action):
    timers.append(ManualTimer(delay, action))
    return timers[-1]


seen = []
record = debounce(0.5, timer_factory=factory)(seen.append)
record(1)
record(2)
for timer in [t for t in timers if t.live]:
    timer.live = False
    timer.action()  # "0.5 seconds later"
assert seen == [2]
```

The test suite has a small virtual clock (`tests/_virtual.py`) that drives the clock,
the timers and the scheduler together, which is how it replays lodash's behaviour.

## Command line

```console
$ printf 'a\nb\nc\n' | throttlebounce throttle --interval 60 --trailing -- python -c "print('deployed')"
deployed
deployed
```

`throttlebounce debounce --wait S [--max-wait S] [--leading] [--no-trailing] -- cmd`
and `throttlebounce throttle --interval S [--trailing] -- cmd`. Each input line is one
trigger. Runs never overlap. When the input ends, a pending run happens at once.
Exit status: that of the last run, 0 if the command never ran, 127 if it could not be
started, 2 for a usage error, 130 when interrupted with Ctrl+C.

## Differences from lodash

The scenarios in `tests/fixtures/oracle_runs.json` were run through lodash 4.18.1 and
Underscore 1.13.8 (`scripts/oracle_fixture.py`). Debounce matches Underscore in all of
them and lodash in all but the two cases below; throttle matches Underscore in all of
them and lodash whenever the trailing edge is off.

- **Deadlines.** After a `max_wait` run, lodash restarts its timer at the next call
  with the full `wait`, so when `max_wait` is under twice `wait` the next deadline can
  pass unnoticed and the held call runs later. throttlebounce runs it exactly at the
  deadline.
- **Throttle with a trailing edge.** lodash builds its throttle from that same
  debounce, so a trailing run can come late, and a call right after a trailing run can
  run again at once, twice inside one interval. throttlebounce, like Underscore, keeps
  every run at least one interval after the one before.

Other differences by design: throttle defaults to `trailing=False` (lodash and
Underscore default to `True`); there is no `leading=False` option for throttle; a
debounced call returns None rather than the previous result; `flush()` returns None
when nothing is pending; `max_wait` below `wait` is refused instead of raised to it.

## Upgrading from 0.1.0

Code written for 0.1.0 keeps working: same names, same defaults, same results. New
since then: the `leading`, `trailing` and `max_wait` options, `trailing` on throttle,
`flush`, `cancel`, `pending` and `result` on every wrapper, the async decorators, the
command line and per-instance methods. Durations are now checked when the decorator is
built: NaN, infinities, values beyond `threading.TIMEOUT_MAX` and booleans raise
`ValueError` or `TypeError`. 0.1.0 accepted them, with broken results: an infinite
debounce wait crashed its timer thread and left the call pending forever, and a NaN
throttle interval let every call through.

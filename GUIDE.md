# throttlebounce guide

A practical tour of the library: when to debounce, when to throttle, the edge
options, `max_wait`, cancel and flush, thread-safety, the async API, testing
without real time, and the command line.

## Debounce vs throttle

- **Debounce** waits for calls to go quiet, then runs once. Use it for "do this
  after the user stops": autosave after typing, search-as-you-type, resize
  handlers, rebuild after a burst of file edits.
- **Throttle** runs at a steady maximum rate while calls keep coming. Use it for
  "do this no more than N times a second": scroll and mousemove handlers,
  progress updates, heartbeat pings, API rate limits.

## Debounce edges

By default `debounce` runs on the trailing edge: once, `wait` seconds after the
last call, with that call's arguments.

```python
from throttlebounce import debounce


@debounce(0.3)
def save(text: str) -> None:
    write_to_disk(text)


save("h")
save("he")
save("hello")  # only this reaches disk, 0.3s after typing stops
```

`leading=True` runs on the first call of a burst instead of (or as well as) the
last. With both edges on, the trailing run happens only when more than one call
arrived during the window.

```python
@debounce(0.3, leading=True, trailing=False)
def open_once(path: str) -> None:
    launch(path)  # fires on the first click, ignores the rest of the burst
```

## max_wait

A pure trailing debounce under a non-stop stream of calls never runs, because the
window keeps resetting. `max_wait` guarantees a run at least that often.

```python
@debounce(0.2, max_wait=2.0)
def report(progress: float) -> None:
    update_bar(progress)  # at most 0.2s after quiet, and at least every 2s
```

## Throttle edges

`throttle` runs on the leading edge: the first call fires immediately, calls
within `interval` are skipped and return the last result.

```python
from throttlebounce import throttle


@throttle(1.0)
def ping() -> None:
    send_heartbeat()  # at most once per second
```

`trailing=True` also runs the most recent skipped call when the interval closes,
so the final value in a busy window is never lost.

```python
@throttle(0.1, trailing=True)
def on_scroll(position: int) -> None:
    render(position)  # steady updates, plus the final resting position
```

## Cancel, flush, pending, result

Both decorators expose the same control surface for their pending call:

```python
save("draft")
save.pending  # True while a call is waiting
save.flush()  # run it now and return its result
save.cancel()  # or drop it so it never runs
save.result  # the most recent value produced
```

`throttle(...).reset()` clears the window so the next call fires immediately.

## Thread-safety

Every sync decorator is safe to call from multiple threads. State changes are
guarded by a lock and the wrapped function runs outside the lock, so a slow or
re-entrant callback never blocks or deadlocks other callers. Trailing runs happen
on a daemon `threading.Timer`, so a pending call never keeps the process alive.

## Async

`async_debounce` and `async_throttle` wrap coroutine functions and schedule runs
on the running event loop, with no threads. The wrapped call returns None;
`flush` is a coroutine.

```python
import asyncio

from throttlebounce import async_debounce


@async_debounce(0.3)
async def push(state: dict[str, int]) -> None:
    await send(state)


async def main() -> None:
    push({"x": 1})
    push({"x": 2})
    await asyncio.sleep(0.4)  # only {"x": 2} is sent
```

## Testing without real time

Inject a fake clock, timer or scheduler so tests never sleep.

```python
from throttlebounce import throttle


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


clock = FakeClock()


@throttle(1.0, clock=clock)
def tick() -> int:
    return 1


assert tick() == 1  # first call runs
clock.now = 0.5
assert tick() == 1  # skipped, returns the last result, no real sleep
```

`debounce` takes `timer_factory=...` and the async pair take `scheduler=...` in
the same spirit: build a fake that records the scheduled action and fire it by
hand. See the test suite for complete fakes.

## Command line

The `throttlebounce` command debounces or throttles a shell command driven by
trigger lines on standard input, the job `entr` does internally. Each line is one
trigger; the content is ignored.

```
# Rebuild once edits settle (0.5s of quiet):
watch-files | throttlebounce debounce --wait 0.5 -- make build

# Deploy at most once every 10 seconds, including the final trigger:
tail -f events.log | throttlebounce throttle --interval 10 --trailing -- ./deploy.sh
```

Debounce flags: `--wait`, `--max-wait`, `--leading`, `--no-trailing` (needs
`--leading`). Throttle flags: `--interval`, `--trailing`. Run
`throttlebounce --help` for the full list.

# throttlebounce

Small, typed, zero-dependency debounce and throttle decorators, sync and async,
with injectable time so tests never wait on the clock.

## Install

```
pip install throttlebounce
```

## Usage

```python
from throttlebounce import debounce, throttle


@debounce(0.3)
def save(text: str) -> None:
    write_to_disk(text)


# Called on every keystroke, it writes once, 0.3s after typing stops.
save("h")
save("he")
save("hello")  # only this one reaches disk


@throttle(1.0)
def ping() -> None:
    send_heartbeat()


# Called in a tight loop, it fires at most once per second.
while running:
    ping()
```

`debounce` collapses a burst of calls into as few runs as the edges allow. By
default it runs once after the calls go quiet (trailing edge), with the last
call's arguments. `leading=True` also runs on the first call of a burst, and
`max_wait=...` forces a run at least that often during an unbroken stream so it is
never starved. The debounced callable returns `None` (the real run happens later
on a timer); it exposes `flush()` to run the pending call now and return its
result, `cancel()` to drop it, a `pending` flag, and a `result` property.

`throttle` runs the function at most once per interval (leading edge): the first
call runs, and calls inside the interval are skipped and return the last result.
`trailing=True` also runs the most recent skipped call when the interval closes,
so the final value is not lost; it shares the same `flush`, `cancel`, `pending`
and `result`, plus `reset()` to clear the window.

Both decorators are thread-safe. Both take an injectable dependency so tests run
without real waits: `throttle(interval, clock=...)` and
`debounce(wait, timer_factory=...)`.

```python
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

## Async

`async_debounce` and `async_throttle` wrap coroutine functions and schedule runs
on the running event loop, mirroring the sync options (`leading`, `trailing`,
`max_wait`). The wrapped call returns `None`; `flush()` is a coroutine.

```python
import asyncio

from throttlebounce import async_debounce


@async_debounce(0.3)
async def push(value: int) -> None:
    await send(value)


async def main() -> None:
    push(1)
    push(2)
    await asyncio.sleep(0.4)  # only 2 is sent
```

## Command line

The `throttlebounce` command debounces or throttles a shell command driven by
trigger lines on standard input, the job tools like `entr` do internally. Each
line is one trigger; its content is ignored.

```
# Rebuild once edits settle (0.5s of quiet):
watch-files | throttlebounce debounce --wait 0.5 -- make build

# Deploy at most once every 10 seconds, including the final trigger:
tail -f events.log | throttlebounce throttle --interval 10 --trailing -- ./deploy.sh
```

Run `throttlebounce --help` for the full flag list. See [GUIDE.md](GUIDE.md) for a
deeper tour of edges, `max_wait`, cancel/flush, thread-safety and testing.

## Why

Python's standard library has no debounce or throttle, the timing helpers that
JavaScript developers reach for constantly. The packages that exist fall short:

- [`throttle`](https://pypi.org/project/throttle/) has not been released since
  2020 and is effectively abandoned.
- [`throttler`](https://pypi.org/project/throttler/) is an `asyncio` rate limiter,
  not a sync decorator, and does not debounce.
- [`call-throttle`](https://pypi.org/project/call-throttle/) throttles but has no
  debounce.
- [`python-debouncer`](https://pypi.org/project/python-debouncer/) debounces but
  pulls in a runtime dependency and has not been touched since 2024.

None of them offer a clean, maintained, typed, zero-dependency pair of sync and
async `debounce` and `throttle` decorators that are thread-safe and testable
without real time. That is the gap this fills. Reach for it in desktop apps, CLIs,
background workers, GUIs and asyncio services: anywhere a function is triggered
more often than you want it to run.

## License

MIT. See [LICENSE](LICENSE).

## Links

- Website: https://lianes8studio.com
- GitHub: https://github.com/JaviLianes8
- LinkedIn: https://www.linkedin.com/in/jlianes/

# throttlebounce

Small, typed, zero-dependency sync debounce and throttle decorators with an injectable clock.

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
save("hello")        # only this one reaches disk


@throttle(1.0)
def ping() -> None:
    send_heartbeat()


# Called in a tight loop, it fires at most once per second.
while running:
    ping()
```

`debounce` collapses a burst of calls into a single run that happens once the
calls go quiet (trailing edge), with the last call's arguments. The debounced
callable returns `None`; the real run happens later on a background timer. It
exposes `flush()` to run the pending call now and return its result, `cancel()`
to drop it, and a `pending` flag.

`throttle` runs the function at most once per interval (leading edge): the first
call runs, and calls inside the interval are skipped and return the last result.
`reset()` clears the window.

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


assert tick() == 1       # first call runs
clock.now = 0.5
assert tick() == 1       # skipped, returns the last result, no real sleep
```

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

None of them offer a clean, maintained, typed, zero-dependency pair of sync
`debounce` and `throttle` decorators that are thread-safe and testable without
real time. That is the gap this fills. Reach for it in desktop apps, CLIs,
background workers and GUIs: anywhere a function is triggered more often than you
want it to run.

## License

MIT. See [LICENSE](LICENSE).

## Links

- Website: https://lianes8studio.com
- GitHub: https://github.com/JaviLianes8
- LinkedIn: https://www.linkedin.com/in/jlianes/

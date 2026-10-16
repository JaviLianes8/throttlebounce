# throttlebounce

Typed, zero-dependency debounce and throttle decorators for Python, sync and async,
with the edge semantics of lodash and Underscore and injectable time, so your tests
never sleep.

- `debounce`: run once a burst of calls goes quiet (trailing edge), on its first call
  (leading edge), or both, with an optional `max_wait` so a non-stop stream still runs.
- `throttle`: run at most once per interval, optionally also the last call of a busy
  window (trailing edge).
- `async_debounce` and `async_throttle`: the same for coroutine functions, on the
  running event loop.
- A `throttlebounce` command that debounces or throttles a shell command fed by
  trigger lines on standard input.

## Install

```
pip install throttlebounce
```

Python 3.10 or newer. No runtime dependencies.

## Quick start

```python
from throttlebounce import debounce, throttle

saved = []


@debounce(0.3)
def save(text: str) -> None:
    saved.append(text)


# Called on every keystroke; only the last call runs, 0.3 s after typing stops.
save("h")
save("he")
save("hello")
save.flush()  # run the pending call now instead of waiting
assert saved == ["hello"]


@throttle(1.0)
def progress(percent: int) -> int:
    return percent


assert progress(10) == 10  # the first call runs at once
assert progress(20) == 10  # inside the interval: skipped, returns the last result
```

Every wrapper has `flush()` (run the pending call now), `cancel()` (drop it),
`pending` and `result`; throttles also have `reset()`. The sync wrappers are
thread-safe, and the wrapped function always runs outside their lock.

## How the edges work

| Call | Runs |
| --- | --- |
| `debounce(w)` | once, `w` seconds after the last call of a burst, with that call's arguments |
| `debounce(w, leading=True, trailing=False)` | on the first call of a burst; a burst ends after `w` seconds without calls |
| `debounce(w, leading=True)` | on the first call, and again at the end only if more calls came |
| `debounce(w, max_wait=m)` | as above, and during an unbroken burst at most `m` seconds after the burst began or after the last run |
| `throttle(i)` | the first call, then the first call after each `i`-second window |
| `throttle(i, trailing=True)` | as above, and the last call made inside a window runs when that window closes |

These rules are checked against lodash 4.18.1 and Underscore 1.13.8 on 1200 seeded
call patterns, run live on a virtual clock. The only differences are two places
where lodash runs a call later than its own deadline, or twice inside one throttle
interval; the [guide](https://github.com/JaviLianes8/throttlebounce/blob/main/GUIDE.md#differences-from-lodash)
has the details.

## Async

```python
import asyncio

from throttlebounce import async_debounce

sent = []


@async_debounce(0.3)
async def push(value: int) -> None:
    sent.append(value)


async def main() -> None:
    push(1)
    push(2)
    await push.flush()


asyncio.run(main())
assert sent == [2]
```

## Methods

A decorated method keeps separate state for each object, so two editors never share
a pending save:

```python
from throttlebounce import debounce


class Editor:
    def __init__(self) -> None:
        self.saved = []

    @debounce(0.5)
    def save(self, text: str) -> None:
        self.saved.append(text)


a, b = Editor(), Editor()
a.save("one")
b.save("two")
a.save.flush()
b.save.flush()
assert (a.saved, b.saved) == (["one"], ["two"])
```

## Testing without real time

Pass a `clock` to the throttles, a `timer_factory` to `debounce` and
`throttle(trailing=True)`, and a `scheduler` to the async pair, and drive time by hand:

```python
from throttlebounce import throttle

now = 0.0


@throttle(1.0, clock=lambda: now)
def tick() -> str:
    return f"ran at {now}"


assert tick() == "ran at 0.0"
now = 0.5
assert tick() == "ran at 0.0"  # skipped
now = 1.0
assert tick() == "ran at 1.0"
```

## Command line

Each line on standard input is a trigger; the command after `--` runs on the chosen
schedule. When the input ends a pending run happens at once, and the exit status is
that of the last run.

```console
$ printf 'a\nb\nc\n' | throttlebounce debounce --wait 0.5 -- python -c "print('rebuilt')"
rebuilt
```

Typical uses: `watch-files | throttlebounce debounce --wait 0.5 -- make build`, or
`tail -f events.log | throttlebounce throttle --interval 10 --trailing -- ./deploy.sh`.
Run `throttlebounce --help` for every flag.

## Why

The standard library has no debounce or throttle. On PyPI, as of October 2026:

- [`throttle`](https://pypi.org/project/throttle/) last released in January 2020.
- [`python-debouncer`](https://pypi.org/project/python-debouncer/) needs
  `python-immutable` at runtime and last released in July 2024.
- [`throttler`](https://pypi.org/project/throttler/),
  [`asyncio-throttle`](https://pypi.org/project/asyncio-throttle/) and
  [`call-throttle`](https://pypi.org/project/call-throttle/) throttle or rate-limit
  calls; none of them debounces.

throttlebounce puts both in one small typed package, sync and async, with leading
and trailing edges and `max_wait` that behave as in lodash and Underscore (and a test
suite that runs those libraries to prove it), per-instance methods, and time you can
inject.

## Documentation

- [Guide](https://github.com/JaviLianes8/throttlebounce/blob/main/GUIDE.md): every
  option, the control methods, threads, async, testing, the command line, and the
  differences from lodash.
- [Changelog](https://github.com/JaviLianes8/throttlebounce/blob/main/CHANGELOG.md)

## License

MIT. See [LICENSE](https://github.com/JaviLianes8/throttlebounce/blob/main/LICENSE).

## Links

- Website: https://lianes8studio.com
- GitHub: https://github.com/JaviLianes8
- LinkedIn: https://www.linkedin.com/in/jlianes/

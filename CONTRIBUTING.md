# Contributing

Thanks for taking the time. This project keeps a small, predictable shape.

## Setup

```
pip install -r requirements-dev.txt
```

## Before you open a pull request

- Keep public API in `src/throttlebounce/__init__.py`; internals live in `_`-prefixed modules.
- Add a test for the behaviour you change. Tests inject time, disk and network; they
  never touch the real thing.
- Run the gate and make sure each step passes: `ruff format --check .`, `ruff check .`,
  `mypy --strict src tests` and `pytest` (`scripts/check.ps1` runs all four from a clone).
- One logical change per commit, imperative subject line.

Open an issue first if the change is large or shifts the public API.

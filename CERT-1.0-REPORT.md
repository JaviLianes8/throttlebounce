# throttlebounce 1.0.0 certification report

Progress:
- [x] Branch `release/1.0.0` created from `main` (0.2.0, 7a38e3a; PyPI has 0.1.0)
- [x] Baseline gates run on 0.2.0
- [x] Real ground truth: lodash 4.18.1 and Underscore 1.13.8 run live on a virtual clock (item 7)
- [x] API review and 1.0.0 API changes (item 1)
- [x] Errors, typing, docstrings and doctests (items 2 to 5)
- [x] Contract, fuzz and author mutation round (items 6, 9, 18)
- [x] Docs: README, GUIDE, CHANGELOG (items 11, 12)
- [x] Packaging, e2e and upgrade from PyPI 0.1.0 (items 8, 10, 13, 14), author run
- [ ] Five QA lenses report PASS (item 19)
- [ ] Independent reviewer reports PASS (item 16)
- [ ] Gates (item 15), final run
- [ ] PR and trace guard CLEAN (item 17); merge and publish left to the maintainer

## Baseline on 0.2.0 (before any change)

Fresh clone of `main` (7a38e3a): `ruff format --check .`, `ruff check .` and
`mypy --strict src tests` exit 0; `pytest` 47 passed without the venv tests; no doctests.
PyPI has 0.1.0 only; 0.2.0 was never published.

Defects found in 0.2.0 and 0.1.0:

- `max_wait` ended the burst at each deadline run, so the leading edge fired again in the
  middle of a burst and the next deadline drifted (counted from the next call, not from
  the run). With the trailing edge off, calls were still kept pending, and `flush()` ran
  them.
- A timer thread that had already started when a newer call replaced it still ran the
  pending call, early.
- Decorated methods did not work: the wrapper had no `__get__`, so `self` was never
  passed (0.1.0 too).
- Async runs were held only through the latest task, so an earlier run could be
  garbage-collected halfway.
- Durations were not checked: NaN let every throttled call through, an infinite or very
  long wait crashed the timer thread and left the call pending forever, `True` was a
  duration (0.1.0 too).
- Attributes of the wrapped callable were copied over the wrapper's own state (the CLI
  passed an object whose `_lock` replaced the wrapper's).
- CLI: always exit 0, tracebacks for bad values, overlapping runs, a trailing run could be
  cut off at exit.
- Tests slept on the real clock with tight margins (flaky on a loaded machine).

## Ground truth (item 7)

`tests/oracle/MANIFEST.json` names the npm tarballs of lodash 4.18.1 and Underscore 1.13.8
(URL, npm sha1, size, sha256, licence, fetched 2026-10-16); `scripts/fetch_oracles.py`
downloads them into the gitignored `tests/oracle/<name>/` and checks the hashes.
`tests/oracle/run.cjs` (written here) runs call patterns through the libraries' own
`debounce` and `throttle` with `Date.now`, `setTimeout` and `clearTimeout` replaced by a
virtual clock. `scripts/oracle_fixture.py` generated 1200 seeded scenarios (waits of 0,
1, 10, 25 and 100 ms, gaps around the wait, ties, every shared option) and recorded what
the libraries did (Node v24.18.0) in `tests/fixtures/oracle_runs.json`: program output,
not hand-written data. No third-party text is committed.

`tests/test_oracle.py` replays every scenario through the sync and the async wrappers on
the same virtual clock:

- 992 scenarios match run for run (time and arguments), and for throttles the value each
  call returned: Underscore's debounce (trailing, and leading as `immediate`) and
  throttle (both trailing settings), lodash's debounce without `maxWait` or with
  `maxWait` at least twice `wait`, and lodash's throttle without a trailing edge.
- The other 208 are lodash's throttle with a trailing edge and lodash's debounce with
  `maxWait` under twice `wait`. 160 match; the 48 that differ (39 throttles, 9 debounces) are pinned: at the first
  run that differs, either lodash ran inside the interval of the previous run, or
  throttlebounce ran exactly at the deadline and lodash later. Reading lodash's source
  explains both: after a deadline run lodash restarts its timer with the full `wait` at
  the next call. The GUIDE states both differences.
- With Node and the fetched libraries present, the test also reruns all 1200 scenarios
  live and compares them with the fixture.

Writing the harness exposed one artefact, fixed before recording: Underscore's throttle
treats clock readings below its wait as "ran at time 0", so the virtual clock reports a
far epoch, as a real clock does.

## API review (item 1)

Kept from 0.1.0 with the same signatures and defaults: `debounce(wait, *,
timer_factory)`, `throttle(interval, *, clock)`, `Debounced` (`cancel`, `flush`,
`pending`), `Throttled` (`reset`), `Clock`, `TimerFactory`. The 0.1.0 test suite passes
against 1.0.0 except its list of exported names.

Changed for 1.0.0, all in the CHANGELOG and the GUIDE: the 0.2.0 additions with the
`max_wait` and trailing-off semantics above; per-instance method binding; durations
checked when the decorator is built (`TypeError`, `ValueError`); `max_wait < wait`
refused; `Clock`, `TimerFactory` and `Scheduler` turned into documented callback
protocols (positional parameters, so any callable of the right shape fits); public names
report `throttlebounce` as their module; the wrapper classes take keyword defaults like
the decorators; the public `dev` extra replaced by `requirements-dev.txt`; CLI exit
status and usage errors.

Kept on purpose: throttle defaults to `trailing=False` (0.1.0 behaviour) and has no
`leading=False`; a debounced call returns None.

## Errors, typing, docs (items 2 to 5)

- `__all__` lists the eleven public names; `tests/test_contract.py` pins it.
- Every public name has a docstring with a doctest (11 doctests, run by `pytest` through
  `--doctest-modules`). Every Python example and console transcript in README and GUIDE
  runs in `tests/test_docs.py`.
- `mypy --strict src tests` clean; `py.typed` shipped; no `Any` in the public signatures
  except `Debounced[..., R]` for a method read through an instance.
- Errors: `TypeError` for a duration that is not a real number, `ValueError` for one a
  timer cannot wait or for an impossible option combination; messages under 80
  characters and never echo the value.

## Contracts, fuzz and mutations (items 6, 9, 18)

Contracts: `test_contract*.py` (API, edges, timers, methods, async), `test_oracle.py`,
`test_real_time.py` (default timers and loop, with waits that never race), `test_cli.py`,
`test_e2e_cli.py`, `test_docs.py`. `test_fuzz.py`: 300 seeded plans of calls, `flush`,
`cancel` and `reset` where the sync and async wrappers must agree run for run, every run
is a real earlier call, and the timer count stays bounded; 200,000 calls keep the live
timer queue at most 4; a run that calls its own wrapper does not deadlock.

Author mutation round: 48 mutations over every module, each applied alone to a fresh
clone of the pushed branch on Elena's PC (CPython 3.14.2), suite with `-x`, no bytecode,
file restored after; baseline green before and after.

| # | Module | Mutation | Caught by |
| --- | --- | --- | --- |
| 1 | `_edges` | expired deadline does not open a new burst | `test_contract_edges::test_a_deadline_with_trailing_off_opens_a_new_burst_on_the_next_call` |
| 2 | `_edges` | leading edge inverted | `test_async::test_async_debounce_collapses_a_burst_into_one_trailing_run` |
| 3 | `_edges` | pending kept with trailing off | `test_async::test_async_debounce_leading_runs_the_first_call_at_once` |
| 4 | `_edges` | old quiet timer not cancelled | `test_contract_edges::test_debounce_cancel_and_flush_end_the_burst` |
| 5 | `_edges` | quiet delay doubled | `test_contract_timers::test_timer_delays_are_the_wait_the_deadline_and_the_rest_of_the_window` |
| 6 | `_edges` | deadline not started with the burst | same |
| 7 | `_edges` | deadline uses `wait` | same |
| 8 | `_edges` | stale timers treated as the deadline | `test_contract_timers::test_a_replaced_timer_that_fires_late_is_ignored` |
| 9 | `_edges` | expired flag never set | `test_contract_edges::test_a_deadline_with_trailing_off_opens_a_new_burst_on_the_next_call` |
| 10 | `_edges` | deadline not restarted after a deadline run | `test_fuzz::test_two_hundred_thousand_calls_keep_a_bounded_timer_queue` |
| 11 | `_edges` | end of burst leaves the deadline timer running | survived; killed by `test_contract_timers::test_nothing_stays_scheduled_once_a_burst_ends` |
| 12 | `_edges` | flush does not end the burst | `test_contract_edges::test_debounce_cancel_and_flush_end_the_burst` |
| 13 | `_edges` | cancel keeps the pending call | `test_async::test_async_debounce_cancel_drops_the_pending_call` |
| 14 | `_edges` | `end()` marks the deadline expired | equivalent: `end()` also clears the quiet timer, so the next call opens a burst either way, and `call()` resets the flag |
| 15 | `_edges` | window boundary exclusive | `test_contract_edges::test_a_run_that_raises_propagates_and_leaves_the_wrapper_usable` |
| 16 | `_edges` | small backwards clock jumps keep the window | `test_contract_edges::test_a_clock_that_goes_backwards_closes_the_window` |
| 17 | `_edges` | trailing timer waits a full interval | `test_contract_timers::test_timer_delays_are_the_wait_the_deadline_and_the_rest_of_the_window` |
| 18 | `_edges` | leading run does not open a window | `test_async::test_async_throttle_runs_the_first_call_and_skips_within_the_interval` |
| 19 | `_edges` | leading run keeps the stale pending call | `test_contract_edges::test_throttle_cancel_keeps_the_window_and_reset_clears_it` |
| 20 | `_edges` | trailing run does not open a window | `test_contract_edges::test_throttle_flush_opens_a_new_window` |
| 21 | `_edges` | stale throttle timer runs | `test_contract_timers::test_a_cancelled_throttle_timer_that_fires_late_is_ignored` |
| 22 | `_edges` | throttle flush leaves its timer running | survived; killed by `test_contract_timers::test_nothing_stays_scheduled_once_a_burst_ends` |
| 23 | `_edges` | `reset` does nothing | `test_contract_async::test_async_flush_and_reset_mirror_the_sync_throttle` |
| 24 | `_edges` | throttle always trailing | `test_cli::test_throttle_runs_the_first_trigger_and_with_trailing_the_last` |
| 25 | `_types` | booleans accepted | `test_contract_api::test_a_duration_that_is_not_a_real_number_is_a_type_error` |
| 26 | `_types` | zero refused | `test_contract_api::test_any_finite_real_duration_is_accepted` |
| 27 | `_types` | no upper bound | `test_cli::test_usage_errors_exit_2_with_a_short_message` |
| 28 | `_types` | `max_wait == wait` refused | `test_contract_api::test_debounce_option_errors_are_raised_before_decorating` |
| 29 | `_types` | both edges off accepted | `test_async::test_async_rejects_bad_arguments` |
| 30 | `_types` | timer threads not daemon | `test_real_time::test_debounce_runs_on_a_real_daemon_timer_thread` |
| 31 | `_types` | overflowing ints accepted as zero | `test_contract_api::test_a_duration_a_timer_cannot_wait_is_a_value_error` |
| 32 | `_debounce` | flush discards the result | `test_cli::test_a_burst_runs_the_command_once_and_the_exit_status_is_that_run` |
| 33 | `_debounce` | result not stored | `test_contract_api::test_debounce_calls_return_none_and_throttle_calls_return_a_result` |
| 34 | `_debounce` | timers never started | `test_contract_edges::test_a_deadline_with_trailing_off_opens_a_new_burst_on_the_next_call` |
| 35 | `_debounce` | methods not bound | `test_contract_methods::test_each_instance_keeps_its_own_pending_call` |
| 36 | `_debounce` | bound copy swaps the edges | same |
| 37 | `_throttle` | skipped call returns None | `test_contract_api::test_attributes_of_the_wrapped_callable_never_replace_the_wrapper_state` |
| 38 | `_throttle` | bound copy loses the injected clock | survived; killed by `test_contract_methods::test_each_instance_has_its_own_throttle_window` |
| 39 | `_async_debounce` | tasks not held | `test_contract_async::test_a_spawned_run_survives_garbage_collection_until_it_finishes` |
| 40 | `_async_debounce` | async result not stored | `test_async::test_async_debounce_flush_runs_the_pending_call_and_returns_it` |
| 41 | `_async_throttle` | async flush opens the window at time 0 | `test_fuzz::test_sync_and_async_agree_and_every_run_is_a_real_earlier_call` |
| 42 | `_bind` | bound wrapper not cached | `test_contract_methods::test_each_instance_keeps_its_own_pending_call` |
| 43 | `_bind` | cache key from the function name, not the attribute | survived; killed by `test_contract_methods::test_two_attributes_wrapping_one_function_stay_separate` |
| 44 | `_cli` | exit status ignored | `test_cli::test_a_burst_runs_the_command_once_and_the_exit_status_is_that_run` |
| 45 | `_cli` | start failure exits 1 | `test_cli::test_a_command_that_cannot_start_exits_127` |
| 46 | `_cli` | `--leading` drops the trailing edge | `test_cli::test_leading_and_trailing_runs_both_count` |
| 47 | `_cli` | separator kept in the command | `test_cli::test_split_command_separates_options_from_the_command` |
| 48 | `_cli` | interrupt exits 1 | `test_cli::test_an_interrupt_drops_the_pending_run_and_exits_130` |

Result: 43 killed at once, 4 survivors (11, 22, 38, 43) killed by the contracts added in
the commits after the round (each confirmed to fail on its mutant), 1 equivalent (14).
Mutation 8 first produced a syntax error and was rewritten as `elif True:`.

## Packaging and end-to-end (items 8, 10, 14), author run

- `python -m build` and `twine check --strict` on a clean clone: both PASSED.
- Wheel: the nine package modules, `py.typed`, LICENSE, metadata and the console script
  entry point. Sdist: `src`, `tests` (with the oracle fixture, manifest and runner, not
  the fetched libraries), the two oracle scripts, README, GUIDE, CHANGELOG,
  CONTRIBUTING, LICENSE, `requirements-dev.txt`, pyproject and the `.gitignore`
  hatchling adds; no report, round notes, check scripts or scratch files.
- The wheel in fresh venvs, the suite run from the extracted sdist with `src` removed
  (so it imports the installed wheel and drives its console script): green on CPython
  3.10.19, 3.11.5, 3.12.12, 3.13.2, 3.14.2 and 3.14.2 free-threaded on this PC, and on
  3.14.2 on Elena's PC. 3.10.19, 3.12.12 and 3.14.2 were fetched with uv into a scratch
  folder for the run; 3.8 and 3.9 are below `requires-python`.
- Sabotage: with the installed console script removed, the end-to-end tests fail.
- PyPI 0.1.0 installed, then upgraded in place to the 1.0.0 wheel, same probe before and
  after: the trailing debounce, the throttle and their results are identical; exported
  names 6 then 11; NaN, infinity, `True` and 1e7 seconds accepted then refused
  (`ValueError`, `TypeError`); a decorated method `TypeError` then works.

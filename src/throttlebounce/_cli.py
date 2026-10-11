"""Command line: debounce or throttle a command driven by trigger lines on stdin.

Pipe a stream of trigger lines (for example from a file watcher) into this tool
and it runs a command on the debounced or throttled schedule, the same job tools
like ``entr`` do internally. Each line of standard input is one trigger; the line
content is ignored.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Callable, Sequence

from . import __version__
from ._debounce import Debounced, debounce
from ._throttle import Throttled, throttle

_EPILOG = """\
examples:
  # Rebuild once typing/edits settle, waiting 0.5s of quiet:
  watch-files | throttlebounce debounce --wait 0.5 -- make build

  # Run a deploy at most once every 10 seconds, including the final trigger:
  tail -f events.log | throttlebounce throttle --interval 10 --trailing -- ./deploy.sh
"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="throttlebounce",
        description="Debounce or throttle a command driven by trigger lines on stdin.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"throttlebounce {__version__}")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    deb = subparsers.add_parser("debounce", help="run the command after triggers go quiet")
    deb.add_argument("--wait", type=float, required=True, help="seconds of quiet before running")
    deb.add_argument("--max-wait", type=float, default=None, help="force a run at least this often")
    deb.add_argument("--leading", action="store_true", help="also run on the first trigger")
    deb.add_argument("--no-trailing", action="store_true", help="skip the run after quiet")

    thr = subparsers.add_parser("throttle", help="run the command at most once per interval")
    thr.add_argument("--interval", type=float, required=True, help="minimum seconds between runs")
    thr.add_argument("--trailing", action="store_true", help="also run the final trigger")

    return parser


def _split_command(args: Sequence[str]) -> tuple[list[str], list[str]]:
    """Split argv at the first ``--`` into options and the command to run."""
    args = list(args)
    if "--" in args:
        index = args.index("--")
        return args[:index], args[index + 1 :]
    return args, []


def _make_runner(command: list[str]) -> Callable[[], int]:
    def run() -> int:
        return subprocess.run(command).returncode

    return run


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the ``throttlebounce`` console script."""
    raw = sys.argv[1:] if argv is None else list(argv)
    options, command = _split_command(raw)
    parser = _build_parser()
    namespace = parser.parse_args(options)
    if not command:
        parser.error("a command is required after --")

    run = _make_runner(command)
    scheduled: Debounced[[], int] | Throttled[[], int]
    if namespace.mode == "debounce":
        if namespace.no_trailing and not namespace.leading:
            parser.error("--no-trailing needs --leading, or nothing would ever run")
        scheduled = debounce(
            namespace.wait,
            leading=namespace.leading,
            trailing=not namespace.no_trailing,
            max_wait=namespace.max_wait,
        )(run)
    else:
        scheduled = throttle(namespace.interval, trailing=namespace.trailing)(run)

    for _line in sys.stdin:
        scheduled()
    scheduled.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

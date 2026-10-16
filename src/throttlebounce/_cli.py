"""Command line: debounce or throttle a command driven by trigger lines on stdin.

Pipe a stream of trigger lines (for example from a file watcher) into this tool and it
runs a command on the debounced or throttled schedule. Each line of standard input is
one trigger; its content is ignored. When the input ends, a pending run happens at
once, and the exit status is that of the last run (0 if the command never ran).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import threading
from collections.abc import Sequence

from . import __version__
from ._debounce import Debounced, debounce
from ._throttle import Throttled, throttle

_EPILOG = """\
examples:
  # Rebuild once edits settle, after 0.5 seconds of quiet:
  watch-files | throttlebounce debounce --wait 0.5 -- make build

  # Deploy at most once every 10 seconds, including the final trigger:
  tail -f events.log | throttlebounce throttle --interval 10 --trailing -- ./deploy.sh

Runs never overlap. Exit status: that of the last run, 0 if the command never ran,
127 if it could not be started, 2 for a usage error, 130 when interrupted.
"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="throttlebounce",
        usage="throttlebounce {debounce,throttle} [options] -- command [args ...]",
        description="Debounce or throttle a command driven by trigger lines on stdin.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"throttlebounce {__version__}")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    deb = subparsers.add_parser("debounce", help="run the command after triggers go quiet")
    deb.add_argument("--wait", type=float, required=True, help="seconds of quiet before running")
    deb.add_argument("--max-wait", type=float, default=None, help="run at least this often")
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


class _Runner:
    """Runs the command one at a time and remembers the last exit status."""

    def __init__(self, command: list[str]) -> None:
        self._command = command
        self._lock = threading.Lock()
        self.status = 0

    def __call__(self) -> int:
        with self._lock:
            try:
                status = subprocess.run(self._command, check=False).returncode
            except OSError as error:
                print(f"throttlebounce: cannot run {self._command[0]!r}: {error}", file=sys.stderr)
                status = 127
            self.status = status
            return status

    def last_status(self) -> int:
        """Wait for a run in progress, then return the last exit status."""
        with self._lock:
            return self.status


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the ``throttlebounce`` console script."""
    options, command = _split_command(sys.argv[1:] if argv is None else argv)
    parser = _build_parser()
    namespace = parser.parse_args(options)
    if not command:
        parser.error("a command is required after --")
    if namespace.mode == "debounce" and namespace.no_trailing and not namespace.leading:
        parser.error("--no-trailing needs --leading, or nothing would ever run")

    runner = _Runner(command)
    scheduled: Debounced[[], int] | Throttled[[], int]
    try:
        if namespace.mode == "debounce":
            scheduled = debounce(
                namespace.wait,
                leading=namespace.leading,
                trailing=not namespace.no_trailing,
                max_wait=namespace.max_wait,
            )(runner)
        else:
            scheduled = throttle(namespace.interval, trailing=namespace.trailing)(runner)
    except ValueError as error:
        parser.error(str(error))

    try:
        for _line in sys.stdin:
            scheduled()
    except KeyboardInterrupt:
        scheduled.cancel()
        return 130
    scheduled.flush()
    return runner.last_status()


if __name__ == "__main__":
    raise SystemExit(main())

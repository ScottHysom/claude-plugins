"""Let a CI script exit 0, silently, when the reader of its output goes away.

Run `python3 .github/scripts/check-tests.py naming | head -1` and `head`
closes the pipe after one line. Python writes stdout through a buffer, so a
command usually returns with its output still unwritten, and Python flushes it
at exit, after main() has returned. A closed pipe fails that flush with
`Exception ignored ... BrokenPipeError` on stderr and exit 120, out of reach
of any handler in main(). argparse's --help does the same: it prints and exits
before the command runs.

Each script in .github/scripts/ decorates its main() with `exits_ok`:

    import closed_pipe

    @closed_pipe.exits_ok
    def main(argv=None):
        ...

The decorator flushes stdout inside its own try, after main() returns and
after argparse exits. On a closed pipe it points stdout at the null device, so
the flush at exit has nowhere to fail, and returns OK.

The file name has no hyphen so that the scripts can import it. Running a
script puts its own directory first on sys.path, which is how the import
resolves; the tests' conftest.py adds the directory for the scripts it loads
by path. A plugin script cannot import this: each plugin installs on its own,
so prose.py, todos.py and gitify.py each carry the same few lines.
"""

import functools
import os
import sys

OK = 0


def exits_ok(main):
    """main(), returning OK without a traceback when stdout's reader has gone."""

    @functools.wraps(main)
    def guarded(*args, **kwargs):
        try:
            try:
                code = main(*args, **kwargs)
            except SystemExit:
                sys.stdout.flush()
                raise
            sys.stdout.flush()
            return code
        except BrokenPipeError:
            silence_stdout()
            return OK

    return guarded


def silence_stdout():
    """Point stdout at the null device, so the flush at exit cannot fail.

    The output still buffered when the pipe closed stays in the buffer, and
    Python flushes it again at exit.
    """
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull, sys.stdout.fileno())
    finally:
        os.close(devnull)

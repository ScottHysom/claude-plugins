"""A pytest plugin that writes what a run collected and how each test ended.

check-tests.py fails-on-base loads it into the pytest runs it starts, with
`-p outcomes_plugin` and this directory on PYTHONPATH. It is not a test file
and pytest never loads it on its own.

It reads two environment variables:

  CHECK_TESTS_OUTCOMES  the JSON file to write when the session ends
  CHECK_TESTS_SELECT    a JSON file holding a list of node ids. When set,
                        every other collected test is deselected, so a run
                        given whole files runs only these. A file rather
                        than the list itself, since a branch can add more
                        tests than one environment variable holds.

The file it writes holds:

  collected  each collected node id, mapped to its passes_on_base marker's
             reason, or null when it has no marker. A marker given no
             argument maps to "".
  outcomes   each test that ran, mapped to "passed", "failed" or "skipped".
             A test passes only when its setup, call and teardown all pass.
  errors     how many files failed to collect.
"""

import json
import os

OUTCOMES_ENV = "CHECK_TESTS_OUTCOMES"
SELECT_ENV = "CHECK_TESTS_SELECT"
MARKER = "passes_on_base"

_collected = {}
_outcomes = {}
_errors = []


def _reason(item):
    mark = item.get_closest_marker(MARKER)
    if mark is None:
        return None
    return str(mark.args[0]) if mark.args else ""


def pytest_collection_modifyitems(session, config, items):
    for item in items:
        _collected[item.nodeid] = _reason(item)
    select = os.environ.get(SELECT_ENV)
    if select is None:
        return
    with open(select) as fh:
        wanted = set(json.load(fh))
    keep = [item for item in items if item.nodeid in wanted]
    dropped = [item for item in items if item.nodeid not in wanted]
    if dropped:
        config.hook.pytest_deselected(items=dropped)
    items[:] = keep


def pytest_collectreport(report):
    if report.failed:
        _errors.append(report.nodeid)


def pytest_runtest_logreport(report):
    # A later phase that did not pass decides the outcome. A passing setup
    # or teardown does not overwrite the call's result.
    if report.when == "call" or report.outcome != "passed":
        if _outcomes.get(report.nodeid, "passed") == "passed":
            _outcomes[report.nodeid] = report.outcome


def pytest_sessionfinish(session, exitstatus):
    path = os.environ.get(OUTCOMES_ENV)
    if path:
        with open(path, "w") as fh:
            json.dump({"collected": _collected, "outcomes": _outcomes, "errors": len(_errors)}, fh)

"""An edit that only changed a number, a link or some whitespace is not a
prose decision. Classifying those keeps them out of the evidence the model is
asked to infer a rule from.
"""

import pytest

import prose


@pytest.mark.parametrize(
    ("before", "after", "signal"),
    [
        pytest.param("we saw 3 things", "we saw 4 things", "numeric-only", id="numeric"),
        pytest.param("a  b", "a b", "whitespace-only", id="whitespace"),
        pytest.param("see [x](/a)", "see [x](/b)", "link-only", id="link"),
        pytest.param("short line", "a longer line", None, id="real-edit"),
    ],
)
def test_signal_classification(before, after, signal):
    assert prose.classify_signal(before, after) == signal

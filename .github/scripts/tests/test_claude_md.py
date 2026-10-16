"""The rules CLAUDE.md gives an agent that a test can read for. An eval would
check that an agent follows them; these check that they are written."""

from pathlib import Path

import pytest

_CLAUDE_MD = Path(__file__).resolve().parents[3] / "CLAUDE.md"


def issues_section():
    text = _CLAUDE_MD.read_text(encoding="utf-8")
    return text.split("\n## Issues\n", 1)[1].split("\n## ", 1)[0]


@pytest.mark.spec("claudemd-reports-claim-first")
class DescribeTheClaimRuleInClaudeMd:
    def it_tells_the_agent_to_report_the_claim_before_other_work(self):
        rule = next(item for item in issues_section().split("\n- ") if "how the claim went" in item)
        assert "before any other work" in rule
        assert "`claim N`" in rule
        assert "#N" in rule
        assert "`issue/N`" in rule
        assert "exit 1" in rule

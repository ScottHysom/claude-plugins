## Rules for agents

These rules are the method's rules for agents that the flywheel plugin
follows. Each cites the principle it serves, and the plugin's `docs/`
defines each one.

### Level 1

- Build only what a need someone stated, or a constraint the platform forces,
  asks for. Before adding a command, an option or a branch, find the
  requirement it serves. Source: the method's `trace-behavior-to-need`.
- The owner decides, and agents record. When the work needs a decision the
  issue does not make, propose it on the issue and wait for the owner. Source:
  the method's `humans-decide-agents-record`.
- Work only on an issue labeled `approved`, and never add that label. A new
  need or constraint enters `specs/` only once the owner approves the issue
  that proposes it. Source: the method's `owner-admits-every-need`.
- Keep a change's intent in its issue, and link to the issue rather than
  copying it into the pull request or the code. Source: the method's
  `one-home-per-artifact`.
- Write a failing test first, then the code that passes it. Name the test for
  the behavior it checks, as `describe`/`it`, without the word "should".
  Source: the method's `write-behavior-tests-first`.

### Level 2

- Before writing code for an issue of more than one unit, post the plan on the
  issue, naming the requirement ids each unit builds, and wait for the owner
  to approve it. Source: the method's `approve-plan-before-code`.

### Level 3

- Change the loop one thing at a time, such as a model, an effort setting, a
  tool or a step. Measure the change against a baseline, and keep it only if
  the measures hold or improve. Source: the method's
  `improve-by-measured-trial`.
- When a mistake repeats, file an issue to turn it into a rule here, and when
  it repeats again, into a check or a hook. Source: the method's
  `repeat-mistakes-become-checks`.

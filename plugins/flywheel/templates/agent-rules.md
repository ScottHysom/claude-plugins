## Rules for agents

These rules are the playbook's rules for agents that the flywheel plugin
follows. Each level's section has a rule for every principle that level's
controls name, and each rule cites its principle. The plugin's `docs/`
defines each one.

### Level 1

- Build only what a need someone stated, or a constraint the platform forces,
  asks for. Before adding a command, an option or a branch, find the
  requirement it serves. Source: the playbook's `trace-behavior-to-need`.
- The owner decides, and agents record. When the work needs a decision the
  issue does not make, propose it on the issue and wait for the owner. Source:
  the playbook's `humans-decide-agents-record`.
- Drop a claim's commits, or close an issue as not planned, only after the
  owner has said so in chat. Source: the playbook's
  `humans-decide-agents-record`.
- Open each component's spec with what it deliberately does not do. Source:
  the playbook's `list-out-of-scope-first`.
- Take each need from a source outside the code, such as the owner, a brief
  or an issue, and cite that source. Never infer a need from what the code
  does. Source: the playbook's `source-needs-outside-code`.
- Work only on an issue labeled `approved`, and never add that label. A new
  need or constraint enters `specs/` only once the owner approves the issue
  that proposes it. Source: the playbook's `owner-admits-every-need`.
- Keep a change's intent in its issue, and link to the issue rather than
  copying it into the pull request or the code. Source: the playbook's
  `one-home-per-artifact`.
- Run the project's `build`, `test` and `check` commands to finish a unit,
  and do not open a pull request while `check` fails. Source: the playbook's
  `one-command-per-gate`.
- Write a failing test first, then the code that passes it. Name the test for
  the behavior it checks, as `describe`/`it`, without the word "should".
  Source: the playbook's `write-behavior-tests-first`.

### Level 2

- Treat a rule that only this file states as a request, and propose a check
  for each rule that matters. Never edit a check to get past it. Source: the
  playbook's `checks-over-instructions`.
- Do not merge a change whose code and spec disagree. Update the spec in the
  same pull request, or stop and ask. Source: the playbook's
  `no-merge-without-alignment`.
- Run the project's `verify` command before asking for review, since CI runs
  it on every pull request. Source: the playbook's `one-command-per-gate`.
- Open a pull request through the project's skill for opening one, or
  flywheel's open-pr when the project has none. Name each requirement id it
  adds, changes or removes in the section that `.flywheel/pr-template.md`
  marks, `## Requirements` without the file. Source: the playbook's
  `no-merge-without-alignment`.
- Never loosen a test or a check to make it pass. Confirm that each new test
  fails on the code before the change. Source: the playbook's
  `agents-never-weaken-checks`.
- Never add the `approved` label, by any route, and leave approval to the
  owner. Source: the playbook's `owner-admits-every-need`.
- Before writing code for an issue of more than one unit, post the plan on the
  issue, naming the requirement ids each unit builds, and wait for the owner
  to approve it. Source: the playbook's `approve-plan-before-code`.
- Review a pull request against the project's written review policy, its
  passes, its P0 to P3 scale and its cap on nits, and not against your own
  taste. Source: the playbook's `review-against-written-policy`.
- Leave the review of your own pull request to a reviewer that starts without
  your context. Source: the playbook's
  `separate-generation-from-verification`.

### Level 3

- When this file, a skill, a hook or the model behind a role changes, rerun
  the evals for the instructions it touches. Source: the playbook's
  `eval-instructions-on-change`.
- Work at the model and effort the roles file gives your role, and escalate
  to the owner rather than guess when a task needs more. Source: the playbook's
  `match-capability-to-task`.
- Merge only what the written merge policy lets through, and ask the owner
  about the rest. Source: the playbook's `autonomy-scales-with-risk`.
- Run the audit on its schedule, with its repeatable process, and file what
  it finds. Source: the playbook's `audit-on-schedule`.
- Name the decision each measure informs, and drop a measure that informs
  none. Source: the playbook's `measure-the-loop`.
- Let a script detect drift or a breach, and diagnose only what a script
  reports. Source: the playbook's `scripts-detect-models-diagnose`.
- Change the loop one thing at a time, such as a model, an effort setting, a
  tool or a step. Measure the change against a baseline, and keep it only if
  the measures hold or improve. Source: the playbook's
  `improve-by-measured-trial`.
- When a mistake repeats, file an issue to turn it into a rule here, and when
  it repeats again, into a check or a hook. Source: the playbook's
  `repeat-mistakes-become-checks`.

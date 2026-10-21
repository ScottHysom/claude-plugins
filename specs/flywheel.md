# flywheel

This file records what the flywheel plugin is for. SPEC-METHODOLOGY.md, at
the repo root, has the grammar of this file and the steps that add its
requirements.

## Out of scope

- Running the loop outside the Claude desktop app. The dispatcher starts its
  sessions through the app.
- Running in Cowork, the Claude desktop app's mode for a user's own files. The
  loop needs Claude Code and a clone with a GitHub remote.
- Issue trackers other than GitHub's.
- Choosing the model behind a role. Only the owner fills it in.

## need owner-installs-loop-as-plugin: Install the issue loop as a plugin

When the owner wants the issue loop in a repo, they want to install one plugin
that carries its script, skills, rules and docs, so the repo adopts it as it
adopts any other plugin.

Source: #643, and the method's `match-capability-to-task` and
`scripts-do-deterministic-work`.

- `setup-cmd-copies-script` (test): When `flywheel.py setup` runs in a
  project, it copies the script to `.flywheel/` beside a `.gitignore` that
  keeps it out of every commit, and prints the prefix later commands start
  with.
- `configinit-cmd-writes-roles-file` (test): When `flywheel.py config init`
  runs, it writes `.flywheel/roles.json` from the plugin's template with one
  entry per role, and refuses to overwrite one that exists.
- `configinit-cmd-writes-policies` (test): When `config init` runs, it also
  writes `.flywheel/review-policy.md` and `.flywheel/merge-policy.md` from the
  plugin's templates. It leaves as it is each file of the three that exists,
  names it and exits 1, and still writes the others.
- `configinit-cmd-names-owner-fields` (test): When `config init` writes a file
  with a field only the owner can fill, it names each such field in its
  result.
- `configinit-cmd-writes-gate-fields` (test): When `config init` writes
  `.flywheel/gates.json`, it writes `build`, `test`, `check` and `verify`
  under `gates`, unset, names each one as a field the owner fills in, and
  leaves each gate the file gives as it is.

## need contributor-reads-method-beside-plugin: Read the method beside the plugin

When a contributor or an adopting owner reads a principle id in a spec, a
template or a skill, they want to open the document that defines it from the
same install, so the id is a definition and not a pointer to another repo.

Source: #644, and the method's `one-home-per-artifact`.

- `ids-cmd-fails-unknown-id` (test): When `flywheel.py ids` finds a principle
  or stage-rule id cited in the plugin's templates, skills or
  `specs/flywheel.md` that no document under `docs/` defines, it names it and
  exits 1.

## need owner-keeps-claims-exclusive: Keep two agents off the same issue

When two agents are told to take the next issue at the same time, the owner
wants each to get a different one, so two agents never do the same work.

Source: README.md, under "Claiming an issue". #645 moved this need here from
specs/repo.md, which keeps the requirements this repo's own checks meet.

- `next-cmd-offers-free-issue` (test): When `flywheel.py queue` runs, it
  names the lowest-numbered open issue labeled `approved` that is unheld by
  any `issue/N` branch and unblocked by any open issue. It exits 0 even when
  every such issue is held or blocked. It does not offer a **tracking issue**
  (an issue labeled `tracking`, which groups a plan's issues as its
  sub-issues), or a sub-issue of an open tracking issue labeled `approved`.
- `queue-cmd-offers-up-to-count` (test): When `flywheel.py queue --count N`
  runs, it offers up to N free approved issues that no open issue blocks,
  oldest first, and says when fewer are free. With `--tracking`, it offers up
  to N of the plan's sub-issues in the plan's order, and stops with a warning
  before a sub-issue that lacks `approved`.
- `claim-cmd-picks-one-winner` (test): When two agents claim the same
  issue at once, `flywheel.py claim` lets exactly one create `issue/N`, and
  the other exits 1, names the holder and writes nothing.
- `claim-cmd-switches-to-issue-branch` (test): When `flywheel.py claim N`
  wins, it switches the clone to `issue/N`, and warns when the switch fails.
- `claim-cmd-stops-when-nobody-wins` (test): When the push fails and
  `issue/N` does not exist, `flywheel.py claim` exits 2 without writing to
  the issue.
- `next-cmd-moves-past-lost-claim` (test): When `flywheel.py claim --next`
  loses the claim on the issue `queue` offered, it claims the next free
  issue, until it wins or none is free, and then exits 1 saying why. With
  `--tracking N`, it takes #N's next free sub-issue, and stops where
  `queue --tracking N` stops. When the owner named the issue, as in
  `claim N`, a lost claim still stops the agent.

## need owner-orders-dependent-issues: Leave an issue until its blocker closes

When one issue waits on another, the owner wants agents told to take the next
issue to leave it until its blocker closes, so an agent builds only on work
that has landed.

Source: the owner's request on 2026-10-04, recorded in #345.

- `next-cmd-skips-blocked-issues` (test): When GitHub lists an open issue as
  blocking an issue, `flywheel.py queue` does not offer it. When every free
  issue is blocked, `queue` names each with its open blockers and exits 0,
  and `claim` still takes a blocked issue the owner names.

## need owner-works-one-plan: Work one approved plan in its order

When the owner has grouped one plan's issues under a tracking issue and
approved the plan, the owner wants to tell an agent to take the plan's next
issue, so agents work the plan in its listed order without picking issues
from outside it.

Source: the owner's request on 2026-10-05, recorded in #350.

- `next-cmd-follows-tracking-issue` (test): When `flywheel.py queue
  --tracking N` runs, it offers the first sub-issue in #N's listed order that
  is open, unheld and unblocked. It exits 1 when that sub-issue lacks
  `approved`, or when #N is not an open issue labeled both `tracking` and
  `approved`.
- `next-cmd-names-tracking-issue` (test): When an open tracking issue labeled
  `approved` takes its place in the queue, at the lowest number among itself
  and its open sub-issues, before the issue `flywheel.py queue` would offer,
  `queue` names the tracking issue and the command to follow it, and exits 0.
- `next-cmd-reports-finished-plan` (test): When every sub-issue of #N is
  closed, `flywheel.py queue --tracking N` says the plan is finished, names
  the command that closes #N, and exits 0. An open sub-issue keeps the plan
  unfinished even when a claim holds it, and so does a tracking issue without
  sub-issues.
- `planclose-cmd-closes-finished-plan` (test): When `flywheel.py plan close N`
  runs on an open issue labeled both `tracking` and `approved` whose
  sub-issues are all closed, it closes #N with a comment naming them. It exits
  1 without writing to #N when any of these holds:
  - any sub-issue of #N is open.
  - #N lacks sub-issues.
  - #N is closed, or lacks either label.

## need owner-approves-plan-once: Approve a plan's issues once

When a plan yields several issues, the owner wants to approve the whole plan
once, and have its issues filed, linked and grouped under a tracking issue
exactly as approved, so the order GitHub holds is the order the owner
approved.

Source: the owner's request on 2026-10-05, after #347 and its sub-issues were
filed by hand, recorded in #359. #647 moved this need here from
specs/repo.md, which keeps the requirements under constraints that the plan
commands meet.

- `planreport-cmd-checks-each-draft` (test): When `flywheel.py plan report
  --drafts <file>` reads a plan, it names every fault in one run, does not
  print a token, and refuses each issue that meets any of these:
  - has a body that does not open with `**Claude:**`.
  - lacks a heading CLAUDE.md asks for.
  - does not carry exactly one kind label and one area label.
  - carries `approved` or `tracking`.
  - carries a label the repository does not have.
- `planreport-cmd-checks-plan-links` (test): When a key repeats, a `{KEY}` or a
  `blocked_by` key does not name an issue in the plan, a body names an issue
  filed after it, a blocker outside the plan is anything but an open issue, or
  the links form a cycle, `plan report` refuses the plan and names each fault.
- `planreport-cmd-accepts-one-issue` (test): When `flywheel.py plan report`
  reads a plan of one issue with no tracking issue, it checks and reports
  that issue alone, and `plan file` files it without a tracking issue. It
  refuses a plan of several issues without a tracking issue.
- `planreport-cmd-orders-by-links` (test): When `plan report` accepts a plan,
  it puts each issue after the issues that block it, with ties in the plan's
  listed order. It shows each issue whole, and the tracking issue's body as
  it will be filed, with an Order section written from the links.
- `planfile-cmd-requires-token` (test): When `flywheel.py plan file --drafts
  <file> --token <token>` is given a token that does not match the plan, the
  repository and its labels as they are now, or the plan now fails one of the
  checks `plan report` made, it exits 1 without filing anything.
- `planfile-cmd-files-in-order` (test): When `plan file` runs with a current
  token, it files the issues in the report's order, each `{KEY}` replaced by
  the number filed, and adds each "blocked by" link. It then files the
  tracking issue labeled `tracking`, and adds the sub-issues in that order.
- `planfile-cmd-verifies-links` (test): When `plan file` has filed a plan, it
  reads every link and the sub-issues back from GitHub, and exits 1 naming
  each that differs from the plan.
- `planreport-cmd-shows-filed-issue` (test): When a plan's issue gives the
  `number` of an issue already filed in place of a draft, `plan report` shows
  that issue as GitHub holds it, marked as filed already. It refuses a number
  that is closed, that cannot be read, or that two keys name.
- `planfile-cmd-groups-filed-issue` (test): When `plan file` files a plan that
  names an issue by its `number`, it does not file or edit that issue. It adds
  the issue's "blocked by" links, adds it as a sub-issue in the plan's order,
  and reads it back with the rest.
- `fileissue-shows-report-whole` (step): When the file-issue skill asks the owner
  to approve a plan, it shows the report file whole, as a private artifact (a
  page Claude publishes on claude.ai) or, where it cannot publish one, in its
  reply, rather than a summary of its own.
- `plandraft-cmd-makes-own-file` (test): When `flywheel.py plan draft` runs, it
  makes an empty file in the temporary directory, named so that no other run
  gets the same file, and prints its literal path.
- `fileissue-drafts-in-own-file` (step): When the file-issue skill drafts a
  plan, it writes the plan to the file `plan draft` made for that run, and
  every later step of the run reads that file, so a plan another session
  drafts does not replace it.

## need owner-sees-held-issues: See from the issue list which issues are held

When an agent or the owner looks at the issue list, they want a claimed issue
to show as claimed, and a label that disagrees with its branch to be reported,
so a reader never takes a stale label for a claim.

Source: README.md, under "Claiming an issue", and #33.

- `claim-cmd-adds-in-progress-label` (test): When `flywheel.py claim` wins,
  it adds `in-progress` and a claim comment, and if either fails, it warns and
  still exits 0.
- `stale-cmd-reports-claims-left-behind` (test): When any of these holds, `flywheel.py stale` fails and names the remedy:
  - a label has no branch.
  - a closed issue keeps its label.
  - a closed issue keeps its branch.
  - an open issue has its branch and lacks the label.

## need owner-frees-abandoned-claims: Free an abandoned claim without losing work

When an agent stops without opening a pull request, the owner wants its claim
freed for someone else, so the issue does not stay held, and wants every commit
on the claim branch kept through the freeing.

Source: README.md, under "Claiming an issue", and CLAUDE.md, under "Issues".

- `release-cmd-frees-unused-claim` (test): When `flywheel.py release N`
  finds `issue/N` with no commits off main, or only the `in-progress` label,
  it deletes the branch, removes the label and comments.
- `release-cmd-keeps-work` (test): When `issue/N` has commits off main, or
  changed after `release` checked it, `flywheel.py release` exits 1 and
  deletes nothing.
- `release-cmd-requires-held-claim` (test): When `flywheel.py release N`
  finds neither `issue/N` nor the `in-progress` label, it exits 1 without
  commenting, so only an issue that was held can read as released.

## need owner-clears-merged-claims: Clear a merged claim's local branch

When a pull request from `issue/N` has merged, the owner wants the local claim
branch removed without anyone typing git commands, so claim branches do not
pile up.

Source: #289, and README.md, under "Claiming an issue".

- `clear-cmd-deletes-merged-branch` (test): When `flywheel.py clear N` finds
  #N closed, and the local `issue/N` either inside the head of a merged pull
  request from it or not holding any change `origin/main` lacks, it does
  these:
  - switches any worktree that has the branch checked out to a detached
    `origin/main`.
  - leaves every worktree in place.
  - deletes the branch.
- `clear-cmd-keeps-unmerged-work` (test): When #N is open, the local `issue/N`
  is missing, or it holds a commit that every merged pull request from it lacks
  and a change `origin/main` lacks, `flywheel.py clear` exits 1, says what to
  do next and deletes nothing.
- `clear-cmd-keeps-uncommitted-changes` (test): When a worktree that has
  `issue/N` checked out has uncommitted changes, `flywheel.py clear N` exits
  1, names the worktree and says to commit or discard the changes, and neither
  moves a worktree nor deletes anything, with or without `--dry-run`.

## need owner-prevents-stale-branches: Keep finished branches from piling up

When a session's work has merged or was never started, the owner wants every
local branch it left removed without typing git commands, so the clone keeps
only live branches.

Source: #294, and README.md, under "Claiming an issue". specs/repo.md keeps
the requirements on this repo's hook that runs `sweep`.

- `sweep-cmd-deletes-merged-branches` (test): When `flywheel.py sweep` runs,
  it deletes every local branch but `main` whose tip is inside the head of a
  merged pull request from that branch, or which does not hold any change
  `origin/main` lacks, as a branch without commits of its own does.
- `sweep-cmd-keeps-live-branches` (test): When a local branch holds a change
  `origin/main` lacks, is checked out in any worktree, or still exists on
  `origin`, `flywheel.py sweep` keeps it and prints it with the reason.

## need owner-starts-worker-from-brief: Start a worker session from what the owner approved

When the owner or the dispatcher starts a session on an issue, they want its
first message to carry the issue as approved, the owner's comments, the role
and the gate commands, so the session works from what the owner approved and
nothing else.

Source: #645, and the method's `humans-decide-agents-record` and
`owner-admits-every-need`.

- `brief-cmd-prints-issue-as-approved` (test): When `flywheel.py brief N`
  runs, it prints the skill that works the issue, the issue's title and body
  as they stood when `approved` was last added, the owner's comments since, the role, and the gate commands
  from `.flywheel/gates.json`, and warns when `.flywheel/` does not give the
  role's tier or the gate commands. It exits 1 when the body changed after
  approval, or the issue lacks `approved`.
- `workissue-works-from-brief` (step): When work-issue has claimed an issue,
  it reads the issue from `flywheel.py brief`, or from the brief that started
  the session, and stops and releases the claim when `brief` refuses the
  issue.

## need owner-keeps-work-to-issue: Build only what the issue asks

When an implementer meets something the issue does not answer, the owner
wants it to stop and ask, or to file the idea and go on, so no behavior
enters from a guess.

Source: #648, and the method's `pause-on-discovery` and
`owner-admits-every-need`.

- `workissue-claims-first` (step): When work-issue starts, it claims the
  issue and reports the claim before any other work.
- `workissue-runs-check-before-pr` (step): When work-issue has the unit done,
  it runs the project's `check` and does not open a pull request while it
  fails.
- `workissue-pauses-on-gap` (step): When work-issue finds the issue silent or
  wrong on something the unit needs, it stops and asks, and files a candidate
  need instead when the issue is only improvable.

## need owner-watches-every-pull-request: Watch every agent's pull request

When an agent opens a pull request from a desktop session, the owner wants
that session woken on CI failures, conflicts and review comments, and
archived on close, without turning either on by hand.

Source: #305, #648, and the method's `checks-over-instructions`.

- `workissue-opens-pr-through-skill` (step): When work-issue has the unit
  committed and `check` passing, it opens the pull request through the
  installed skill whose description says it opens one, and with
  `gh pr create` when no skill does.
- `workissue-turns-on-pr-watch` (step): When work-issue has opened the pull
  request, it turns on Auto-fix and archive-on-close for it with the
  session's monitor tool, before reporting.

## need owner-starts-round-with-one-command: Start a round of issues with one command

When the owner wants a round of issues worked, they want to name the count,
the plan or the issues once and have sessions started, restarted after each
merge and reported on, so the loop runs without the owner typing each start.
They want to run more than one round at once, each on its own plan, count or
issues, without one round acting on another's pull requests.

Source: #649, #665, #688, #689, #701, and the method's `decompose-into-parallel-units`
and `match-capability-to-task`.

- `events-cmd-lists-claim-prs` (test): When `flywheel.py events` runs, it
  lists each open pull request from an `issue/N` branch with its CI and
  review state, and each merged since `--since`. It gives as `as_of` the
  newest merge it saw, so a look that passes it as `--since` does not name a
  merge twice.
- `events-cmd-scopes-to-round` (test): When `flywheel.py events` runs with
  `--tracking N`, it lists only the pull requests from sub-issues of #N, and
  with `--issue M`, given once per issue, only those from the issues it
  names. Its `as_of` still comes from every claim pull request's merge.
- `role-cmd-names-unset-fields` (test): When `flywheel.py role NAME` runs, it
  prints the model and effort `.flywheel/roles.json` gives the role. It exits
  1 naming the field when the file leaves either unset, and naming the role
  when the file does not have it.
- `run-refuses-unmapped-role` (step): When the roles file does not name a
  role `run` needs, `run` stops and names the field.
- `adopt-asks-roles-at-every-level` (step): When adopt runs at any target
  level, it asks the owner for each role's model and effort, since every
  round starts its sessions from them.
- `run-starts-one-session-per-issue` (step): When `run` has the issues from
  `queue`, it starts one session per issue with `brief N`, at the roles
  file's model and effort for the implementer. It stops rather than start
  one when either is above its own session's.
- `queue-cmd-checks-named-issues` (test): When `flywheel.py queue` is given
  issue numbers, as in `queue 12 14`, it reports each as an issue to start, a
  tracking issue, or the reason it cannot start: closed, lacking `approved`,
  held by another session's claim, or blocked by an open issue. It exits 1
  when any named issue cannot start, and refuses issue numbers given with
  `--tracking`.
- `run-starts-named-issues` (step): When the owner names issues, `run`
  starts one session for each issue that can start, tells the owner why each
  other one cannot, and stops once each has merged or stopped.
- `run-takes-issue-requests` (step): When the owner asks to fix, work or
  take an issue, or the next issue, the session runs that issue as a round,
  unless the owner asks for the work in this session.
- `run-reports-pull-request` (step): When a worker reports its pull request,
  `run` reports the pull request to the owner.
- `run-restarts-after-merge` (step): When `events` reports a merge from its
  round, `run` clears the claim and starts a worker on the next free issue.
- `run-acts-on-stalled-wait` (step): When `merge-check` names `wait` for a
  pull request from the round and its implementer is not working, `run`
  messages the implementer once for each head and set of reasons, and tells
  the owner which pull request waits and why when the implementer has
  already been messaged or has stopped.
- `run-closes-finished-plan` (step): When `queue --tracking N` says #N's plan
  is finished, `run` closes it with `plan close N`.
- `run-stops-on-empty-queue` (step): When `queue` offers nothing and no pull
  request from its round is open, `run` reports what merged and stops.

## need owner-keeps-gate-on-behavior-changes: Keep the owner's gate on changes to behavior

When a pull request would change what the product does, the owner wants to
approve it themselves, and when it would not, they want it merged once the
checks and the reviewer pass, so their attention goes where the risk is.

Source: #650, and the method's `autonomy-scales-with-risk` and
`owner-admits-every-need`.

- `mergecheck-cmd-holds-requirement-changes` (test): When
  `flywheel.py merge-check N` finds that pull request N adds, changes or
  removes a requirement, it reports hold with that reason. It reads that from
  N's `## Requirements` section, which names a requirement id or is missing.
- `mergecheck-cmd-holds-protected-paths` (test): When pull request N touches
  a path the merge policy protects, `merge-check` reports hold and names the
  path.
- `mergecheck-cmd-holds-outside-area` (test): When pull request N changes a
  file outside the paths the merge policy's `areas` gives its issue's area
  label, `merge-check` reports hold and names the file. It also holds when
  the issue has no area label that `areas` names, or `areas` is unset.
- `mergecheck-cmd-holds-open-findings` (test): When any of these holds,
  `merge-check` reports hold and names the thread's file and line, or the
  review:
  - the reviewer has not posted a review of pull request N's head.
  - a thread on N has no answer.
  - a thread stays unresolved after the reviewer's look at its answer.
- `mergecheck-cmd-flows-clean-pr` (test): When pull request N meets every
  flow condition in the policy, `merge-check` reports flow.
- `mergecheck-cmd-names-next-step` (test): When `merge-check` reports hold,
  it names the next step: `review` when the reviewer has yet to look at the
  head or at an answer, `wait` when a check, a conflict or a thread waits on
  the implementer, and `ask` when only the owner can settle it.
- `mergecheck-cmd-merges-on-flow` (test): When `merge-check N --merge` finds
  that N flows, it squashes N at the head it checked. When N holds, it merges
  nothing, and when the merge fails, it reports hold with GitHub's reason.
- `run-merges-what-flows` (step): When `merge-check` reports flow, `run`
  merges the pull request with a squash and clears the claim.
- `run-asks-owner-on-hold` (step): When `merge-check` reports hold, `run`
  asks the owner with its reasons and merges nothing until they answer.
- `run-reviews-each-pull-request` (step): When `merge-check` names `review`
  as the next step for a pull request from the round, `run` starts a reviewer
  session on it at the roles file's model and effort for the reviewer.
- `workissue-answers-each-thread` (step): When a review comment arrives on
  its pull request, work-issue answers each unresolved thread with a reply
  opening with `**Claude:**`, and leaves resolving it to the reviewer.

## need owner-gets-review-from-policy: Review every pull request from a written policy

When a pull request is reviewed by an agent, the owner wants the review made
from a written policy in a fresh context, so reviews are comparable and nits
cannot bury a real finding.

Source: #650, and the method's `review-against-written-policy` and
`separate-generation-from-verification`.

- `reviewpolicy-cmd-prints-policy` (test): When `flywheel.py review-policy`
  runs, it prints the project's review policy with its scale and cap, and
  exits 2 when the file is missing.
- `reviewbrief-cmd-prints-pull-request` (test): When
  `flywheel.py review-brief N` runs, it prints pull request N's head, its
  description, the requirement ids its `## Requirements` section names, its
  review threads, its diff, and the head the reviewer last reviewed. It
  exits 1 when N is not open.
- `reviewpost-cmd-checks-findings` (test): When
  `flywheel.py review-post N --findings <file>` reads findings that do any of
  these, it names each fault, posts nothing and exits 1:
  - name a head other than N's.
  - hold more P3 findings than the review policy's cap.
  - put a finding on a file N does not change, or at a level outside P0 to P3.
  - resolve a thread that is not an unresolved thread on N.
- `reviewpost-cmd-posts-comment-review` (test): When `review-post` accepts
  the findings, it resolves each thread they name. It then posts one review
  of the head that only comments, with each finding's comment opening with
  `**Claude:**` and its level.
- `reviewpr-reviews-against-policy` (step): When review-pr starts, it reads
  the policy with `review-policy` and the pull request with `review-brief`,
  and reviews the diff in each of the policy's passes, against the
  requirement ids the description lists.
- `reviewpr-posts-findings-under-cap` (step): When review-pr has its
  findings, it posts each as a review comment opening with `**Claude:**` and
  its level, and posts no more P3 findings than the cap.
- `reviewpr-never-approves` (step): When review-pr finishes, it has posted
  comments only, and no approval or request for changes.
- `reviewpr-rechecks-answered-threads` (step): When review-pr runs on a pull
  request it has reviewed before, it resolves each thread whose answer it
  accepts, and leaves the others unresolved.

## need owner-adopts-by-level: Adopt the method by level

When the owner brings a repo under the method, they want its gaps named by
principle id against the level they chose, filed one control per issue, and
the version recorded, so a later assessment shows only what changed.

Source: #651, the method's adoption.md, and the method's
`checks-over-instructions`.

- `assess-cmd-reports-gaps-by-id` (test): When `flywheel.py assess` runs in a
  project, it reports each level, and each control the level introduces by its
  principle ids, with its evidence found or missing. It exits 1 when a control
  that a level at or below the recorded level introduces is missing.
- `assess-cmd-checks-level-1-controls` (test): When `flywheel.py assess`
  runs, it holds level 1 only when the project holds all of these controls,
  each named by its key:
  - `agent-rules`, rules for agents in the file agents read every session,
    from the method's `trace-behavior-to-need` and
    `humans-decide-agents-record`.
  - `needs-spec`, a needs spec for each component opening with its
    out-of-scope list, from the method's `list-out-of-scope-first` and
    `source-needs-outside-code`.
  - `approved-ticket`, the ticket as the home of each change's intent, which
    the owner approves, from the method's `owner-admits-every-need` and
    `one-home-per-artifact`.
  - `core-gates`, the `build`, `test` and `check` commands, from the method's
    `one-command-per-gate`.
  - `tests-first`, tests written first and named for behavior, from the
    method's `write-behavior-tests-first`.
- `assess-cmd-checks-level-2-controls` (test): When `flywheel.py assess`
  runs, it holds level 2 only when the project holds level 1 and all of these
  controls, each named by its key:
  - `trace-checks`, traceability checks in CI, from the method's
    `checks-over-instructions` and `no-merge-without-alignment`.
  - `verify-gate`, the `verify` command run by CI on every pull request, from
    the method's `one-command-per-gate`.
  - `unweakened-checks`, new tests that must fail on the base and checks that
    agents cannot loosen, from the method's `agents-never-weaken-checks`.
    It is held only when `.flywheel/gates.json` gives the test commands
    under `tests`, the `verify` command or a file it names runs
    `fails-on-base`, and a workflow cites the principle.
  - `approval-guard`, approval kept out of agent reach by a hook or a CI
    check, from the method's `checks-over-instructions` and
    `owner-admits-every-need`.
  - `plan-first`, a plan approved before code, from the method's
    `approve-plan-before-code`.
  - `review-policy`, a written review policy and a fresh-context reviewer,
    from the method's `review-against-written-policy` and
    `separate-generation-from-verification`.
- `assess-cmd-checks-level-3-controls` (test): When `flywheel.py assess`
  runs, it holds level 3 only when the project holds level 2 and all of these
  controls, each named by its key:
  - `instruction-evals`, evals for the agent's instructions rerun on every
    change to them, from the method's `eval-instructions-on-change`.
  - `role-tiers`, agents assigned by role and tier, each tier with a model and
    a default effort, from the method's `match-capability-to-task`.
  - `merge-policy`, a written merge policy, from the method's
    `autonomy-scales-with-risk`.
  - `scheduled-audit`, a scheduled audit, from the method's
    `audit-on-schedule`.
  - `loop-measures`, measures for each stage with control bands, from the
    method's `measure-the-loop` and `scripts-detect-models-diagnose`.
  - `measured-trials`, improvement trials one change at a time against a
    baseline, from the method's `improve-by-measured-trial`.
  - `mistakes-to-checks`, repeated mistakes that climb to checks, from the
    method's `repeat-mistakes-become-checks`.
- `record-cmd-writes-version-and-controls` (test): When
  `flywheel.py record --level N` runs, it writes the plugin version, level N
  and, under each level, whether each control the level introduces is held,
  to `.flywheel/adoption.json`. `assess` then names each control whose state
  changed since, and each control the record lacks under its level.
- `adopt-never-invents-owner-fields` (step): When adopt needs a need, a
  constraint, the target level, a policy's terms, a role's model or a gate's
  command, it asks the owner and writes nothing until they answer.
- `adopt-writes-agent-rules` (step): When adopt has the target level, it
  writes the plugin's rules for agents up to that level into the project's
  `CLAUDE.md`, with a rule for every principle that each level's controls
  name, each citing the principle it serves, and leaves the project's own
  rules as they are.
- `labels-cmd-names-missing-labels` (test): When `flywheel.py labels` runs,
  it names each label the loop and file-issue need that the repository
  lacks, and exits 1 when one is missing. With `--create`, it creates each
  one.
- `adopt-creates-missing-labels` (step): When adopt has gaps to file, it
  shows the owner the missing labels and creates them once the owner agrees,
  before it hands the gaps to file-issue.
- `adopt-files-gaps-as-plan` (step): When `record` names a control missing at
  or below the target level, adopt files the gaps as one plan through
  file-issue, one control per issue, in the order of the method's tables.
- `hook-ships-with-plugin` (test): When the plugin is installed, its
  `hooks/hooks.json` runs the approval guard on every Bash call.

## need owner-checks-new-tests-fail: Check that each new test fails on the base

When the owner adopts the method at level 2, they want the plugin to fail a
pull request whose new test passes on the code before its change, in a
project of any language, so the control is a check rather than a comment.

Source: #682, and the method's `agents-never-weaken-checks`.

- `failsonbase-cmd-fails-test-passing-on-base` (test): When a test that the
  branch adds since its merge base with `--base` passes in the base tree,
  `flywheel.py fails-on-base` fails and names it. The base tree is the merge
  base's code with the branch's test paths copied over it. A test whose run
  exits nonzero there does not pass.
- `failsonbase-cmd-reads-gates-test-commands` (test): When `fails-on-base`
  runs, it lists the tests at the branch and at the merge base with the
  `list` command under `tests` in `.flywheel/gates.json`, runs each new test
  alone with the `run` command, which holds `{id}` where the test's id goes,
  and copies the `paths` from the branch over the base tree. It exits 2 and
  names each of the three that is missing.
- `failsonbase-cmd-refuses-failing-branch-run` (test): When a new test fails
  at the branch, `fails-on-base` exits 2 and names the test and the `run`
  command.
- `failsonbase-cmd-excuses-listed-test` (test): When
  `.flywheel/passes-on-base.json` maps a passing new test's id to a reason,
  `fails-on-base` passes the test and warns with its id and the reason. An
  empty reason fails.
- `configinit-cmd-fills-pytest-test-commands` (test): When
  `flywheel.py config init` runs in a project that configures pytest in
  `pytest.ini`, in `pyproject.toml` under `[tool.pytest.ini_options]` or in
  `setup.cfg` under `[tool:pytest]`, it writes the pytest `list` and `run`
  commands under `tests` in `.flywheel/gates.json`, and `paths` from its
  `testpaths` and the config file. For any other runner, or without
  `testpaths`, it leaves each field it cannot fill unset, for the owner. It
  leaves the file's other keys as they are, and leaves a `tests` object that
  exists as it is, names the file and exits 1.

## need owner-measures-loop: Measure the loop before changing a role

When the owner considers a change to a role's model or effort, they want the
loop's cost, first-pass CI rate, review findings and lead time over a period,
so the change is a trial against a baseline and not a guess.

Source: #652, and the method's `measure-the-loop` and
`improve-by-measured-trial`. specs/repo.md holds the requirement this repo's
scheduled workflow meets under this need.

- `measure-cmd-reports-starting-measures` (test): When
  `flywheel.py measure --since <when>` runs, where `<when>` is a date such as
  `2026-10-12` or a UTC time such as `2026-10-12T06:03:00Z`, it reports spend,
  first-pass CI, reviewer findings by level and lead time for each pull
  request merged at or after it, and a summary, and says which it could not
  compute and why.

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
- `configinit-cmd-names-owner-fields` (test): When `config init` writes a file
  with a field only the owner can fill, it names each such field in its
  result.

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
  runs, it prints the issue's title and body as they stood when `approved`
  was last added, the owner's comments since, the role, and the gate commands
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

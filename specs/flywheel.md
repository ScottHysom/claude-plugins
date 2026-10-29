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

Source: #643, and the playbook's `match-capability-to-task` and
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

## need owner-keeps-own-labels: Keep the repository's own labels for the loop's roles

When the owner adopts the loop in a repository that already has labels that
approve an issue, group a plan or mark work on the whole repository, they
want the loop to act on those labels, so the repository does not carry two
labels for one role. When the repository already uses the loop's claim label
for its own purpose, they want to give the claim a label of its own.

Source: the owner's review comment on #693, and #695 with the owner's
decisions on it.

- `labelsfile-maps-roles` (test): When `.flywheel/labels.json` gives a label
  under `roles` for one of the loop's roles, every flywheel command that
  reads or writes that role's label uses the label it gives. The roles, each
  with the label used when the file leaves it out or is missing:
  - `approval`, the **approval label**, which the owner adds to approve an
    issue: `approved`.
  - `plan`, the **plan label**, which marks the issue that groups a plan's
    issues: `plan`.
  - `claim`, the **claim label**, which `claim` adds to the issue it holds:
    `claimed`.
- `labelsfile-refuses-bad-map` (test): When `.flywheel/labels.json` gives
  any of these, a command that reads it exits 2 and names the fault:
  - a role outside the three.
  - a label that is empty.
  - one label for two roles.
  - a `kinds` that is not an object holding at least one label.
  - a kind whose description is not text.
- `labels-cmd-sets-role` (test): When `flywheel.py labels --set ROLE=NAME`
  runs, it writes NAME as ROLE's label into `.flywheel/labels.json` and
  leaves the file's other roles as they are, before it names the missing
  labels. It refuses a role outside the three, and writes nothing then.
- `labels-cmd-flags-taken-claim-label` (test): When `flywheel.py labels` finds
  the claim label in the repository with a description other than the one
  flywheel gives it, it names the label as taken and exits 1, and the remedy
  says to give the claim another label with `--set claim=NAME`.
- `guard-reads-approval-label` (test): When the approval guard checks a Bash
  command, it blocks the approval label that `.flywheel/labels.json` gives in
  the session's project. When it cannot read that file, it blocks every
  command that adds a label.
- `adopt-asks-role-labels` (step): When adopt runs, it asks the owner which
  label the repository uses for each role, and for the claim a label that
  nothing else in the repository uses, and sets each answer with
  `labels --set` before it names the missing labels.

## need owner-sets-issue-rules: File issues under the project's own labels and headings

When the owner adopts the loop, they want file-issue to file under the
project's own kind labels and issue headings, so the loop fits
the repository rather than the repository fitting the loop. Where the project
sets none, they want GitHub's defaults, such as its `documentation` label.

Source: #692 and the owner's comment on it, with the owner's decisions on the
plan posted there.

- `labelsfile-sets-kinds` (test): When `.flywheel/labels.json` gives
  `kinds`, an object that maps a label to its description, `plan report`
  takes a draft's kind label from `kinds`. Without `kinds`, the kinds are
  GitHub's `bug`, `enhancement` and `documentation`.
- `adopt-asks-issue-rules` (step): When adopt runs, it asks the owner for
  the kind labels and the issue headings, offering the defaults first. It
  sets a kind answer that differs with `labels --kind`, and writes headings
  that differ to
  `.flywheel/issue-template.md`, before it names the missing labels.
- `issuetemplate-sets-headings` (test): When `.flywheel/issue-template.md`
  exists, each `##` heading in it is a heading every draft's body holds, and
  the text under a heading is the guidance for that section. Without the
  file, the headings are `What's wrong`, `Evidence`, `Done when` and
  `Requirements`. A template without a `##` heading stops a command that
  reads it with exit 2.

## need owner-sets-pr-shape: Open pull requests in the project's own shape

When the owner adopts the loop, they want each pull request's description in
the project's own shape, with merge-check and review-brief reading the
requirement ids from the section the project names. Where the project sets no
shape, they want this repository's: a scenario with its before and after, the
change, the requirements and the test plan.

Source: #716, with the owner's approval of the plan posted there.

- `prtemplate-sets-shape` (test): When `.flywheel/pr-template.md` exists,
  each `##` heading in it is a section every description holds, in its
  order, each `###` heading under one is a subsection that section holds,
  and the text under a heading is the guidance for it. The section with
  `<!-- requirement-ids -->` under its heading is the one that names the
  requirement ids. Without the file, the sections are `Scenario`, with the
  subsections `Before` and `After`, then `Change`, `Requirements` (the
  marked one) and `Test plan`. A template that has no `##` heading, marks
  no section or more than one, or puts a `###` heading before every `##`
  stops a command that reads it with exit 2.
- `prdraft-cmd-makes-own-file` (test): When `flywheel.py pr draft` runs, it
  makes an empty file that no other run is given, and prints its path with
  each section, subsection and guidance of the shape to draft from, each
  prose rules file the pull request template names, and the skill the
  template names to run their patterns.
- `prcheck-cmd-requires-shape` (test): When
  `flywheel.py pr check --body-file FILE` reads a description that does any
  of these, it names each fault and exits 1:
  - opens with a heading other than the shape's first section.
  - lacks a section of the shape, or puts two of them out of order.
  - leaves a section empty.
  - lacks a subsection of the shape under its section, leaves one empty, or
    puts two of them out of order.

  A heading inside a code fence or an HTML comment is text.
- `prcheck-cmd-refuses-split-lines` (test): When `pr check` finds a
  paragraph or a list item that continues onto a second line, outside a
  code fence or an HTML comment, it names the line and exits 1.
- `prcheck-cmd-requires-closes` (test): When `pr check` finds no line that
  closes an issue, such as `Closes #N`, outside a code fence or an HTML
  comment, it says so and exits 1.
- `propen-cmd-refuses-failing-draft` (test): When
  `flywheel.py pr open --title TITLE --body-file FILE` reads a description
  that `pr check` would fail, it names each fault, pushes nothing, opens
  nothing and exits 1.
- `propen-cmd-opens-from-file` (test): When `pr open` reads a description
  that passes, it pushes the branch and opens a pull request with that
  title, with the file as its description, and prints its url.
- `prskill-drafts-from-template` (step): When the open-pr skill runs, it
  drafts the description in the shape `pr draft` gives, into the file
  `pr draft` made.
- `prskill-checks-draft` (step): When open-pr has a draft, it checks it with
  `pr check`, and fixes each fault before anyone reads it.
- `prskill-gives-draft-to-cold-reader` (step): When the draft passes
  `pr check`, open-pr gives it to a subagent that has none of the session's
  context, which names each term the draft leaves undefined, and revises
  the draft until a subagent names none that blocks the reading.
- `prskill-opens-through-script` (step): When the cold reader names no
  blocking term, and the prose read leaves no sentence to rewrite or is
  skipped, open-pr opens the pull request with `pr open`.
- `adopt-asks-pr-shape` (step): When adopt asks the owner for the issue
  rules, it asks in the same question for the shape of a pull request's
  description, offering the default first, and writes an answer that
  differs to `.flywheel/pr-template.md`.
- `agentrules-names-requirements-section` (step): When adopt writes the
  rules for agents, they tell the agent to name each requirement id the
  pull request adds, changes or removes in the section the pull request
  template marks, and to open the pull request through the open-pr skill.

## need owner-reads-description-in-project-style: Read each description in the project's prose style

When the owner adopts the loop in a project that keeps prose rules, they want
open-pr to hold each description to those rules before the owner reads it, as
this repository's own open-pr did.

Source: commit db742c2, and the owner's decision of 2026-10-22 to make
open-pr's reading fixes in flywheel's skill, so that they survive #717. The
owner chose in chat on #739 that the pull request template names the files,
and on #740 that open-pr hands the draft to a skill the template names, set
at adoption, to run the rules' patterns. The owner chose in chat on #756 that
the same skill reads the draft against every rule, in place of a reader that
flywheel ships.

- `prtemplate-names-prose-rules` (test): When `.flywheel/pr-template.md`
  holds a line `<!-- prose-rules: PATH -->` outside a code fence, PATH names
  a file of the project's prose rules, from the project root. A template
  names several files with one mark each. A mark that names a file that does
  not exist stops a command that reads the template with exit 2.
- `prtemplate-names-prose-check` (test): When `.flywheel/pr-template.md`
  holds a line `<!-- prose-check: SKILL -->` outside a code fence, SKILL
  names the skill that checks a draft against the prose rules. A second
  such mark, an empty one, or one in a template without a `prose-rules` mark
  stops a command that reads the template with exit 2.
- `adopt-asks-prose-rules` (step): When adopt sets the pull request shape,
  it asks the owner for the project's prose rules files and the skill that
  checks a file against the prose rules, and writes a mark for each answer
  into `.flywheel/pr-template.md`. It tells the owner that each rules file
  has to follow the format of the skill named beside it. When adopt has written the template, it runs
  `pr draft` before it finishes, and fixes the template with the owner
  until `pr draft` reads it.
- `prskill-gives-draft-to-style-reader` (step): When the draft passes
  `pr check`, and again after each revision, open-pr hands the draft to the
  skill that `.flywheel/pr-template.md` names, with the Skill tool, at the
  same time as it gives the draft to the cold reader. The skill runs every
  pattern the project's prose rules carry and reads the draft against every
  rule. The hand-off tells the skill that the cold reader checks undefined
  terms. open-pr rewrites each sentence that a match or a breach falls in,
  and takes a term to explain only from the cold reader. After a revision,
  open-pr also passes the skill each line the revision changed. When the
  template does not name a skill, or names one that is not installed,
  open-pr skips the prose check, and tells the owner when the template
  names prose rules files.

## need contributor-reads-playbook-beside-plugin: Read the playbook beside the plugin

When a contributor or an adopting owner reads a principle id in a spec, a
template or a skill, they want to open the document that defines it from the
same install, so the id is a definition and not a pointer to another repo.

Source: #644, and the playbook's `one-home-per-artifact`.

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
  names the lowest-numbered open issue carrying the approval label that is
  unheld by any `issue/N` branch and unblocked by any open issue. It exits 0
  even when every such issue is held or blocked. It does not offer a
  **plan issue** (an issue carrying the plan label, which groups a plan's
  issues as its sub-issues), or a sub-issue of an open plan issue
  carrying the approval label.
- `queue-cmd-offers-up-to-count` (test): When `flywheel.py queue --count N`
  runs, it offers up to N free approved issues that no open issue blocks,
  oldest first, and says when fewer are free. With `--plan`, it offers up
  to N of the plan's sub-issues in the plan's order, and stops with a warning
  before a sub-issue that lacks the approval label.
- `claim-cmd-picks-one-winner` (test): When two agents claim the same
  issue at once, `flywheel.py claim` lets exactly one create `issue/N`, and
  the other exits 1, names the holder and writes nothing.
- `claim-cmd-switches-to-issue-branch` (test): When `flywheel.py claim N`
  wins, it switches the clone to `issue/N`, and warns when the switch fails.
- `claim-cmd-warns-of-changes-already-in-worktree` (test): When
  `flywheel.py claim N` wins in a worktree that already holds untracked or
  modified files, it names each one in a warning and still claims.
- `claim-cmd-stops-when-nobody-wins` (test): When the push fails and
  `issue/N` does not exist, `flywheel.py claim` exits 2 without writing to
  the issue.
- `workissue-relays-changes-already-in-worktree` (step): When `claim`
  warns of changes already in the worktree, work-issue relays the warning to
  the owner before it starts the work, so the owner decides what happens to
  those files.
- `next-cmd-moves-past-lost-claim` (test): When `flywheel.py claim --next`
  loses the claim on the issue `queue` offered, it claims the next free
  issue, until it wins or none is free, and then exits 1 saying why. With
  `--plan N`, it takes #N's next free sub-issue, and stops where
  `queue --plan N` stops. When the owner named the issue, as in
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

When the owner has grouped one plan's issues under a plan issue and
approved the plan, the owner wants to tell an agent to take the plan's next
issue, so agents work the plan in its listed order without picking issues
from outside it.

Source: the owner's request on 2026-10-05, recorded in #350.

- `next-cmd-follows-plan-issue` (test): When `flywheel.py queue
  --plan N` runs, it offers the first sub-issue in #N's listed order that
  is open, unheld and unblocked. It exits 1 when that sub-issue lacks the
  approval label, or when #N does not carry both the plan label and the
  approval label, or is closed. A plan issue that is closed while all
  its sub-issues are closed is the exception: the plan is finished, as
  `next-cmd-reports-finished-plan` says.
- `next-cmd-names-plan-issue` (test): When an open plan issue
  carrying the approval label takes its place in the queue, at the lowest number among itself
  and its open sub-issues, before the issue `flywheel.py queue` would offer,
  `queue` names the plan issue and the command to follow it, and exits 0.
- `next-cmd-reports-finished-plan` (test): When every sub-issue of #N is
  closed, `flywheel.py queue --plan N` says the plan is finished and exits 0.
  It names the command that closes #N when #N is open. When #N is closed
  already, it marks `data.plan` with `closed` true and names no command. An open sub-issue keeps the plan
  unfinished even when a claim holds it, and so does a plan issue without
  sub-issues.
- `planclose-cmd-closes-finished-plan` (test): When `flywheel.py plan close N`
  runs on an open issue carrying both the plan label and the approval label
  whose sub-issues are all closed, it closes #N with a comment naming them. It exits
  1 without writing to #N when any of these holds:
  - any sub-issue of #N is open.
  - #N lacks sub-issues.
  - #N is closed, or lacks either label.

## need owner-sees-finished-plans-closed: See a finished plan closed

When the last issue of a plan closes, the owner wants the plan's tracking
issue closed with it, so an open tracking issue always means work remains.

Source: the owner's request on 2026-10-21, recorded in #732, with #729 as
the example.

- `planclose-cmd-closes-parent-plan` (test): When `flywheel.py plan close
  --sub-issue M` runs, it finds the issue that holds #M as a sub-issue, and
  closes it under the checks `plan close N` makes, with the same comment. It
  exits 0 without writing to GitHub when any of these holds:
  - #M is not a sub-issue of any issue.
  - the parent is closed, or lacks the plan label or the approval label.
  - a sub-issue of the parent is open.

## need owner-approves-plan-once: Approve a plan's issues once

When a plan yields several issues, the owner wants to approve the whole plan
once, and have its issues filed, linked and grouped under a plan issue
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
  - lacks a heading the project's issue template gives.
  - does not carry exactly one kind label.
  - carries the approval label or the plan label.
  - carries a label the repository does not have.
- `planreport-cmd-checks-plan-links` (test): When a key repeats, a `{KEY}` or a
  `blocked_by` key does not name an issue in the plan, a body names an issue
  filed after it, a blocker outside the plan is anything but an open issue, or
  the links form a cycle, `plan report` refuses the plan and names each fault.
- `planreport-cmd-accepts-one-issue` (test): When `flywheel.py plan report`
  reads a plan of one issue with no plan issue, it checks and reports
  that issue alone, and `plan file` files it without a plan issue. It
  refuses a plan of several issues without a plan issue.
- `planreport-cmd-orders-by-links` (test): When `plan report` accepts a plan,
  it puts each issue after the issues that block it, with ties in the plan's
  listed order. It shows each issue whole, and the plan issue's body as
  it will be filed, with an Order section written from the links.
- `planfile-cmd-requires-token` (test): When `flywheel.py plan file --drafts
  <file> --token <token>` is given a token that does not match the plan, the
  repository and its labels as they are now, or the plan now fails one of the
  checks `plan report` made, it exits 1 without filing anything.
- `planfile-cmd-files-in-order` (test): When `plan file` runs with a current
  token, it files the issues in the report's order, each `{KEY}` replaced by
  the number filed, and adds each "blocked by" link. It then files the
  plan issue carrying the plan label, and adds the sub-issues in that
  order.
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
- `plandraft-cmd-gives-issue-rules` (test): When `flywheel.py plan draft
  --json` runs, its `data` also gives the kinds, each with its
  description, the role labels, and each heading with its guidance, as
  `plan report` checks them.
- `fileissue-follows-issue-rules` (step): When the file-issue skill drafts
  an issue, it takes the issue's headings and kind label from what `plan
  draft` gives, writes under each heading what its guidance asks for, and
  chooses the kind by its description. It adds any other label the
  project's own instructions ask for.
- `fileissue-drafts-in-own-file` (step): When the file-issue skill drafts a
  plan, it writes the plan to the file `plan draft` made for that run, and
  every later step of the run reads that file, so a plan another session
  drafts does not replace it.

## need owner-sees-held-issues: See from the issue list which issues are held

When an agent or the owner looks at the issue list, they want a claimed issue
to show as claimed, and a label that disagrees with its branch to be reported,
so a reader never takes a stale label for a claim.

Source: README.md, under "Claiming an issue", and #33.

- `claim-cmd-adds-claim-label` (test): When `flywheel.py claim` wins,
  it adds the claim label and a claim comment, and if either fails, it warns
  and still exits 0.
- `stale-cmd-reports-claims-left-behind` (test): When any of these holds, `flywheel.py stale` fails and names the remedy:
  - a label has no branch.
  - a closed issue keeps its label.
  - a closed issue keeps its branch.
  - an open issue has its branch and lacks the label.

## need owner-frees-abandoned-claims: Free an abandoned claim, keeping its work unless the owner drops it

When an agent stops without opening a pull request, the owner wants its claim
freed for someone else, so the issue does not stay held. The owner wants every
commit on the claim branch kept through the freeing, unless the owner has said
in chat to drop them, so that dropping them needs no step run by hand.

Source: README.md, under "Claiming an issue", CLAUDE.md, under "Issues", and
#264.

- `release-cmd-frees-unused-claim` (test): When `flywheel.py release N`
  finds `issue/N` with no commits off main, or only the claim label,
  it deletes the branch, removes the label and comments.
- `release-cmd-keeps-work` (test): When `issue/N` has commits off main, or
  changed after `release` checked it, `flywheel.py release` exits 1 and
  deletes nothing. Without `--drop-work`, its error names `--drop-work` as
  the way to drop the commits once the owner has said to.
- `release-cmd-drops-work-on-request` (test): When `flywheel.py release N
  --drop-work` finds `issue/N` with commits off main, it deletes the branch
  only at the tip it checked, removes the claim label, and comments with
  that tip's sha, so the work can be recovered.
- `workissue-drops-work-on-owner-word` (step): When work-issue gives up a
  claim whose `issue/N` holds commits, it passes `--drop-work` only after the
  owner has said in chat to drop them.
- `release-cmd-requires-held-claim` (test): When `flywheel.py release N`
  finds neither `issue/N` nor the claim label, it exits 1 without
  commenting, so only an issue that was held can read as released.

## need owner-closes-moot-issue: Close an issue that has no work left

When an approved issue turns out to need no change, the owner wants an agent
to close it as not planned and free its claim on the owner's word, so that the
owner does not run commands by hand.

Source: #264.

- `close-cmd-closes-not-planned` (test): When `flywheel.py close N --reason
  TEXT` finds #N open, it frees any claim on #N as `release` would, taking
  `--drop-work` the same way, then closes #N as not planned with a comment
  that opens with the agent's mark and carries the reason. When #N is closed
  already, or `release` would refuse, it exits 1 and closes nothing.
- `workissue-closes-on-owner-word` (step): When work-issue finds that its
  issue needs no change, it asks the owner, and runs `flywheel.py close` only
  after the owner has said in chat to close it.

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
- `clear-cmd-keeps-unmerged-work` (test): `flywheel.py clear` exits 1, says
  what to do next and deletes nothing under any of these conditions:
  - #N is open.
  - The local `issue/N` is missing and no pull request from it has merged.
  - The local `issue/N` holds a commit that every merged pull request from it
    lacks and a change `origin/main` lacks.
- `clear-cmd-reports-cleared-claim` (test): When #N is closed, the local
  `issue/N` is missing and a pull request from `issue/N` has merged,
  `flywheel.py clear N` exits 0 and says the claim is already cleared.
- `workissue-clears-merged-claim` (step): When work-issue's scheduled check
  finds its pull request merged, it runs `flywheel.py clear` for its issue,
  inside a round or outside one.
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

Source: #645, and the playbook's `humans-decide-agents-record` and
`owner-admits-every-need`.

- `brief-cmd-prints-issue-as-approved` (test): When `flywheel.py brief N`
  runs, it prints the skill that works the issue, the issue's title and body
  as they stood when the approval label was last added, the owner's comments since, the role, and the gate commands
  from `.flywheel/gates.json`, and warns when `.flywheel/` does not give the
  role's tier or the gate commands. It exits 1 when the body changed after
  approval, or the issue lacks the approval label.
- `workissue-works-from-brief` (step): When work-issue has claimed an issue,
  it reads the issue from `flywheel.py brief`, or from the brief that started
  the session, and stops and releases the claim when `brief` refuses the
  issue.

## need owner-keeps-work-to-issue: Build only what the issue asks

When an implementer meets something the issue does not answer, the owner
wants it to stop and ask, or to file the idea and go on, so no behavior
enters from a guess.

Source: #648, and the playbook's `pause-on-discovery` and
`owner-admits-every-need`.

- `workissue-claims-first` (step): When work-issue starts, it claims the
  issue and reports the claim before any other work.
- `workissue-runs-check-before-pr` (step): When work-issue has the unit done,
  it runs the project's `check`, and its `verify` when the gates name one,
  and does not open a pull request while either fails.
- `workissue-pauses-on-gap` (step): When work-issue finds the issue silent or
  wrong on something the unit needs, it stops and asks, and files a candidate
  need instead when the issue is only improvable.

## need owner-watches-every-pull-request: Watch every agent's pull request

When an agent opens a pull request from a desktop session, the owner wants
that session woken on CI failures, conflicts and review comments, and
archived once it has cleaned up after the pull request closes, without
turning either on by hand.

Source: #305, #648, and the playbook's `checks-over-instructions`.

- `workissue-opens-pr-through-skill` (step): When work-issue has the unit
  committed and `check` and `verify` passing, it opens the pull request through the
  project's own skill for opening one, and through the plugin's open-pr
  skill when the project has none.
- `workissue-turns-on-pr-watch` (step): When work-issue has opened the pull
  request, it turns on Auto-fix for it, and leaves archive-on-close
  off, with the session's monitor tool, before reporting. When the
  session has no monitor tool or the app refuses, its report and its
  wrap-up recap open with "Auto-fix is off" and the pull request's url, and
  a refusal's reason follows.
- `workissue-rechecks-for-comments` (step): When work-issue has turned on the
  watch, it schedules a recurring check of its pull request's unresolved
  review threads with `flywheel.py unanswered`, since the app does not wake the
  session on comments from the account the session posts as. It answers a
  waiting thread as `workissue-answers-each-thread` says, and ends the check
  once the pull request is no longer open. A run that found nothing ends with
  a reply whose first words say no review thread is waiting, and that names CI
  only when it reports on CI. A run that acted says what it did.
- `workissue-archives-after-clear` (step): When work-issue's pull request has
  merged, the session archives itself with the app's `archive_session` tool
  once `flywheel.py clear` has succeeded, or once it has discarded only its
  own temporary files and `clear` then succeeded. When `clear` finds changes
  the session did not make or cannot account for, the session names them to
  the owner and stays unarchived. When the pull request closes unmerged, the
  session tells the owner and stays unarchived. When the session cannot
  archive itself, the dispatcher of a round archives it once the
  implementer reports, and outside a round the session tells the owner it is
  ready to archive.
- `unanswered-cmd-lists-waiting-threads` (test): When `flywheel.py unanswered N`
  runs, it lists each unresolved review thread on pull request N whose last
  comment does not open with `**Claude:**`, or that has a single comment, with
  the pull request's state. It lists none for a thread that is resolved or
  whose last comment is an answer.

## need owner-starts-round-with-one-command: Start a round of issues with one command

When the owner wants a round of issues worked, they want to name the count,
the plan or the issues once and have sessions started, restarted after each
merge and reported on, so the loop runs without the owner typing each start.
They want to run more than one round at once, each on its own plan, count or
issues, without one round acting on another's pull requests.

Source: #649, #665, #688, #689, #701, #703, and the playbook's `decompose-into-parallel-units`
and `match-capability-to-task`.

- `events-cmd-lists-claim-prs` (test): When `flywheel.py events` runs, it
  lists each open pull request from an `issue/N` branch with its CI and
  review state. Each row also carries the head, verdict, next step, reasons
  and `only_running_check` that `merge-check` gives it, or the error that
  kept it from assessing the pull request, as a hold for the owner. It lists
  each merge since `--since`, and gives as `as_of` the newest merge it saw,
  so a look that passes it as `--since` does not name a merge twice.
- `events-cmd-scopes-to-round` (test): When `flywheel.py events` runs with
  `--plan N`, it lists only the pull requests from sub-issues of #N, and
  with `--issue M`, given once per issue, only those from the issues it
  names. Its `as_of` still comes from every claim pull request's merge.
- `checkrole-cmd-names-unset-fields` (test): When `flywheel.py check-role NAME`
  runs, it prints the model and effort `.flywheel/roles.json` gives the role.
  It exits 1 naming the field when the file leaves either unset, and naming
  the role when the file does not have it.
- `checkrole-cmd-exits-1-above-session` (test): When `flywheel.py check-role
  NAME` runs with `--model` and `--effort`, a session's own, it exits 1 when
  the role's model or effort is above the session's, and says to run the
  skill from a session at least that strong. It matches a model by family, so
  `opus` matches `claude-opus-5-5`. It exits 1 when it cannot rank either
  value, and refuses one of the two options given alone.
- `run-checks-dispatcher-role` (step): When `run` starts, it reads its own
  model and effort with the app's `get_session` tool and checks the
  `dispatcher` role against them with `check-role`, before it starts
  anything. It stops when the role is above its own session.
- `run-checks-started-session` (step): After each `start_session` call,
  `run` reads the new session with `get_session` and checks it against its
  role with `check-role`. When `check-role` exits 1, the session runs below
  its role's model or effort, and `run` tells the owner and starts nothing
  else on that work until the owner answers.
- `run-refuses-unmapped-role` (step): When the roles file does not name a
  role `run` needs, `run` stops and names the field.
- `adopt-asks-roles-at-every-level` (step): When adopt runs at any target
  level, it asks the owner for each role's model and effort, since every
  round starts its sessions from them.
- `run-starts-one-session-per-issue` (step): When `run` has the issues from
  `queue`, it starts one session per issue with `brief N`, at the roles
  file's model and effort for the implementer. It stops rather than start
  one when either is above its own session's, as `check-role` finds.
- `queue-cmd-starts-at-issue` (test): When `flywheel.py queue --count N
  --from M` runs, it offers up to N free approved issues as `queue --count N`
  does, leaving out every issue and plan issue that comes before #M in the
  queue's order. The queue's order is by number, with a plan issue at its
  lowest open number. It warns, naming the reason, when #M cannot be offered
  and no claim holds it, and refuses `--from` given with issue numbers or
  `--plan`.
- `queue-cmd-checks-named-issues` (test): When `flywheel.py queue` is given
  issue numbers, as in `queue 12 14`, it reports each as an issue to start, a
  plan issue, or the reason it cannot start: closed, lacking the approval label,
  held by another session's claim, or blocked by an open issue. It exits 1
  when any named issue cannot start, and refuses issue numbers given with
  `--plan`.
- `run-starts-named-issues` (step): When the owner names issues, `run`
  starts one session for each issue that can start, tells the owner why each
  other one cannot, and stops once each has merged or stopped.
- `run-takes-issue-requests` (step): When the owner asks to fix, work or
  take an issue, or the next issue, the session runs that issue as a round,
  unless the owner asks for the work in this session.
- `run-looks-on-schedule` (step): While a pull request from its round is
  open, `run` looks at the round on a schedule, so a check that finishes is
  acted on without a session ending a turn.
- `run-reports-pull-request` (step): When a worker reports its pull request,
  `run` reports the pull request to the owner.
- `run-relays-refused-auto-fix` (step): When a worker reports that Auto-fix is
  off for its pull request, `run` tells the owner the pull request's url and
  the app's reason, once.
- `run-restarts-after-merge` (step): When `events` reports a merge from its
  round, `run` clears the claim (or accepts a claim its implementer already
  cleared) and starts a worker on the next free issue.
- `run-archives-reviewer` (step): When a pull request from the round merges
  or closes, `run` archives each reviewer session it started on it.
- `run-acts-on-stalled-wait` (step): When `merge-check` names `wait` for a
  pull request from the round and its implementer is not working, `run`
  messages the implementer once for each head and set of reasons, and tells
  the owner which pull request waits and why when the implementer has
  already been messaged or has stopped.
- `run-closes-finished-plan` (step): When `queue --plan N` says #N's plan
  is finished, `run` closes it with `plan close N`. When `data.plan`
  marks #N closed already, `run` does not close it a second time.
- `run-stops-on-empty-queue` (step): When `queue` offers nothing and no pull
  request from its round is open, `run` reports what merged and stops.

## need owner-keeps-gate-on-behavior-changes: Keep the owner's gate on changes to behavior

When a pull request would change what the product does, the owner wants to
approve it themselves, and when it would not, they want it merged once the
checks and the reviewer pass, so their attention goes where the risk is.

Source: #650, and the playbook's `autonomy-scales-with-risk` and
`owner-admits-every-need`.

- `mergecheck-cmd-holds-requirement-changes` (test): When
  `flywheel.py merge-check N` finds that pull request N adds, changes or
  removes a requirement, it reports hold with that reason. It reads that from
  the section of N's description that the pull request template marks, which
  names a requirement id or is missing.
- `mergecheck-cmd-holds-protected-paths` (test): When pull request N touches
  a path the merge policy protects, `merge-check` reports hold and names the
  path.
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
  the implementer, and `ask` when only the owner can settle it. It also
  reports `only_running_check`, true when a running check is the only reason
  that waits on the implementer.
- `mergecheck-cmd-merges-on-flow` (test): When `merge-check N --merge` finds
  that N flows, it squashes N at the head it checked. When N holds, it merges
  nothing, and when the merge fails, it reports hold with GitHub's reason.
- `run-merges-what-flows` (step): When `merge-check` reports flow, `run`
  merges the pull request with a squash and clears the claim.
- `run-asks-owner-on-hold` (step): When `merge-check` reports hold, `run`
  asks the owner with its reasons and merges nothing until they answer.
- `run-reviews-each-pull-request` (step): When `merge-check` names `review`
  as the next step for a pull request from the round, `run` starts a reviewer
  session on it at the roles file's model and effort for the reviewer. It
  stops rather than start one when either is above its own session's, as
  `check-role` finds. A later look at the same pull request goes back to the
  reviewer session that reviewed it, and `run` starts a new reviewer only
  when it has not started one on that pull request, or that reviewer's
  session has stopped or is archived.
- `workissue-answers-each-thread` (step): When a review comment arrives on
  its pull request, work-issue answers each unresolved thread with a reply
  opening with `**Claude:**`, and leaves resolving it to the reviewer.
- `workissue-hands-review-todos` (step): When an unresolved thread on its
  pull request holds a review comment that opens with `TODO`, and the
  session has a skill whose description says it processes the TODOs in a
  pull request's review comments, work-issue hands that skill the pull
  request's number through the Skill tool before it answers any thread. When
  the session has no such skill, it answers that comment as any other thread.

## need owner-gets-review-from-policy: Review every pull request from a written policy

When a pull request is reviewed by an agent, the owner wants the review made
from a written policy in a fresh context, so reviews are comparable and nits
cannot bury a real finding.

Source: #650, and the playbook's `review-against-written-policy` and
`separate-generation-from-verification`.

- `reviewpolicy-cmd-prints-policy` (test): When `flywheel.py review-policy`
  runs, it prints the project's review policy with its scale and cap, and
  exits 2 when the file is missing.
- `reviewbrief-cmd-prints-pull-request` (test): When
  `flywheel.py review-brief N` runs, it prints pull request N's head, its
  description, the requirement ids named in the section the pull request
  template marks, its
  review threads, its diff, and the head the reviewer last reviewed. It
  exits 1 when N is not open.
- `reviewpost-cmd-checks-findings` (test): When
  `flywheel.py review-post N --findings <file>` reads findings that do any of
  these, it names each fault, posts nothing and exits 1:
  - name a head other than N's.
  - hold more P3 findings than the review policy's cap.
  - put a finding on a file N does not change, or at a level outside P0 to P3.
  - put a finding on a line outside N's diff, one that a review comment cannot
    sit on.
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

## need owner-adopts-by-level: Adopt the playbook by level

When the owner brings a repo under the playbook, they want its gaps named by
principle id against the level they chose, filed one control per issue, and
the version recorded, so a later assessment shows only what changed.

Source: #651, the playbook's adoption.md, and the playbook's
`checks-over-instructions`.

- `assess-cmd-reports-gaps-by-id` (test): When `flywheel.py assess` runs in a
  project, it reports each level, and each control the level introduces by its
  principle ids, with its evidence found or missing. It exits 1 when a control
  that a level at or below the recorded level introduces is missing.
- `assess-cmd-checks-level-1-controls` (test): When `flywheel.py assess`
  runs, it holds level 1 only when the project holds all of these controls,
  each named by its key:
  - `agent-rules`, rules for agents in the file agents read every session,
    from the playbook's `trace-behavior-to-need` and
    `humans-decide-agents-record`.
  - `needs-spec`, a needs spec for each component opening with its
    out-of-scope list, from the playbook's `list-out-of-scope-first` and
    `source-needs-outside-code`.
  - `approved-ticket`, the ticket as the home of each change's intent, which
    the owner approves, from the playbook's `owner-admits-every-need` and
    `one-home-per-artifact`.
  - `core-gates`, the `build`, `test` and `check` commands, from the playbook's
    `one-command-per-gate`.
  - `tests-first`, tests written first and named for behavior, from the
    playbook's `write-behavior-tests-first`.
- `assess-cmd-checks-level-2-controls` (test): When `flywheel.py assess`
  runs, it holds level 2 only when the project holds level 1 and all of these
  controls, each named by its key:
  - `trace-checks`, traceability checks in CI, from the playbook's
    `checks-over-instructions` and `no-merge-without-alignment`.
  - `verify-gate`, the `verify` command run by CI on every pull request, from
    the playbook's `one-command-per-gate`.
  - `unweakened-checks`, new tests that must fail on the base and checks that
    agents cannot loosen, from the playbook's `agents-never-weaken-checks`.
    It is held only when `.flywheel/gates.json` gives the test commands
    under `tests`, the `verify` command or a file it names runs
    `fails-on-base`, and a workflow cites the principle.
  - `approval-guard`, approval kept out of agent reach by a hook or a CI
    check, from the playbook's `checks-over-instructions` and
    `owner-admits-every-need`.
  - `plan-first`, a plan approved before code, from the playbook's
    `approve-plan-before-code`.
  - `review-policy`, a written review policy and a fresh-context reviewer,
    from the playbook's `review-against-written-policy` and
    `separate-generation-from-verification`.
- `assess-cmd-checks-level-3-controls` (test): When `flywheel.py assess`
  runs, it holds level 3 only when the project holds level 2 and all of these
  controls, each named by its key:
  - `instruction-evals`, evals for the agent's instructions rerun on every
    change to them, from the playbook's `eval-instructions-on-change`.
  - `role-tiers`, agents assigned by role and tier, each tier with a model and
    a default effort, from the playbook's `match-capability-to-task`.
  - `merge-policy`, a written merge policy, from the playbook's
    `autonomy-scales-with-risk`.
  - `scheduled-audit`, a scheduled audit, from the playbook's
    `audit-on-schedule`.
  - `loop-measures`, measures for each stage with control bands, from the
    playbook's `measure-the-loop` and `scripts-detect-models-diagnose`.
  - `measured-trials`, improvement trials one change at a time against a
    baseline, from the playbook's `improve-by-measured-trial`.
  - `mistakes-to-checks`, repeated mistakes that climb to checks, from the
    playbook's `repeat-mistakes-become-checks`.
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
  lacks, and exits 1 when one is missing. Those labels are the role labels
  and the kinds, as `.flywheel/labels.json` gives them. With `--create`, it
  creates each one, with the description the file gives it.
- `labels-cmd-sets-kinds` (test): When `flywheel.py labels` runs with
  `--kind NAME=TEXT`, it writes the kinds given, each with its description,
  into `.flywheel/labels.json` in place of the ones the file gives, and
  leaves the file's other keys as they are, before it names the missing
  labels. It refuses an option without a NAME, and writes nothing when the
  result breaks a rule that `labelsfile-refuses-bad-map` lists.
- `adopt-creates-missing-labels` (step): When adopt runs, it shows the owner
  the missing labels and creates them once the owner agrees, before it hands
  any gaps to file-issue.
- `adopt-files-gaps-as-plan` (step): When `record` names a control missing at
  or below the target level, adopt files the gaps as one plan through
  file-issue, one control per issue, in the order of the playbook's tables.
- `hook-ships-with-plugin` (test): When the plugin is installed, its
  `hooks/hooks.json` runs the approval guard on every Bash call.

## need owner-checks-new-tests-fail: Check that each new test fails on the base

When the owner adopts the playbook at level 2, they want the plugin to fail a
pull request whose new test passes on the code before its change, in a
project of any language, so the control is a check rather than a comment.

Source: #682, and the playbook's `agents-never-weaken-checks`.

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
- `failsonbase-cmd-runs-report-command-once` (test): When `tests` in
  `.flywheel/gates.json` gives `report`, a command that runs the tests in the
  files that `{files}` names in one run and writes a JUnit XML report to the
  path that `{report}` names, `fails-on-base` runs it once at the branch and
  once in the base tree, and reads each new test's outcome from the report.
  A test's file is its id up to the first `::`. A report that is missing or
  cannot be parsed exits 2 and names the command. Without `report`,
  `fails-on-base` runs each new test alone with `run`.
- `failsonbase-cmd-maps-report-cases-to-ids` (test): `fails-on-base` maps
  each test case in the report to the id that `list` prints, in pytest's
  form. The case's `classname` is the id's file with `/` as `.` and `.py`
  dropped, then its classes, and its `name` is the test's name with any
  parameters. A new test that the report does not name, or names more than
  once, does not pass that run. A case with `<failure>` or `<error>` does not
  pass, and a skipped case passes.
- `configinit-cmd-fills-pytest-report-command` (test): When
  `flywheel.py config init` finds pytest, it writes the pytest `report`
  command, which runs with `--continue-on-collection-errors`, under `tests`
  in `.flywheel/gates.json`. For any other runner it leaves `report` unset.
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

Source: #652, and the playbook's `measure-the-loop` and
`improve-by-measured-trial`. specs/repo.md holds the requirement this repo's
scheduled workflow meets under this need.

- `measure-cmd-reports-starting-measures` (test): When
  `flywheel.py measure --since <when>` runs, where `<when>` is a date such as
  `2026-10-12` or a UTC time such as `2026-10-12T06:03:00Z`, it reports spend,
  first-pass CI, reviewer findings by level and lead time for each pull
  request merged at or after it, and a summary, and says which it could not
  compute and why.

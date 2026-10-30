# flywheel: technical design

This file explains why the flywheel plugin is built the way it is, for a
contributor changing it. What the plugin does and how to use it is in
[README.md](README.md). The requirements it serves are in `specs/flywheel.md`,
at the repo root.

## Origin

The owner ran the issue loop by hand: three desktop sessions a round, each
started with its model and effort chosen, told when CI failed or a review
landed, and told when its pull request merged. The parts a script or a skill
could do lived in this repo's `.github/scripts/issues.py` and its
`.claude/skills/`, which no other repo can install. Plan issue #653 plans
the move into this plugin, one piece per issue. #643 made the plugin exist
with its script's first two commands, #645 moved the queue and the claim
lock in from `issues.py`, and #647 moved the plan commands and the file-plan
skill, which became `plan` and the file-issue skill.

## The copy in `.flywheel/`

`setup` copies `flywheel.py` into the project for the reason todos and
prose-tuning do: each Bash call starts a fresh shell, and the plugin's install
path is too long to repeat in every command. It also copies the roles template
and `plugin.json` beside the script, so the copy can run `config init` and
read the plugin's version without reaching back into the plugin.

The `.gitignore` that `setup` writes names those copies and itself, rather
than `*` as todos does. `.flywheel/` also holds what the owner sets and
commits, starting with `roles.json`.

## The playbook's docs

`docs/` holds the playbook the loop follows, copied from the Cowork project
where it was first written, at that project's commit 940ae7a. That project
stays as the archive, with its history, its notes and its own skills; the
plugin is now where the playbook changes. Its ids become stable once a repo
records an adopted version, and the plugin's version is that version.

`ids` checks that every id the plugin's templates and skills, and
`specs/flywheel.md`, cite as the playbook's is one the docs define. It reads
the docs from the plugin, so it does not run from the copy in `.flywheel/`.
The script's docstring has the citation form it reads.

## The roles file

A role maps to a tier from the playbook's roles.md, and the tier is fixed. The
model behind a tier, and its default effort, come only from the owner, so
the template leaves them null and `config init` names each null field it
writes. `config init` fills in the plugin version, so a later version can tell
which template a roles file came from.

## The lock

The claim on issue N is the branch `issue/N` on origin, created by a push
that only one claimant can win. flywheel.py's docstring has why the push uses
an empty lease and reads porcelain output rather than its exit code.

Some of the requirements on the lock stay in `specs/repo.md`: the ones this
repo's own CI, hooks and CLAUDE.md meet, since `check-specs.py trace` ties a
repo test or workflow step to `specs/repo.md` only. Those needs appear in both
files, each holding the requirements its side meets.

## Plans

The playbook's Scope stage files issues, and the loop needs it twice: the
owner files a plan, and an implementer that finds a gap files a candidate
need rather than guess. One skill, file-issue, does both, so a plan of one
issue leaves out the plan issue that a plan of several takes.

`plan report` and `plan file` write the report and the record of what was
filed to `.flywheel/plan/`, which holds a `.gitignore` of its own. The
`.gitignore` that `setup` writes names only the files it copies, and a
repository can run the plugin's own script without `setup`, so the folder
ignores itself.

The requirements the plan commands meet under a constraint, rather than
under a need, stay in `specs/repo.md`, and the plugin's tests and skill cite
them as `repo:<id>`. Each constraint is the repo's own copy of one in
another plugin's spec, and copying it again into `specs/flywheel.md` waits on
an issue that names it.

## The issue-closed workflow

`templates/issue-closed.yml` takes the claim label off an issue that closes,
since a claim usually ends with a merge, where no command of the script
runs. For the same reason, a second job runs `plan close --sub-issue` with the
closed issue's number, which closes the issue's plan issue once every
sub-issue is closed. That job fetches the script as the loop report does, and
runs in a concurrency group, so two issues that one merge closes lead to one
close of their plan. The claim label's job stays outside the group, since
GitHub cancels a run waiting in a group when another one queues. A project copies it into `.github/workflows/`. This repository's copy
adds the `# spec:` line that ties its step to `specs/repo.md`.

## The loop report

`templates/loop-report.yml` runs `stale` and `measure` on the schedule its
`cron` line sets, and keeps the result in one open issue, found by its title.
Its `measure` window opens on the day the last successful run started, so a
project that changes the schedule still gets each merge reported. It fetches the script from the
repository that ships the plugin, because a project's `.flywheel/` copy is
ignored by git and so is not in the checkout. This repository's copy adds the
`# spec:` line that ties its step to `specs/repo.md`.

## The brief

`brief` reads the issue through GitHub's GraphQL API, since only that reports
when the body was last edited and when each label was added. It refuses an
issue edited after the approval label was last added, as `check-specs.py changes`
does for the issues a pull request closes. Agents post under the owner's
account, so `brief` tells the owner's comments from an agent's by the
`**Claude:**` opening that CLAUDE.md asks an agent's comment to carry.

The gate commands live in `.flywheel/gates.json` rather than in the roles
file, since a role is a model choice and a gate is the project's own command.

## The implementer's skill

work-issue is the session a brief starts, and the one a request for "the next
issue" runs. It runs the gate command from `.flywheel/gates.json` itself
rather than through the script, since the command is the project's and a
skill fence runs only the plugin's script. It opens the pull request through
whichever installed skill says it opens one, so a project keeps its own
description rules and the skill names no other plugin.

The watch it turns on is the desktop app's per-session CI monitor, which only
the session's own `set_monitor` tool reaches. #305 found Auto-fix off on
every new pull request, so the skill turns it on rather than leaving it to
the owner.

The app turns on Auto-fix only for a pull request it saw the session open.
It sees that when the session's own Bash command runs `gh pr create`, and
binds the pull request then. `flywheel.py pr open` once ran `gh` itself, out
of the app's sight, so the app refused `set_monitor` on #794 to #827, even
after `bind_pr` (#831). `pr push` now checks the description and pushes the
branch, and open-pr runs `gh pr create` in the same command, joined by `&&`,
so a description that fails the check still opens nothing. work-issue keeps
`bind_pr` and the "Auto-fix is off" report for a pull request that a
project's own skill opens out of the app's sight. A dispatcher sees only the
first 400 characters of a report, and relays that opening to the owner (#805).

The review-thread check runs every minute as a turn of the implementer's
session, and the dispatcher starts the session with `wake_when_done`, so a run
wakes the dispatcher once none of the sessions it started is working. Plan
#799's round showed dozens of near-identical wakes that buried the two changes
#806 describes (#807). The app gives a
scheduled job no way to hold back the wake, so the plugin cannot make a quiet
run silent. It makes a quiet run unmistakable instead: the reply opens with
"Nothing waiting on review threads", and says "CI" only for CI. run's step
7 still looks again on every wake. A dispatcher that skims a quiet note
misses nothing, since it also watches its pull requests (#806, #835).

## The dispatcher's skill

run starts the sessions through the desktop app's `start_session` tool,
which only a session can call, so the skill rather than the script starts
them. The script does the rest: `check-role` reads a role's model and
effort, refuses a field the owner has not filled in, and exits 1 when the
role is above the session's own. `events` reads the claim pull requests.
The app starts a session at or below its starter's model and effort, and
lowers anything higher, so the skill stops rather than start an
implementer or a reviewer weaker than the roles file says. It checks the
dispatcher role the same way before it starts anything, and checks each
started session against its role after.

`events` gives the newest merge it saw as the start of the next look, rather
than the time of the look, so a merge is never named twice and `clear` never
runs twice on one claim. The script's docstring has the case this leaves
out.

The dispatcher learns of a merge when it is woken. The watch exits when the
owner merges a pull request of the round, so the dispatcher notices the merge
and clears the claim without a message. The session for the next issue is
offered as a card, since the app refuses `start_session` on that turn.
What wakes it is in the "Waking the dispatcher" section.

The app's Auto-fix does not wake an implementer on every CI failure. On
#700 it woke the session when `validate` failed on head `c72cd46`, and did
not wake it when an edit to the description re-ran CI on that same head and
`validate` failed again. The rule behind this is unconfirmed. One that fits
is that the app reports a failure once per check per head commit. So on
`wait` the dispatcher reads whether the implementer is working, and messages
an idle one itself. It messages once for each head and set of reasons, and
then tells the owner, so that a check still running cannot pass messages
back and forth between the two sessions.

## Which turns start a session

The desktop app lets `start_session` start a session on one kind of turn: the
owner's own message to the dispatcher. Its refusal on every other turn reads
"Start sessions only on the user's own words to you here; this turn runs an
automated event, another session's message, or the task another session gave
you." What plan #837's round showed on 2026-10-30 (#846):

| Turn | `start_session` |
| --- | --- |
| The owner's message | Starts. The reviewer on #845 started at 04:39:34Z, once the owner said "Start review-845". |
| A started session's turn end | Refused. The look that #845's opening woke found the next step `review`, and the call for the reviewer was refused. |
| A scheduled prompt | Refused by the app's wording ("an automated event"). Not measured on its own. |
| A background command's exit | Refused by the same wording, so `watch` does not lift it (#835). Not measured on its own. |

So a look the owner did not start cannot start a reviewer (step 9) or the
implementer for a freed place (step 6). The run skill's step 6 says what run does instead.

## Waking the dispatcher

A round's dispatcher acts on a pull request only when something wakes it, and
CI finishing does not (#835). The owner wants a change acted on within 15
seconds, in a repository whose CI takes seconds or tens of minutes, so the
wake has to come from the change.

What the desktop app does, measured on 2026-10-29 from the session transcripts
(`~/.claude/projects/`) of the #835 implementer and its dispatcher:

- A background command's exit wakes an idle session. A `sleep 30` run with
  `run_in_background` exited at 04:14:04.266 UTC, and the session's transcript
  queued the notification 7 ms later and began the turn after 34 ms. This was
  measured on the implementer, which is the same kind of session as the
  dispatcher. The dispatcher's own wake from a background exit was not
  measured, and neither was whether it still holds after a run of automated
  wakes with no message from the owner. If a round shows it does not, the
  watch moves to the Monitor tool.
- A started session's turn end wakes the dispatcher only once none of the
  sessions it started is still working. The #835 implementer ended a turn at
  04:13:37.7 while the #836 implementer was working. The dispatcher was not
  woken then. #836 ended its turn at 04:13:48.400, and the dispatcher's
  transcript queued both reports 10 ms later, in one wake.
- So with an implementer working, only the owner, a scheduled job or a
  background command wakes the dispatcher, which is why the wake alone does
  not bound the time to act. The wake itself takes under 0.1 s.

`flywheel.py watch` is the background command. It reads the round's open
pull requests every 5 seconds and exits when one has changed, so the app wakes
the dispatcher within about 5 seconds of the change, plus the 1 to 3 seconds
a read takes. A 15-minute scheduled job stays as a backup, in case a watch
stops without telling the dispatcher.

`watch` reads GitHub's REST API with conditional requests, since a `304 Not
Modified` costs nothing against the rate limit. On 2026-10-29, a watch of the
plan #837 round ran for 40 seconds, and once its first reads were done the core
rate limit's `used` read 81 before and after. What it reads for each open pull
request of the round:

- the head, from the list of open pull requests.
- the checks on the head, from the check runs and the commit status, summed
  into the `ci` word `events` gives, so a check that only moves from queued to
  running does not wake the dispatcher.
- the reviews.
- the review comments, which only prompt the thread read below.

Review threads come from GraphQL, which has no conditional request, and
whether a thread is resolved is not in the REST answers. `watch` reads them when a
review or a review comment changed, and on its own every 12th read, a minute.
A thread read of one pull request cost 1 point of the GraphQL limit on
2026-10-29, so a quiet watch spends about 60 points an hour for each open pull
request, and 500 points covers 8 of them. Resolving a thread alone can take up
to a minute to show.

`events` gives the `state` that `watch --state` starts from. The digests are
read before the rows are built, so a change that lands while the dispatcher
is looking makes the next watch exit at once. A pull request that opens, merges
or closes after the state was taken changes it too. The dispatcher passes
each watch's own `state` to the next, so its own merge wakes it once, and it
clears the claim from the row.

## Adoption

#651 gives the playbook's adoption.md a command. A level is how far a project
has adopted the playbook, and each level introduces controls. A control does
not have a level of its own: it belongs to the level that introduces it.

The controls each level introduces have their home in `specs/flywheel.md`,
in the requirements `assess-cmd-checks-level-1-controls` to `-3-`, so
changing one is a requirement change that holds the pull request for the
owner. adoption.md is the view that ships with the plugin, since `specs/`
does not. The script's `PLAYBOOK_LEVELS` is a third copy, because the copy in
`.flywheel/` carries neither, and tests fail when it differs from either.

The evidence for a control is something a script can read without
judgment, so two runs on the same project agree. The kinds of evidence
`assess` reads, and why each counts:

- A file the control names, such as `.flywheel/gates.json` or a policy,
  counts when it exists and the owner has filled in every setting, since a
  setting left null is a decision not yet made.
- A control kept by an instruction to agents counts when the rules files
  agents load every session cite its principle id. A script cannot see
  whether an agent follows a rule, only whether the rule is stated where the
  agent reads it.
- A control kept by a CI check counts when a workflow cites its principle
  id. The shape of a traceability check or an audit differs by project, so
  the citation is how the project says which step keeps the control.
- The approval guard counts when the project's settings run it, directly or
  by enabling the plugin, since a hook that is not registered does not run.
- The check that new tests fail on the base counts when the `verify` gate
  runs `fails-on-base`, in its command or in a file the command names, and
  the gates file gives the test commands it reads. The plugin ships that
  check, so a citation alone would hold the control without running it. A
  workflow must still cite the principle, for the checks that agents cannot
  loosen.

`templates/agent-rules.md` holds the rules adopt writes, by level, with a
rule for every principle each level's controls name. A test fails when a
level's section misses one. The adopt skill merges the sections into the
project's `CLAUDE.md` itself, since placing them beside the project's own
rules is judgment.

The approval guard moved from this repo's `.claude/hooks/` into the plugin's
`hooks/`, so an adopting project gets it by installing the plugin. This
repo's `.claude/settings.json` runs the plugin's copy, so it guards a session
here whether or not the plugin is installed. Its requirements stay in
`specs/repo.md`, and its tests cite them as `repo:<id>`.

## The reviewer and the merge policy

#650 pairs every implementer with a reviewer that starts without any of its
context, and lets the dispatcher merge under a written policy. Both policies
are markdown, since the owner reads and edits them as prose, with their
settings in one JSON fence that the script reads. `config init` copies them
whole and names each null setting, as it does for the roles file.

The reviewer, the implementer and the owner all post under the owner's
account, so `merge-check` cannot tell them apart by author. It tells them
apart by text the script writes itself: `review-post` opens the review and
each finding with a mark that `merge-check` reads back. The reviewer posts
through `review-post` rather than `gh`, so the mark, the P3 cap and the
"comment only" event are checked before anything reaches GitHub, and a skill
fence runs only the plugin's script.

The script cannot read whether an answer settles a finding, so the reviewer
looks again once the implementer has answered, and resolves what it
accepts. The owner chose that second look while #650 was worked. A thread left unresolved
after it is a disagreement, and holds for the owner. `merge-check` names the
next step, so the dispatcher does not weigh reasons itself. `--merge` merges
at the head it checked, so a push between the check and the merge cannot
slip through.

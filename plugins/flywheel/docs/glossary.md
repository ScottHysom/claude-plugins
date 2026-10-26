# Glossary: shared vocabulary

Each term has one meaning, used the same way by client, spec, code and agents (one-shared-vocabulary). Terms are kept in alphabetical order.

| Term | Meaning |
| --- | --- |
| A/B flight | An experiment that shows two or more variants to different users and measures which meets a success metric. |
| Admission | How a need or constraint enters the spec: only through the owner's approval of a ticket. |
| ADR | Architecture Decision Record. A short note on one decision and why it was made. |
| Agentic engineering | Disciplined software work done with AI agents under human direction and review. It is the opposite of "vibe coding." |
| Alignment (spec/code) | The spec describes what the code does, and the code does what the spec says. |
| BDD | Behavior-Driven Development. Tests and scenarios named for observable behavior, such as describe/it blocks or Given/When/Then. |
| `build` (command) | Compiles and packages. A no-op for code that runs without a compile step. The first rung of the command ladder. |
| Candidate need | An idea for a change that is possible but not needed, found during work. It is filed as a ticket for the owner to admit or not. Work does not pause for it (pause-on-discovery). |
| `check` (command) | `build`, then lint, format and type checks, then `test` with coverage, then the traceability checks. The Build stage's gate: a unit is done when `check` passes. |
| Command ladder | The four gate commands every repo exposes, each inside the next: `verify` ⊃ `check` ⊃ `build` + lint + `test` + trace. The playbook names them. Each repo's task runner defines them (one-command-per-gate). |
| Commit | A saved snapshot on a working branch. A commit is local and unreviewed. An implementer may make many commits for one PR. |
| Constraint | A platform fact that forces a design, such as a vendor's rate limit. It cites where the fact is recorded, and justifies the requirements under it. |
| Control band | The range a measure is expected to stay in, set from its own history, such as its mean plus or minus two σ. A script watches it and opens a ticket on a breach (scripts-detect-models-diagnose). |
| Core principle | A rule in the README's principles table: what the playbook holds to, true whatever the tools. Each serves a manifesto value (a line of the README's manifesto, saying which of two good things wins when they conflict). Compare stage rule. |
| Coverage floor | The lowest share of code branches the tests must run for a component. It starts at the day's figure and only rises. |
| DORA | DevOps Research and Assessment. Its four delivery metrics: deployment frequency, lead time for changes, change failure rate and time to restore service. |
| EARS | Easy Approach to Requirements Syntax. Templated sentences such as "When [trigger], the system shall [response]." |
| Effort | The second dial of a tier, beside the model class: reasoning budget, review passes, agents in parallel. It is set by the tier's default and raised for a hard task (match-capability-to-task). |
| Escalation | An agent handing a question up a tier, or to a human, instead of guessing. |
| Eval | A set task run through an agent's instructions, with the result graded. An eval verifies the model's half of a skill, where a test cannot. It is rerun whenever the instructions or the tier-to-model mapping change (eval-instructions-on-change). |
| Gate | A check that must pass before work moves to the next stage. |
| Improvement trial | A written, measured change to the playbook itself, such as a new model, effort setting or CI tool. It is kept only if its measures hold or improve (improve-by-measured-trial). The playbook's counterpart of an A/B flight. |
| Intent | The problem, outcome, users, constraints and open questions behind a change, captured in Scope. Its home is the ticket. The AI-Native SDLC Playbook keeps it as `intent.md`. |
| Job story | The form of a need: "When <situation>, <role> wants <outcome>, so <reason>." |
| Leading and lagging measures | A leading measure shows speed and moves first, such as time from request to approved ticket. A lagging measure shows quality and moves later, such as rework per change (measure-the-loop). |
| Maintain | Stage 7. It runs alongside the increments: the scheduled audit, scheduled scans and metric triggers. Its findings become tickets. |
| Measured improvement | The manifesto value behind improvement trials: the playbook is changed by measured trial, and every measure drives a decision. |
| Merge policy | A written policy naming which changes an agent may merge, in which environments, after which checks. Its autonomy scales with risk, and a human can revoke it (autonomy-scales-with-risk). |
| Mistake ladder | How a repeated agent mistake climbs to a stronger control: fixed once, a rule in the agent's instructions the second time, then a check or hook, and an eval once it reaches production (repeat-mistakes-become-checks). |
| MVP | Minimum viable product. The smallest version that delivers real value and produces feedback. |
| Need | Who wants what outcome, and why, written as a job story. It cites a source outside the code, and justifies the requirements under it. |
| Out of scope | A list at the top of each spec naming what the component deliberately does not do. |
| Owner | The human who decides what the codebase is for, admits needs and constraints, and approves work. |
| P0 ... P3 | Severity levels shared by the audit and PR review. A review nit is P3. They are not principle IDs. |
| Pause on discovery | Stopping work on a unit when coding reveals a needed change, updating the spec, then resuming against it. |
| Plan | The work units for one change, their order, the files each touches and the requirement IDs each builds. A plan is approved before code, is disposable and is never spec (approve-plan-before-code). Also the name of Stage 3. |
| Plan mode | A tool setting that keeps an agent read-only until a human accepts its plan. Claude Code has one. |
| Playbook | The Flywheel Playbook: the premise, manifesto, core principles and practices these documents define, which the flywheel plugin implements. A file cites one of its IDs as "the playbook's `id`". It is not the AI-Native SDLC Playbook, which this glossary names in full. |
| PR | Pull request. A request to merge a branch into main. It is the unit of review and approval (in GitHub, for example), and the point where no-merge-without-alignment is checked. |
| PRD | Product Requirements Document. Why the product exists, for whom, and how success is measured. |
| Premise | The idea the playbook rests on: the spec is the source of truth, and code is its implementation. It is the top layer of the README's diagram. |
| Principle ID | The stable name of a core principle or a stage rule, lint-rule style: kebab-case, at most four words. Example: no-merge-without-alignment. An ID is never renamed or reused, and a retired ID is listed in the README. |
| Proportionate capability | The manifesto value behind leg 2 (matching agents to tasks by capability and cost): each task gets the model and effort it needs, and no more. |
| Requirement | One sentence stating one behavior, in EARS order, with a stable ID and a kind (test, step, check or eval). It sits under the need or constraint it serves. A requirement is not the same as a principle. |
| Review policy | The written rules a reviewer works from: its passes, the P0 to P3 scale and a cap on nits (review-against-written-policy). The AI-Native SDLC Playbook keeps it as `REVIEW.md` at the repo root. |
| SDD | Spec-driven development. Any approach where a spec drives code generation. |
| SDLC | Software development life cycle. |
| Seam | A point where a model stands between one command's output and the next. Judgment and platform seams are kept; courier seams (where the model only carries one command's output to the next) move into the script. |
| Sigma (σ) | Standard deviation: how far values usually sit from their mean. Control bands are set in multiples of it. |
| Spec-anchored | SDD where the spec stays alive and in sync after the code is written. This playbook is spec-anchored. |
| Spec corpus | The full set of spec documents for one product. |
| Spec-first | SDD where the spec is written up front for a task, then set aside once the task is done. |
| Speculative generality | Code built for a need that nobody has. It is the failure that traceability exists to prevent. |
| Stacked PRs | A sequence of small PRs where each builds on the one before, reviewed and merged in order. They are the stair-step way to land large work. |
| Stage crosswalk | The table below this one, mapping the AI-Native SDLC Playbook's stage names to this playbook's. |
| Stage rule | A rule in stage-rules.md: how one stage applies a core principle. It often names a command, a format or a scale. A stage rule is cited by ID like a core principle. |
| Sufficient spec | A spec an implementer can build from without guessing intent. Anything shorter leaves gaps; anything longer is cost (sufficient-not-exhaustive). |
| TDD | Two meanings in this playbook, so always spell it out: **Technical Design Document** (a spec document) and **Test-Driven Development** (write-behavior-tests-first). |
| `test` (command) | Runs the unit tests only, fast and without coverage. It keeps its ecosystem's meaning, such as `npm test` or `pytest`. Passing `test` does not make a unit done. |
| Ticket | An item in the issue tracker (a GitHub issue, for example) that proposes a change. Its "Requirements" field lists the requirement IDs it adds, changes or removes. |
| Traceability chain | The links from code to test, test to requirement, and requirement to need or constraint. CI checks each link on every PR. |
| `verify` (command) | `check`, then the checks that need the base branch, independence or money: diff coverage, spec changes, evals and review. The Verify stage's gate: a PR is ready when `verify` passes. The command is not the same as the Verify stage itself. |
| Work unit | One independently buildable, reviewable piece of work produced by the planner. |

## Stage crosswalk

The AI-Native SDLC Playbook names its stages differently, and two of its names mean something else here. Use this playbook's names.

| SDLC Playbook stage | This playbook |
| --- | --- |
| Plan (`intent.md`) | 1 Scope |
| Design (`spec.md`) | 2 Spec |
| Build (`plan.md`, then code) | 3 Plan, then 4 Build |
| Test (each session checks its own work; evals in CI) | 4 Build (`check`), then 5 Verify (`verify`) |
| Deploy (AI review, approval gates) | 5 Verify, then 6 Release |
| Maintain | 7 Maintain |

"Plan" and "Design" are the collisions. The SDLC Playbook's Plan is this playbook's Scope. Here, "design" means the Technical Design Document or the design system, never a stage.

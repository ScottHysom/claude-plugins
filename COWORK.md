# Designing for Cowork

What Cowork lets a plugin's skills and scripts do, as live sessions have shown
it. Read this before designing anything that runs there. When a probe settles
something new, record it here, not only in a script's docstring or a pull
request, so the next design starts from it.

Nothing here comes from documentation. Each point is what a probe in a real
session printed. A question no probe has answered yet goes under "Not yet
known", added back when there is one.

## The container and the device

| | Container: the model's own shell | Device: `device_bash` |
|---|---|---|
| What it is | Cowork's cloud container | A Linux VM on the user's computer |
| Reads the installed plugin | Yes, under `/root/.claude/plugins/synced/...` | No: Permission denied |
| Sees the user's connected folder | No | Yes, at `$HOME/mnt/<folder name>` |
| Python | 3.11 | 3.10 |
| git | Yes | Yes |
| `$HOME` | `/root` | `/sessions/<session id>` |
| `$TMPDIR` | Not probed | `$HOME/tmp`, the VM's own disk: files there can be deleted |

- **The container's copy of the folder isn't the folder.**
  `/mnt/user-data/uploads/cowork-folders/<name>/` holds a read-only snapshot of
  a file or two, with no `.git`.
- **A script needs both machines.** It can read the plugin only in the
  container, and the project only on the device. Either it runs in the
  container and hands its output across, or it is copied across and runs on the
  device.
- **Every `device_bash` call starts afresh,** in `$HOME`, with no variable or
  `cd` kept from the call before. A command that needs the project starts
  with its own `cd`.

## Moving files: `device_commit_files`

- **Copies byte for byte, from `/mnt/user-data/outputs/` only.** It creates any
  directories it needs, so a mistyped folder quietly becomes a new, empty one.
- **Writes only into a connected folder.** It rejects paths elsewhere on the
  user's computer, and it rejects paths inside the VM, such as `$TMPDIR`: it
  addresses the computer, not the VM.
- **Never writes under `.git`:** "Writing to .git is not permitted via remote
  tools". That includes `.git/info/exclude`.
- **Copies dotfiles.** A file named `.gitignore` arrives like any other.
- **Execute bits are lost.** Run scripts as `sh x.sh` or `python3 x.py`.

## What the bridge cannot do

- **Delete a file in the connected folder.** Anything a skill writes there
  stays until the user removes it. So a write that replaces a file by moving a
  temp file over it fails, because that unlinks the target.
- **Write through git.** A git command that writes leaves a `.git/*.lock` the
  bridge cannot remove, and every later git write fails. Projects carry a
  `commit.sh` that the user runs from their own terminal for this reason.

## How skills load

- **`${CLAUDE_SKILL_DIR}` is filled in only in the text of `SKILL.md`,** as the
  skill loads. It and `$CLAUDE_PLUGIN_ROOT` are unset in both shells, and a
  reference file the skill reads is not filled in. A line that locates a plugin
  script has to live in `SKILL.md` itself.
- **`propose_skills` takes one `SKILL.md` and nothing else.** A skill that needs
  a bundled script works only from a marketplace install, or from an uploaded
  `.plugin` file.
- **A `.plugin` file is a zip of the plugin folder,** with `.claude-plugin/` at
  its root. Uploading one is how to try a branch: Cowork can't add a marketplace
  at a branch of a GitHub repo.
- **An upload is checked harder than a marketplace install.** It rejects a
  skill whose `description` contains anything that looks like an XML tag,
  "SKILL.md description cannot contain XML tags", even where the marketplace
  installed the same skill without complaint. `claude plugin validate --strict`
  doesn't catch it either. `check-skills.py descriptions` does, in CI, for every
  skill and generated-skill template under `plugins/`. A script that writes a
  generated skill, as gitify's does, rejects a tag in the description it is
  handed.

## How instruction files load

Probed on 2026-09-20, 2026-09-22 and 2026-09-23, in a Project made with "Use
an existing folder", beside the same files run through Claude Code 2.1.274.

| Source | Claude Code | Cowork |
|---|---|---|
| Project Instructions field | n/a | From the first message |
| Root `CLAUDE.md`, `.claude/CLAUDE.md` | At session start | From the second message, as a system reminder |
| `.claude/rules/*.md` with no `paths:` | At session start | From the second message |
| `@path` imports in `CLAUDE.md` | Expanded | Not expanded: the line stays as text |
| `CLAUDE.local.md` | Loaded | Not loaded |
| Block-level HTML comments | Stripped | Stripped |
| Path-scoped rules, a subfolder's `CLAUDE.md` | When Claude reads a matching file | Never |
| `AGENTS.md` beside a `CLAUDE.md` | Not loaded | Not loaded |

- **The first message sees only the field.** Its whole turn, every tool call
  included, runs without the folder's `CLAUDE.md`. The file arrives with the
  second message, before any tool call, even when neither message uses a
  tool: it is tied to the message, not to touching the folder.
- **Only the connected folder's root counts.** A `CLAUDE.md` in a folder
  inside the connected one, or above it, is never loaded. Files are read
  through `device_bash`, which triggers nothing, so neither are path-scoped
  rules.
- **A "Start from scratch" Project has no folder,** whatever Cowork's guide
  says: none is created on disk and none is linked, though a chip with a
  folder icon and the project's name sits below the prompt box. A session in
  it reports no connected folder. Only the field carries standing
  instructions there.

## What the design follows from this

- **Do the logic where the files are.** Rendering new files works in the
  container: `gitify-cowork-project` stages them and the bridge copies them
  across. Reading and changing an existing project works on the device:
  `prose-tuning` copies its script into the project and runs it there.
- **Stage, copy, check.** A script writes what goes across under
  `/mnt/user-data/outputs/`. It prints the `files` list `device_commit_files`
  takes, and a `sha256sum --check` for `device_bash` to run after the copy. It
  refuses a destination that doesn't exist yet, instead of letting the copy
  create it.
- **Write in place with `open(path, "w")`.** Never write a temp file and move
  it into place.
- **Only read git.**
- **A plugin's files in a project stay in the plugin's own folder.** Name it
  `.<plugin name>/` and give it a `.gitignore` holding `*`. Git then ignores the
  whole folder, that `.gitignore` included, so the project's commits never pick
  it up. The project's own `.gitignore` doesn't have to know the plugin exists,
  and no other plugin's templates have to either.
- **Instructions every session needs go in `.claude/rules/`, with no
  `paths:`.** Both products load a file there without being asked, as the
  table above shows, and a `paths:` key takes it out of that row. Unlike the root `CLAUDE.md`, a plugin can add a
  file there without editing one the project owns. The file is the project's
  own and is committed, unlike a plugin's working files in `.<plugin name>/`.
  `prose-tuning` keeps a project's rules in `.claude/rules/prose-style.md`.
- **Standing instructions need a line in the field.** A project that keeps
  them in a file has the field hold one line telling Claude to read it, or the
  first message of every conversation works without them.
- **Keep scratch files out of the project.** The bridge could never delete
  them. Pass data on stdin, or use `$TMPDIR` on the device.

## Not yet known

- **Whether the container's shell keeps a variable from one call to the
  next.** No probe has asked. A skill assumes it does not, and sets any
  variable it needs again in each command, as Claude Code requires anyway.

## Probing

The model can't run Cowork from Claude Code. It writes a probe prompt, the
user pastes it into a Cowork session and pastes the answers back. A probe that
works asks for:

- exact commands and verbatim output, with exit codes;
- every step run even when an earlier one fails;
- no writes beyond what each step names;
- a list of every file it created, since the bridge cannot remove them.

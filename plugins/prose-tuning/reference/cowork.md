# Running the skills on Cowork

In Claude Code, skip this page: the script and the checkout share one
filesystem, and every command runs as the skill shows it.

Cowork splits them. The container, where your shell runs, can read the plugin
but not the project. The device side, reached through `device_bash`, sees the
project but cannot read the plugin. So the script is copied into the project,
at `.prose-tuning/prose.py`, and every command runs there. `device_commit_files`
cannot write anywhere else: it accepts only a connected folder, and nothing
under `.git`.

You are on Cowork when `device_bash` and `get_device_info` are among your tools.

## Copy the script across

Do this once per session, after the skill's "Locate the script" step and before
its first command.

1. Call `get_device_info`. The project is one of its `connectedFolders`, or a
   folder inside one. Ask the author which, if it is not obvious.

2. Stage the script:

   ```sh
   python3 "$PROSE" stage --folder "<project folder>" --json
   ```

   Add `--connected "<connected folder>"` when the project is a folder inside
   the connected one. For `update-prose-config` on a project with no
   `prose-style.md`, add `--template <path>` too, naming the scaffold's shipped
   default, so `config init --from .prose-tuning/prose-style.template.md` has
   it on the device:

   ```sh
   find /root/.claude/plugins -path '*cowork-project-scaffold/skills/new-cowork-project/templates/prose-style.md'
   ```

   Exit 0: the files are under `/mnt/user-data/outputs/`. Exit 2: the message
   says which path was wrong.

3. Call `device_commit_files` with `files` set to `data.commit_files`. Stop and
   tell the author about anything it rejects.

4. Run `data.check_command` through `device_bash`. Every line must end `OK`.
   A line that does not means the copy arrived damaged. Stage and copy again;
   never edit the copy on the device.

The copy stays in the project, and the next session's copy overwrites it. The
bridge cannot delete files, so removing it is the author's job, from Finder.

## Run each command on the device

Every `python3 "$PROSE" ...` in the skill runs through `device_bash`, with
`data.device_setup` and `&&` in front:

```sh
cd "$HOME/mnt"/'Notes' && PROSE=.prose-tuning/prose.py && python3 "$PROSE" preflight --for apply
```

Put the prefix on every call. It moves into the project, so a path the skill
gives relative to the project root works as written.

A file the skill writes for the script, such as `findings.json`, goes in
`"$TMPDIR"` on the device, not in the project. The bridge can write into the
project but never delete from it, so a scratch file there would be left behind
for good. Where a command reads `-`, a heredoc avoids the file altogether.

## When preflight says the copy is not ignored

```
.prose-tuning/prose.py  not ignored, so commit.sh's `git add -A` would commit it
```

The project's `.gitignore` is missing `.prose-tuning/`. The templates in
`cowork-project-scaffold` and `gitify-cowork-project` include it, and a project
made before they did does not. Offer to add the line:

```sh
<device_setup> && printf '\n.prose-tuning/\n' >> .gitignore
```

and tell the author that `.gitignore` now needs committing with the project's
own `commit.sh`. Then run preflight again. Do not pass `--force` past this
blocker: it exists so the copy stays out of the project's history.

# Before the first command

Every skill in this plugin starts here, straight after its "Locate the script"
step. That step stays in each `SKILL.md` because Cowork fills in the skill's
directory only there.

If the `ls` in that step failed, stop: the plugin isn't installed here. Every
step is a call into the script, and a missing one surfaces three commands later
as something unrelated. In Cowork the plugin has to come from the marketplace.
`propose_skills` carries a single `SKILL.md` and not the script.

```sh
python3 "$PROSE" where --json
```

- **`local`:** run every command exactly as the skill shows it. Only "Rules
  still at the project root", below, applies.
- **`cowork`:** the project isn't visible from here, and `device_bash`, which
  can see it, can't read the plugin. Copy the script into the project and run
  every command there, as below.

## On Cowork: copy the script across

1. Call `get_device_info`. The project is one of its `connectedFolders`, or a
   folder inside one. Ask the author which, if it isn't obvious.

2. Stage:

   ```sh
   python3 "$PROSE" stage --folder "<project folder>" --json
   ```

   Add `--connected "<connected folder>"` when the project sits inside the
   connected folder rather than being it. Exit 0: staged.
   Exit 2: the message names the path that was wrong.

3. Call `device_commit_files` with `files` set to `data.commit_files`. If it
   rejects anything, stop and tell the author.

4. Run `data.check_command` through `device_bash`. Every line must end `OK`.
   If one doesn't, stage and copy again. Never edit the copy on the device.

The folder `.prose-tuning/` now holds the script and the rules the plugin
ships, which `config init` starts from. It carries its own `.gitignore`, so it
never reaches the project's commits. It stays in the
project, and the next run's copy overwrites it.

## On Cowork: run each command on the device

Every `python3 "$PROSE" ...` in the skill runs through `device_bash`, with
`data.device_setup` and `&&` in front:

```sh
cd "$HOME/mnt"/Notes && PROSE=.prose-tuning/prose.py && python3 "$PROSE" preflight --for apply
```

- **Use the prefix on every call,** including one that only writes a file. It
  moves into the project, so a path the skill gives relative to the project
  root works as written, and `$TMPDIR` is the device's.
- **If preflight says `.prose-tuning/prose.py` is not ignored,** the
  `.gitignore` beside it didn't arrive. Stage and copy again. Never pass
  `--force` past this blocker.

## Rules still at the project root

A project's rules live in `.claude/rules/prose-style.md`, where every session
loads them. If preflight reports a `prose-style.md` at the project root, the
project predates that. Offer to move it, and with the author's yes run:

```sh
python3 "$PROSE" config move
```

It copies the file and never deletes one. Ask the author to delete the root
copy, then run preflight again. It blocks while both copies are there.

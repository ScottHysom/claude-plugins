# The batch file

A run writes its batch (the findings or the rules it hands to the script) to a
file outside the project, so the run does not leave a stray file in it. Make
the file with:

```sh
python3 "$PROSE" batch --json
```

`data.path` is a file that no other run is given. Name it in every later step
by the path exactly as `batch` printed it, never through `$TMPDIR` or another
variable. The skill's commands show it as `/var/folders/k2/T/prose-x8q1zv.json`.

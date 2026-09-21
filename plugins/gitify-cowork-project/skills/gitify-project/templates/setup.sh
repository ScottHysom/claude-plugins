#!/bin/sh
# One-time bootstrap that puts an existing Cowork project folder under git. Run
# it from your own terminal, after Claude has written the files:
#
#   sh setup.sh           stage everything and show what would be committed
#   sh setup.sh commit    stage again and make the first commit
#
# The folder already holds your work, and the first commit takes all of it. So
# the first run only stages: read the list, add anything that should stay out
# of git to .gitignore, and run `sh setup.sh` again until the list is right.
# Nothing is committed until you say `commit`.
#
# Each run empties the index and stages again; the files themselves are not
# touched. `git add -A` on its own never drops a file that is already staged,
# so a pattern added to .gitignore after the first run would not keep that
# file out of the commit.
#
# The bridge cannot complete a git commit (it cannot delete the HEAD.lock it
# strands), so the repo has to be created from here. Files arrive from the
# bridge without their execute bit, which is why this is run with `sh` and why
# it sets the bit on both scripts before git records them.
#
set -e
cd "$(dirname "$0")"
chmod +x setup.sh commit.sh

case "${1:-}" in
    "" | commit) ;;
    *)
        echo "usage: sh setup.sh [commit]" >&2
        exit 2
        ;;
esac

if [ -d .git ] && git rev-parse --verify --quiet HEAD >/dev/null; then
    echo "Already a git repo with history. Nothing to do."
    echo "Use ./commit.sh for later commits."
    exit 0
fi

[ -d .git ] || git init --quiet

# clear anything the bridge could not remove
find .git -name '*.lock' -delete 2>/dev/null || true

git read-tree --empty
git add -A

if [ "${1:-}" != commit ]; then
    echo "Staged, not committed. These are the files the first commit would take:"
    echo
    git status --short
    echo
    echo "Anything here that should not be in git: add a pattern for it to"
    echo ".gitignore and run 'sh setup.sh' again to see the new list."
    echo "When the list is right, run 'sh setup.sh commit'."
    exit 0
fi

if [ -s .commit-msg ]; then
    git commit --quiet -F .commit-msg
    : > .commit-msg
else
    git commit --quiet -m "chore: adopt existing folder into git with gitify-cowork-project"
fi

echo "Done. From now on, use ./commit.sh"
git --no-pager log --stat --oneline

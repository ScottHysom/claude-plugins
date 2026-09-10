#!/bin/sh
# One-time bootstrap for a Cowork project folder. Run it once, from your own
# terminal, after Claude has scaffolded the folder.
#
# The bridge cannot complete a git commit (it cannot delete the HEAD.lock it
# strands), so the repo has to be created from here.
#
set -e
cd "$(dirname "$0")"

if [ -d .git ]; then
    echo "Already a git repo. Nothing to do."
    echo "Use ./commit.sh for subsequent commits."
    exit 0
fi

git init
git add -A
if [ -s .commit-msg ]; then
    git commit -F .commit-msg
    : > .commit-msg
else
    git commit -m "chore: scaffold project from cowork-project-scaffold"
fi

echo
echo "Done. From now on, use ./commit.sh"
git --no-pager log --oneline

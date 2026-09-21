#!/bin/sh
# Commit helper for a Cowork project folder.
#
# The Claude bridge cannot delete files, so every commit it attempts strands a
# .git/HEAD.lock that blocks all later writes. This script clears that debris
# and makes the commit. Run it from your own terminal.
#
#   ./commit.sh                 use the message Claude left in .commit-msg
#   ./commit.sh "docs: ..."     use a message given on the command line
#
set -e
cd "$(dirname "$0")"

# The first commit is setup.sh's, which shows what it would take first.
if ! git rev-parse --verify --quiet HEAD >/dev/null 2>&1; then
    echo "No commits yet: run 'sh setup.sh' for the first one." >&2
    exit 1
fi

# clear anything the bridge could not remove
find .git -name '*.lock' -delete 2>/dev/null || true
find .git -name 'tmp_obj_*' -delete 2>/dev/null || true

git add -A

if [ -n "$1" ]; then
    git commit -m "$1"
elif [ -s .commit-msg ]; then
    git commit -F .commit-msg
    : > .commit-msg
else
    echo "Nothing to commit with: pass a message or leave one in .commit-msg" >&2
    exit 1
fi

git --no-pager log --oneline -5

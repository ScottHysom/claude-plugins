#!/bin/sh
# Commit helper for this repo when Claude is editing it through Cowork's
# device bridge.
#
# The bridge cannot delete files, so every commit it attempts strands a
# .git/HEAD.lock that blocks all later writes. This script clears that debris
# and makes the commit. Run it from your own terminal.
#
#   ./commit.sh                 use the message Claude left in .commit-msg
#   ./commit.sh "feat: ..."     use a message given on the command line
#
# Editing the repo yourself? Just use git. This script is only for the case
# above.
#
set -e
cd "$(dirname "$0")"

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

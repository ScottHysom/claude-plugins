# Merge policy

The dispatcher merges a pull request without the owner when
`flywheel.py merge-check` reports that it flows under this policy, and asks
the owner about every other pull request, with merge-check's reasons. A
change that alters what the product does keeps the owner's gate. Source: the
method's `autonomy-scales-with-risk` and `owner-admits-every-need`.

## Flow

A pull request flows when all of these hold:

- It closes an issue labeled `approved`, from that issue's claim branch,
  `issue/N`.
- Every check on its head passes.
- The reviewer has posted a review of its head, and has resolved every
  finding thread. Every other unresolved thread has a reply.
- The section of its description that names requirement ids does not name
  one. `.flywheel/pr-template.md` marks that section, which is
  `## Requirements` without the file.

## Hold

The dispatcher holds a pull request for the owner when any of these holds:

- It adds, changes or removes a requirement: the section of its description
  that names requirement ids names one, or is missing.
- It touches a path that `protected` names.
- A P0, P1 or P2 finding is still open after the reviewer's look at its head.
- A thread stays unresolved after the reviewer's look at the implementer's
  answer, so the reviewer and the implementer disagree.
- GitHub reports a conflict, or the merge fails.

## Settings

```json
{
  "protected": ["specs/", "CLAUDE.md", ".claude/", ".github/", "plugins/*/templates/"]
}
```

- `protected` lists the paths a pull request holds for the owner when it
  touches one. A path that ends in `/` covers everything under it, and `*`
  matches any run of characters.

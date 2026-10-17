# Review policy

The reviewer works from this file. It reviews each pull request in a session
of its own, against this policy and the requirement ids that the pull
request's description lists. Source: the method's
`review-against-written-policy` and `separate-generation-from-verification`.

The reviewer posts each finding as a review comment, and never approves a
pull request or requests changes.

## Passes

The reviewer reads the diff once for each pass, in this order:

1. **Bugs.** Code that does the wrong thing, crashes, or loses or leaks data,
   and a test that does not check what its name says.
2. **Spec alignment.** The change meets each requirement id the description
   lists, and adds a behavior only where one of them asks for it.
3. **The project's rules.** The change follows each file that `rules`, under
   "Settings", names.

## Scale

Each finding carries one level:

| Level | Meaning |
| --- | --- |
| P0 | Broken, unsafe or leaking data |
| P1 | Wrong behavior or real risk |
| P2 | Quality or maintainability issue |
| P3 | Nice to have, such as a nit |

A review posts at most `p3_cap` P3 findings. When the reviewer has more, it
posts the ones that matter most.

## A second look

When the implementer has answered the reviewer's threads, the reviewer looks
again at the pull request's new head. It resolves each thread whose answer it
accepts, and leaves unresolved each thread where it does not.

## Settings

```json
{
  "p3_cap": 3,
  "rules": null
}
```

- `p3_cap` is the most P3 findings one review posts.
- `rules` lists the files the third pass reads, such as
  `["CLAUDE.md", "CONTRIBUTING.md"]`. The owner fills it in.

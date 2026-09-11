# claude-plugins

A personal plugin marketplace for Claude. Add it once, then install any plugin
listed below.

Plugins here may target Cowork, Claude Code, or both. **Each plugin's
description says which surface it needs.** The plugin format is identical
across surfaces, but a plugin that calls Cowork's device bridge will not work
in Claude Code, and installing it there will fail confusingly rather than
loudly.

## Adding this marketplace

In Claude Code:

```
/plugin marketplace add ScottHysom/claude-plugins
/plugin install cowork-project-scaffold@scott-claude-plugins
```

In Cowork, add the marketplace and install from the plugin browser.

Custom marketplaces do not auto-update. To pick up new versions:

```
/plugin marketplace update scott-claude-plugins
```

## Plugins

| Plugin | Surface | What it does |
|---|---|---|
| [cowork-project-scaffold](plugins/cowork-project-scaffold) | Cowork | Scaffolds a Cowork Project folder as a git repo, and generates a per-project skill that keeps its documents stating what is true while git holds the history |
| [prose-tuning](plugins/prose-tuning) | Claude Code, Cowork | Learns a project's house prose style from edits already made, records it as `prose-style.md` with stable rule ids, and conforms the rest of the documents to it |

## Layout

```
.claude-plugin/
  marketplace.json         the catalog. One entry per plugin
plugins/
  <plugin-name>/
    .claude-plugin/
      plugin.json          the plugin's own manifest
    README.md
    scripts/               optional. Shared by every skill in the plugin
    reference/             optional. Normative docs a skill points at
    skills/
      <skill-name>/
        SKILL.md           plus any files the skill bundles
```

A plugin's `source` in `marketplace.json` is a path relative to the repo root,
such as `./plugins/cowork-project-scaffold`. Adding a plugin means one new
directory under `plugins/` and one new entry in the catalog.

## Adding a plugin

1. Create `plugins/<name>/.claude-plugin/plugin.json` with at least a `name`
   field, in kebab-case, matching the directory name.
2. Put skills at `plugins/<name>/skills/<skill-name>/SKILL.md`. A skill can
   bundle reference files, scripts and templates in subdirectories beside its
   `SKILL.md`, and reach them at `${CLAUDE_SKILL_DIR}/...`. Anything two skills
   share goes at the plugin root instead, reached at
   `${CLAUDE_PLUGIN_ROOT}/...`. Copying it into each skill is how one parser
   becomes three that disagree.

   A plugin that bundles a script cannot be delivered to Cowork through
   `propose_skills`, which takes a single `SKILL.md` and no bundled files. Say
   so in the skill, or it fails confusingly at the point of use.
3. Add an entry to `.claude-plugin/marketplace.json` with `name`, `source`,
   `description` and `version`. State the required surface in the first
   sentence of the description.
4. Validate, then push:
   ```sh
   claude plugin validate .
   python3 .github/scripts/check-manifest-consistency.py
   ```

   CI runs both on every pull request. The second one catches what
   `claude plugin validate` cannot: two manifests that each validate but
   disagree with each other, such as a version bumped in one and not the other.

## Editing this repo from Cowork

Cowork's device bridge cannot delete files, so a commit it attempts strands a
`.git/HEAD.lock` that blocks every later write. `commit.sh` clears that and
commits. Claude drafts the message into `.commit-msg`; you run `./commit.sh`.

Editing the repo yourself needs none of this. Just use git.

## Versioning

Each plugin carries its own `version` in both `plugin.json` and its
`marketplace.json` entry. Keep them the same. Bump it whenever the plugin's
behaviour changes, or installed users have no signal that anything did.

Semver, starting at `0.1.0`. Patch for a fix, minor for new behaviour, major
when an existing project or workflow would need changing to keep working.

## Licence

MIT. See [LICENSE](LICENSE).

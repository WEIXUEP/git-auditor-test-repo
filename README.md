# Git / Gerrit long-history audit fixture

Disposable synthetic data for [git_large_object_auditor](https://github.com/WEIXUEP/git_large_object_auditor).
No production files, secrets or real review metadata are included.

## History and expected results

Approximately 100 commits span two years. `fixture-manifest.json` records the
generation seed, baseline date, blob IDs, sizes, paths, scenarios and expected
classifications at **5 MiB / 180 days** after restoring Gerrit refs.
The default baseline is **2026-10-20**. Age classifications in live audits
will change as time passes; the verifier freezes the audit clock to this date.

Scenarios include multiple large versions; deletion; identical-content
restoration; one blob at multiple paths; rename and cross-directory move;
small-to-large and large-to-small transitions; unmerged and merged branches;
shared branch history; lightweight and annotated release tags; recent deletion;
and historical source/document/data suffix protection.

Formats include valid Python comments, C++ and JavaScript comments, Markdown,
TXT, CSV, JSON, YAML, logs, ZIP, PNG and synthetic binary models. Entropy varies
deliberately; raw blob sizes differ from pack size and possible cleanup savings.
Every blob is below GitHub's 100 MiB ordinary Git limit. No LFS is used, since
LFS pointers would not exercise actual large Git blobs.

## Clone and restore simulated Gerrit refs

```shell
git clone https://github.com/WEIXUEP/git-auditor-test-repo.git disposable-audit-clone
python disposable-audit-clone/scripts/restore_gerrit.py --repo disposable-audit-clone --disposable-clone
```

Changes 1001 and 1002 contain two and three patch sets respectively. A later
patch set removes an upload, while earlier patch sets still retain it.
Patch sets share a target parent, as in Gerrit; later patch sets do not inherit
the earlier upload merely through their parent history.

`fixture-archive/*` tags transport patch-set commits through GitHub. They would
protect their tip trees during an audit, so the restore command validates the
archives, creates `refs/changes/*`, and removes **only these fixture tags in
the explicitly selected disposable clone**. Other branches and release tags
are retained. To restore again after tags were removed, fetch the archive tags
first: `git fetch origin 'refs/tags/fixture-archive/*:refs/tags/fixture-archive/*'`.
Ordinary `git clone` does not fetch Gerrit refs directly.

This is a Git ref simulation, not a Gerrit server: no refs/for submission,
Change-Id hook, NoteDb, review status, permission model or service-side GC.

## Verify against the auditor

Python 3.10+ and Git are sufficient; generation has no third-party dependency.
The auditor is provided separately. Run:

```shell
python scripts/verify.py --source . --auditor /path/to/git_history_auditor.py
```

The verifier creates a temporary independent clone and checks expected default,
code-protection, text/data-protection and path-exclusion results. It also checks
commit chronology, object sizes, file formats, Gerrit reachability, a clean
worktree, unchanged HEAD tree, local push/fetch, and `git fsck`.
It never rewrites history or pushes to GitHub.

## Generate another fixture

```shell
python scripts/generate.py /new/path/fixture --base-date 2026-10-20 --seed 24762
```

Both the destination and adjacent `<name>-local-test.git` must not exist.
The generated repository's `local-test` remote is that local bare repository;
`origin` is reserved for GitHub. Generated local remote paths are not portable.
After a GitHub clone, a local test remote can be created with:

```shell
git clone --bare disposable-audit-clone local-test.git
git -C disposable-audit-clone remote add local-test ../local-test.git
```

All data is synthetic and may be discarded in a disposable clone. Actual
auditor history cleanup and remote history replacement require separate user
confirmation. Never use mirror pushes to publish this fixture.

# Git / Gerrit long-history audit fixture

Disposable synthetic data for [Git History Toolkit](https://github.com/WEIXUEP/git-history-toolkit).
No production files, secrets or real review metadata are included.

## History and expected results

The original 100 commits span two years; the subtree extension adds small-file
histories on dedicated branches. `fixture-manifest.json` records the
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

## Squash-subtree migration scenarios

These scenarios extend this same large-object repository. `fixture/subtree`
contains two real squash imports, local edits by Subtree Alice, an unmerged
topic branch, a merge commit, and upstream v2 pulls. Mapping:
`vendor/a` to `components/a`, `vendor/b` to `third_party/deep/b`.
`fixture/subtree-renamed` additionally contains a historical move from
`vendor/a` to `vendor/legacy-a`; map both aliases to `components/a`.
`fixture/subtree-original` provides an unselected reference control.

`fixture-subtree/release` is annotated. The four
`fixture-subtree/upstream-{a,b}-{v1,v2}` tags retain original upstream objects,
including the native upstream path `vendor/a/embedded.txt`, which must not
be rewritten inside the upstream root. These tags differ from Gerrit archives.
`subtree-fixture.json` on `fixture/subtree` records identities and expectations.

Run the toolkit integration tests against a fresh clone:

```shell
git clone https://github.com/WEIXUEP/git-auditor-test-repo
git -C git-auditor-test-repo branch fixture/subtree origin/fixture/subtree
git -C git-auditor-test-repo branch fixture/subtree-topic origin/fixture/subtree-topic
git -C git-auditor-test-repo branch fixture/subtree-renamed origin/fixture/subtree-renamed
# Set GIT_HISTORY_FIXTURE to the clone's absolute path if not beside the toolkit.
cd git-history-toolkit
python -m unittest discover -s tests -p test_subtree_migration.py -v
```

Tests confirm migration only in disposable clones, compare every selected
commit's tree, identities and topology, check log/blame, perform two synthetic
upstream increments per selected ref/subtree and test repeated pull idempotency.
They also verify historical aliases, unchanged unselected refs, cancellation
and publication leases without publishing rewritten history.

`scripts/add_subtree_scenarios.py` reproduces the extension on a clean base
fixture that has no `fixture/subtree` refs. It refuses existing destinations:

```shell
python scripts/add_subtree_scenarios.py --repo /path/to/base-fixture --upstream-workspace /new/path/upstreams
```

The frozen subtree baseline is 2026-10-20 14:00 UTC. These are actual local
subtree operations, not a Gerrit service or permission simulation. Extending
the fixture requires updating expected_commit_count before its next commit;
large-object classifications and the audit date remain unchanged.

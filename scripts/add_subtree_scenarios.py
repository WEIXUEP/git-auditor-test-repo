"""Add an isolated subtree fixture branch without rewriting existing history."""

import argparse
import json
import os
from pathlib import Path
import subprocess


def build(repo, upstream_workspace):
    repo, upstream_workspace = Path(repo).resolve(), Path(upstream_workspace).resolve()
    env = os.environ.copy()
    env.update(GIT_AUTHOR_DATE="2026-10-20T14:00:00Z", GIT_COMMITTER_DATE="2026-10-20T14:00:00Z")

    def git(path, *args):
        return subprocess.check_output(["git", "-C", str(path), *args], env=env,
                                       stderr=subprocess.PIPE).decode().strip()

    if git(repo, "status", "--porcelain") or upstream_workspace.exists():
        raise SystemExit("Use a clean fixture and a new external upstream workspace")
    existing = git(repo, "for-each-ref", "--format=%(refname)")
    if "refs/heads/fixture/subtree" in existing or "refs/tags/fixture-subtree/" in existing:
        raise SystemExit("Subtree fixture refs already exist; refusing to overwrite")
    original = git(repo, "symbolic-ref", "--short", "HEAD")
    upstream_workspace.mkdir(parents=True)
    archives, sources = [], {}
    for name in ("a", "b"):
        upstream = upstream_workspace / name
        upstream.mkdir()
        git(upstream, "init", "-b", "main")
        git(upstream, "config", "user.name", "Upstream Fixture")
        git(upstream, "config", "user.email", "upstream@example.invalid")
        git(upstream, "config", "commit.gpgsign", "false")
        git(upstream, "config", "core.autocrlf", "false")
        (upstream / "lib.txt").write_text(f"upstream {name} line one\nupstream stable line two\n", encoding="utf-8")
        # A native upstream path that happens to match a host subtree prefix
        # must not itself be renamed inside squash-root trees.
        (upstream / "vendor/a").mkdir(parents=True)
        (upstream / "vendor/a/embedded.txt").write_text("upstream nested directory\n", encoding="utf-8")
        git(upstream, "add", "--all")
        git(upstream, "commit", "-m", f"Upstream {name} baseline")
        sources[name] = {"path": str(upstream), "v1": git(upstream, "rev-parse", "HEAD")}
    git(repo, "checkout", "-b", "fixture/subtree", "main")
    git(repo, "config", "commit.gpgsign", "false")
    for name in ("a", "b"):
        git(repo, "subtree", "add", "--prefix=vendor/" + name, sources[name]["path"], "main", "--squash")
        (repo / f"vendor/{name}/local-only.txt").write_text(f"local changes to {name}\n", encoding="utf-8")
        git(repo, "add", "--all")
        git(repo, "-c", "user.name=Local Maintainer", "-c", "user.email=maintainer@example.invalid",
            "commit", "-m", f"Maintain subtree {name} locally")
    git(repo, "checkout", "-b", "fixture/subtree-topic")
    (repo / "vendor/a/lib.txt").write_text("locally maintained first line\nupstream stable line two\n", encoding="utf-8")
    git(repo, "add", "--all")
    git(repo, "-c", "user.name=Subtree Alice", "-c", "user.email=alice@example.invalid",
        "commit", "-m", "Alice edits imported subtree before migration")
    alice = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "fixture/subtree")
    (repo / "subtree-unrelated.txt").write_text("host-only content must remain unchanged\n", encoding="utf-8")
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "Maintain unrelated host content")
    git(repo, "merge", "--no-ff", "fixture/subtree-topic", "-m", "Merge local subtree maintenance")
    for name in ("a", "b"):
        upstream = Path(sources[name]["path"])
        (upstream / "upstream-v2.txt").write_text(f"incremental {name} upstream version 2\n", encoding="utf-8")
        git(upstream, "add", "--all")
        git(upstream, "commit", "-m", f"Upstream {name} incremental version 2")
        sources[name]["v2"] = git(upstream, "rev-parse", "HEAD")
        git(repo, "subtree", "pull", "--prefix=vendor/" + name, str(upstream), "main", "--squash")
        for version in ("v1", "v2"):
            tag = f"fixture-subtree/upstream-{name}-{version}"
            git(repo, "tag", tag, sources[name][version])
            archives.append(tag)
    git(repo, "tag", "-a", "fixture-subtree/release", "-m", "Host subtree release before path migration")
    git(repo, "branch", "fixture/subtree-original")
    git(repo, "checkout", "-b", "fixture/subtree-renamed")
    git(repo, "mv", "vendor/a", "vendor/legacy-a")
    git(repo, "commit", "-m", "Historical git mv alias for subtree a")
    git(repo, "checkout", "fixture/subtree")
    manifest = {"branch": "fixture/subtree", "topic": "fixture/subtree-topic",
                "unselected": "fixture/subtree-original", "historical_alias": "fixture/subtree-renamed",
                "moves": {"vendor/a": "components/a", "vendor/b": "third_party/deep/b"},
                "alice_commit": alice, "archive_tags": archives,
                "upstream_commits": {name: {key: value for key, value in values.items() if key != "path"}
                                     for name, values in sources.items()}}
    (repo / "subtree-fixture.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    git(repo, "add", "subtree-fixture.json")
    git(repo, "commit", "-m", "Document subtree migration scenarios and upstream archive refs")
    git(repo, "checkout", original)
    print(json.dumps(manifest, indent=2))
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--upstream-workspace", required=True)
    args = parser.parse_args()
    build(args.repo, args.upstream_workspace)

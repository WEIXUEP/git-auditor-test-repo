"""Restore simulated Gerrit refs in an explicitly selected disposable clone."""

import argparse
import json
from pathlib import Path
import subprocess


def restore(repo):
    repo = Path(repo).resolve()
    manifest = json.loads((repo / "fixture-manifest.json").read_text(encoding="utf-8"))

    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args]).decode().strip()

    if git("status", "--porcelain"):
        raise SystemExit("Use a clean disposable clone")
    # Validate the complete archive before changing any references.
    for item in manifest["gerrit_refs"]:
        archived = git("rev-parse", "--verify", item["tag"] + "^{commit}")
        if archived != item["commit"]:
            raise SystemExit(f"Archive mismatch: {item['tag']}")
    for item in manifest["gerrit_refs"]:
        git("update-ref", item["ref"], item["commit"])
    for item in manifest["gerrit_refs"]:
        git("tag", "-d", item["tag"])
    print(f"Restored {len(manifest['gerrit_refs'])} Gerrit refs; removed only fixture archive tags")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--disposable-clone", action="store_true", required=True,
                        help="Acknowledge that fixture archive tags will be removed locally")
    restore(parser.parse_args().repo)

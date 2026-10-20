"""Build a GitHub-compatible, two-year Git/Gerrit audit fixture using stdlib only."""

import argparse
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import random
import shutil
import struct
import subprocess
import zipfile
import zlib

MIB = 1024 * 1024


def generate(destination, base_date="2026-10-20", seed=24762):
    root = Path(destination).resolve()
    remote = root.parent / (root.name + "-local-test.git")
    if root.exists() or remote.exists():
        raise SystemExit("Destination and adjacent local-test remote must not exist")
    root.mkdir(parents=True)
    baseline = datetime.fromisoformat(base_date).replace(hour=12, tzinfo=timezone.utc)
    records, archives = [], []

    def git(*args, day=0, input=None):
        env = os.environ.copy()
        stamp = (baseline - timedelta(days=730 - day)).isoformat()
        env.update(GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp,
                   GIT_CONFIG_NOSYSTEM="1", LC_ALL="C")
        return subprocess.check_output(["git", "-C", str(root), *args], env=env,
                                       input=input, stderr=subprocess.PIPE).decode().strip()

    def commit(message, day):
        git("add", "--all")
        git("commit", "-m", message, day=day)
        return git("rev-parse", "HEAD")

    def payload(path, version):
        rng = random.Random(f"{seed}:{path}:{version}")
        suffix = Path(path).suffix
        if suffix == ".png":
            width, height = 2048, 1366
            raw = b"".join(b"\0" + rng.randbytes(width * 3) for _ in range(height))
            def chunk(kind, data):
                return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
            return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
                    + chunk(b"IDAT", zlib.compress(raw, 1)) + chunk(b"IEND", b""))
        if suffix == ".zip":
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
                entry = zipfile.ZipInfo("synthetic-payload.bin", (2024, 1, 1, 0, 0, 0))
                archive.writestr(entry, rng.randbytes(10 * MIB))
            return buffer.getvalue()
        if suffix == ".bin":
            return rng.randbytes(10 * MIB)
        prefixes = {".py": "# ", ".cpp": "// ", ".js": "// ", ".md": "", ".txt": ""}
        rows = []
        if suffix == ".csv":
            rows.append("index,payload\n")
        elif suffix == ".json":
            rows.append("[\n")
        size = 0
        index = 0
        while size < 8 * MIB:
            # Mix repetitive text and deterministic entropy for realistic compression differences.
            value = ("synthetic-content-" * 30 if suffix in (".md", ".py") else rng.randbytes(240).hex())
            if suffix == ".json":
                row = ("," if index else "") + json.dumps({"index": index, "value": value}) + "\n"
            elif suffix == ".yaml":
                row = f"- index: {index}\n  value: '{value}'\n"
            elif suffix == ".csv":
                row = f"{index},{value}\n"
            elif suffix == ".log":
                row = f"2025-01-01T00:00:00Z INFO record={index} payload={value}\n"
            else:
                row = prefixes[suffix] + f"record {index} {value}\n"
            rows.append(row)
            size += len(row)
            index += 1
        if suffix == ".json":
            rows.append("]\n")
        return "".join(rows).encode()

    def large(path, scenario, status, version=1):
        content = payload(path, version)
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        oid = git("hash-object", path)
        records.append({"sha": oid, "paths": [path], "scenario": scenario,
                        "size_bytes": len(content), "expected_status": status})
        return content

    def remove(path):
        (root / path).unlink()

    def small(path):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("small replacement\n", encoding="utf-8")

    git("init", "-b", "main")
    git("config", "user.name", "Audit Fixture")
    git("config", "user.email", "fixture@example.invalid")
    git("config", "commit.gpgsign", "false")
    git("config", "tag.gpgsign", "false")
    git("config", "core.autocrlf", "false")
    git("config", "core.hooksPath", ".git/disabled-hooks")
    (root / "scripts").mkdir()
    for name in ("generate.py", "restore_gerrit.py", "verify.py", "add_subtree_scenarios.py"):
        shutil.copyfile(Path(__file__).parent / name, root / "scripts" / name)
    (root / ".gitignore").write_text("__pycache__/\n*.pyc\nreports/\n", encoding="utf-8")
    (root / ".gitattributes").write_text("* -text\n", encoding="utf-8")
    guide = Path(__file__).parent / "README.md"
    if not guide.is_file():
        guide = Path(__file__).parent.parent / "README.md"
    shutil.copyfile(guide, root / "README.md")
    initial = commit("Initialize documented reproducible audit fixture", 0)
    saved = None
    for step in range(1, 90):
        day = step * 8
        message = f"Maintenance iteration {step:02d}"
        if step in (2, 5, 8):
            large("models/model.bin", f"model_version_{step}", "CURRENT" if step == 8 else "OLD_VERSION", step)
            message = f"Publish model version {step}"
        elif step == 10:
            large("archives/deleted.zip", "deleted_zip", "DELETED_PATH")
            message = "Add historical ZIP archive"
        elif step == 12:
            remove("archives/deleted.zip")
            message = "Delete obsolete ZIP archive"
        elif step == 14:
            for path in ("src/legacy.py", "src/legacy.cpp", "src/legacy.js", "docs/legacy.md",
                         "docs/legacy.txt", "data/legacy.csv", "data/legacy.json", "data/legacy.yaml", "logs/legacy.log"):
                large(path, "deleted_" + Path(path).suffix[1:], "DELETED_PATH")
            message = "Add source, documentation and structured data snapshots"
        elif step == 18:
            for record in records:
                if record["scenario"].startswith("deleted_") and record["scenario"] != "deleted_zip":
                    remove(record["paths"][0])
            message = "Remove historical code and text data snapshots"
        elif step == 20:
            large("images/old.png", "renamed_and_moved_current", "CURRENT")
            message = "Add valid PNG image"
        elif step == 22:
            (root / "assets").mkdir()
            git("mv", "images/old.png", "assets/renamed.png")
            records[-1]["paths"].append("assets/renamed.png")
            message = "Rename image and move across directories"
        elif step == 24:
            small("transitions/growing.bin")
        elif step == 26:
            large("transitions/growing.bin", "small_to_large_current", "CURRENT")
            large("transitions/shrinking.bin", "large_to_small", "OLD_VERSION")
        elif step == 28:
            small("transitions/shrinking.bin")
            saved = large("restored/original.bin", "delete_restore_original_current", "CURRENT")
        elif step == 30:
            remove("restored/original.bin")
            message = "Delete object before later original-content restoration"
        elif step == 32:
            (root / "restored/original.bin").write_bytes(saved)
            (root / "shared").mkdir()
            (root / "shared/copy.bin").write_bytes(saved)
            records[-1]["paths"].append("shared/copy.bin")
            message = "Restore identical blob and reuse it at a second path"
        elif step == 35:
            branch_base = git("rev-parse", "HEAD")
            git("checkout", "-b", "feature/unmerged", branch_base)
            large("branch/retained.bin", "unmerged_branch_current", "CURRENT")
            commit("Retain large artifact only on unmerged branch", day - 1)
            git("checkout", "main")
            git("checkout", "-b", "feature/merged", branch_base)
            small("feature/merged.txt")
            commit("Develop feature on separate branch", day - 1)
            git("checkout", "main")
            git("merge", "--no-ff", "feature/merged", "-m", "Merge feature preserving branch history", day=day)
            message = "Record merged feature maintenance"
        elif step == 38:
            large("release/tagged.bin", "tag_only_current", "CURRENT")
        elif step == 39:
            tip = git("rev-parse", "HEAD")
            git("tag", "release-lightweight", tip)
            git("tag", "-a", "release-annotated", "-m", "Protected historical release", tip, day=day)
            remove("release/tagged.bin")
            message = "Delete artifact from main while release tags retain it"
        elif step == 88:
            large("recent/deleted.bin", "recent_deleted", "TOO_NEW")
            message = "Add recent experimental object"
        elif step == 89:
            remove("recent/deleted.bin")
            message = "Delete recent object within age protection window"
        (root / "maintenance.txt").write_text(f"Iteration {step:02d}\n", encoding="utf-8")
        commit(message, day)

    for change, count in ((1001, 2), (1002, 3)):
        for patchset in range(1, count + 1):
            git("checkout", "--detach", initial)
            if patchset < count:
                large("review/upload.bin", f"gerrit_{change}_{patchset}", "GERRIT_PATCHSET_ONLY", change * 10 + patchset)
            else:
                small("review/removed.txt")
            oid = commit(f"Change {change} patch set {patchset}: " + ("upload" if patchset < count else "remove upload"), 400 + patchset)
            ref = f"refs/changes/{change % 100:02d}/{change}/{patchset}"
            tag = f"fixture-archive/change-{change}-ps-{patchset}"
            git("update-ref", ref, oid)
            git("tag", tag, oid)
            archives.append({"ref": ref, "tag": tag, "commit": oid})
    git("checkout", "main")
    manifest = {"schema_version": 1, "base_date": base_date, "seed": seed,
                "expected_commit_count": int(git("rev-list", "--all", "--count")) + 1,
                "audit": {"min_size_mb": 5, "min_age_days": 180}, "objects": records,
                "gerrit_refs": archives, "branches": ["main", "feature/unmerged", "feature/merged"],
                "release_tags": ["release-lightweight", "release-annotated"]}
    (root / "fixture-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    commit("Publish fixture manifest and expected audit results", 730)
    git("gc")
    git("fsck", "--full")
    subprocess.check_call(["git", "clone", "--bare", str(root), str(remote)])
    git("remote", "add", "local-test", str(remote))
    git("push", "local-test", *[f"{item['ref']}:{item['ref']}" for item in archives])
    git("fetch", "local-test")
    print(json.dumps({"repository": str(root), "local_remote": str(remote),
                      "commits": int(git("rev-list", "--all", "--count")),
                      "large_objects": len(records), "raw_mib": sum(r["size_bytes"] for r in records) / MIB}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination")
    parser.add_argument("--base-date", default="2026-10-20")
    parser.add_argument("--seed", default=24762, type=int)
    args = parser.parse_args()
    generate(args.destination, args.base_date, args.seed)

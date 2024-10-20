"""Verify fixture integrity, local Git transport and auditor policy outcomes."""

import argparse
import ast
import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from unittest.mock import patch
import zipfile
import zlib


def verify(source, auditor):
    auditor = Path(auditor).resolve()
    if not auditor.is_file():
        raise SystemExit("--auditor must point to git_history_auditor.py")
    with tempfile.TemporaryDirectory(prefix="git-audit-verification-") as temporary:
        workspace = Path(temporary)
        repo = workspace / "clone"
        subprocess.check_call(["git", "clone", "--no-local", str(source), str(repo)])

        def git(*args, binary=False):
            result = subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.PIPE)
            return result if binary else result.decode().strip()

        manifest = json.loads((repo / "fixture-manifest.json").read_text(encoding="utf-8"))
        subprocess.check_call([sys.executable, str(repo / "scripts/restore_gerrit.py"),
                               "--repo", str(repo), "--disposable-clone"])
        count = int(git("rev-list", "--all", "--count"))
        assert 95 <= count <= 110, f"Unexpected commit count: {count}"
        commits = {}
        for line in git("log", "--all", "--format=%H %ct %P").splitlines():
            sha, stamp, *parents = line.split()
            commits[sha] = (int(stamp), parents)
        for sha, (stamp, parents) in commits.items():
            for parent in parents:
                assert commits[parent][0] <= stamp, f"Commit time inversion: {sha}"
        objects = git("rev-list", "--objects", "--all")
        sizes = subprocess.check_output(["git", "-C", str(repo), "cat-file",
                                         "--batch-check=%(objectname) %(objecttype) %(objectsize)"],
                                        input=objects.encode()).decode()
        large_ids = set()
        for line in sizes.splitlines():
            oid, kind, size = line.split()
            if kind == "blob":
                assert int(size) < 100 * 1024 * 1024, f"GitHub oversized object: {oid}"
                if int(size) >= 5 * 1024 * 1024:
                    large_ids.add(oid)
        assert large_ids == {item["sha"] for item in manifest["objects"]}
        for item in manifest["objects"]:
            data = git("cat-file", "blob", item["sha"], binary=True)
            assert len(data) == item["size_bytes"]
            suffix = Path(item["paths"][0]).suffix
            if suffix == ".json":
                json.loads(data)
            elif suffix == ".csv":
                assert all(len(row) == 2 for row in csv.reader(io.StringIO(data.decode())))
            elif suffix == ".py":
                ast.parse(data.decode())
            elif suffix == ".zip":
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    assert archive.testzip() is None
            elif suffix == ".png":
                assert data[:8] == b"\x89PNG\r\n\x1a\n"
                offset, compressed = 8, []
                while offset < len(data):
                    length = struct.unpack(">I", data[offset:offset + 4])[0]
                    kind = data[offset + 4:offset + 8]
                    body = data[offset + 8:offset + 8 + length]
                    checksum = struct.unpack(">I", data[offset + 8 + length:offset + 12 + length])[0]
                    assert checksum == zlib.crc32(kind + body)
                    if kind == b"IDAT":
                        compressed.append(body)
                    offset += 12 + length
                assert len(zlib.decompress(b"".join(compressed))) == 1366 * (2048 * 3 + 1)
        for item in manifest["gerrit_refs"]:
            assert git("rev-parse", item["ref"]) == item["commit"]
        for change in (1001, 1002):
            group = [r for r in manifest["gerrit_refs"] if f"/{change}/" in r["ref"]]
            assert git("ls-tree", "-r", group[0]["ref"], "review/upload.bin")
            assert not git("ls-tree", "-r", group[-1]["ref"], "review/upload.bin")
        before = git("rev-parse", "HEAD^{tree}")
        sys.path.insert(0, str(auditor.parent))
        from src.auditor import GitLargeObjectAuditor
        from src.options import build_parser
        from src.policy import CODE_FILE_SUFFIXES, TEXT_DATA_FILE_SUFFIXES

        class FixtureClock(datetime):
            @classmethod
            def now(cls, tz=None):
                fixed = datetime.fromisoformat(manifest["base_date"]).replace(hour=23, tzinfo=timezone.utc)
                return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)

        results = {}
        modes = {
            "default": [], "code": ["--protect-code-files"],
            "text": ["--protect-text-data-files"],
            "exclude-data": ["--exclude-path", "data/**"],
        }
        for mode, flags in modes.items():
            args = build_parser().parse_args(["--repo", str(repo), "--output-dir", str(workspace / mode),
                                              "--min-size-mb", "5", "--min-age-days", "180", *flags])
            with patch("src.auditor.datetime", FixtureClock):
                result = GitLargeObjectAuditor(args).run()
            observed = {blob.sha: blob.status.value for blob in result.blobs}
            expected = {}
            for item in manifest["objects"]:
                path = item["paths"][0]
                if mode == "exclude-data" and path.startswith("data/"):
                    continue
                status = item["expected_status"]
                suffix = Path(path).suffix
                if status != "CURRENT" and ((mode == "code" and suffix in CODE_FILE_SUFFIXES)
                                             or (mode == "text" and suffix in TEXT_DATA_FILE_SUFFIXES)):
                    status = "PROTECTED"
                expected[item["sha"]] = status
            assert observed == expected, json.dumps({"mode": mode, "expected": expected, "observed": observed}, indent=2)
            results[mode] = {status: list(observed.values()).count(status) for status in sorted(set(observed.values()))}
        assert git("rev-parse", "HEAD^{tree}") == before
        assert not git("status", "--porcelain")
        smoke_remote = workspace / "transport.git"
        subprocess.check_call(["git", "init", "--bare", str(smoke_remote)], stdout=subprocess.DEVNULL)
        git("push", str(smoke_remote), "HEAD:refs/heads/smoke")
        git("fetch", str(smoke_remote), "refs/heads/smoke")
        assert git("rev-parse", "FETCH_HEAD") == git("rev-parse", "HEAD")
        git("push", str(smoke_remote), ":refs/heads/smoke")
        git("fsck", "--full")
        print(json.dumps({"commits": count, "large_objects": len(large_ids),
                          "baseline": manifest["base_date"], "results": results,
                          "git_transport": "passed", "format_and_integrity": "passed"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Local repository path or clone URL")
    parser.add_argument("--auditor", required=True, help="Path to the auditor CLI entry point")
    args = parser.parse_args()
    verify(args.source, args.auditor)

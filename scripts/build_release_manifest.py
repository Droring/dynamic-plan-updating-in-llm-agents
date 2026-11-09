"""Build a deterministic SHA-256 manifest for the current Git release tree."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "provenance" / "RELEASE_MANIFEST_FINAL.json"
EXCLUDED = {
    "provenance/RELEASE_MANIFEST_FINAL.json",
    "provenance/RELEASE_MANIFEST.json",
    "provenance/RELEASE_MANIFEST_HISTORICAL.json",
    "provenance/RELEASE_MANIFEST_PRE_ACL2026.json",
    "provenance/RELEASE_MANIFEST_PRE_PILOT_TITLE.json",
    "provenance/RELEASE_MANIFEST_PRE_PORTABLE.json",
    "provenance/RELEASE_MANIFEST_PRE_PUBLIC_READY.json",
}

def tracked_files():
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
    )
    return sorted(p.decode("utf-8") for p in result.stdout.split(b"\0") if p)

def build():
    hashes = {}
    for name in tracked_files():
        if name in EXCLUDED:
            continue
        path = ROOT / name
        if not path.is_file():
            raise FileNotFoundError(f"tracked release file missing: {name}")
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "description": "SHA-256 of every tracked release file, excluding release manifest snapshots; hashes are computed over raw file bytes.",
        "algorithm": "SHA-256",
        "file_count": len(hashes),
        "sha256": hashes,
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if committed manifest is stale")
    args = parser.parse_args()
    generated = json.dumps(build(), ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if not MANIFEST.is_file() or MANIFEST.read_text(encoding="utf-8") != generated:
            raise SystemExit("RELEASE_MANIFEST_FINAL.json is stale; run python scripts/build_release_manifest.py and commit the result")
        print(f"release manifest current: {json.loads(generated)['file_count']} files")
    else:
        MANIFEST.write_text(generated, encoding="utf-8", newline="\n")
        print(f"wrote {MANIFEST.relative_to(ROOT)}: {json.loads(generated)['file_count']} files")

if __name__ == "__main__":
    main()

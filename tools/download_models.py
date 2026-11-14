"""Download and verify models listed in ``models/manifest.json`` (plan §10.1, T0.4). Standard library only.

    python tools/download_models.py            # download anything missing, verify pinned hashes
    python tools/download_models.py --pin      # also record sha256 for entries that have none (trust on first use)
    python tools/download_models.py --only scrfd_det_10g arcface_w600k_r50
    python tools/download_models.py --check    # verify only, never download

Exit code is non-zero on a hash mismatch or a failed download. Entries with an ``export`` key are produced by
that tool (not downloaded) and are only verified/pinned here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
MANIFEST = MODELS / "manifest.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(1 << 20):
            h.update(block)
    return h.hexdigest()


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "hid-model-downloader"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while chunk := resp.read(1 << 20):
            out.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r  {dest.name}: {done / 1e6:7.1f} / {total / 1e6:.1f} MB", end="", flush=True)
        print()
    tmp.replace(dest)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pin", action="store_true", help="record sha256 for entries that have none")
    ap.add_argument("--check", action="store_true", help="verify only; do not download")
    ap.add_argument("--only", nargs="*", help="restrict to these model names")
    args = ap.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    packs = {p["name"]: p for p in manifest.get("packs", [])}
    entries = [m for m in manifest["models"] if not args.only or m["name"] in args.only]
    rc = 0
    changed = False

    # 1. fetch packs that provide a wanted, missing member
    if not args.check:
        for entry in entries:
            path = MODELS / entry["file"]
            if path.exists() or "export" in entry:
                continue
            if "pack" in entry:
                pack = packs[entry["pack"]]
                zpath = MODELS / pack["file"]
                if not zpath.exists():
                    print(f"downloading pack {pack['name']} ...")
                    download(pack["url"], zpath)
                with zipfile.ZipFile(zpath) as zf:
                    if entry["file"] not in zf.namelist():
                        print(f"ERROR: {entry['file']} not found in {pack['name']} ({zf.namelist()})")
                        rc = 1
                        continue
                    zf.extract(entry["file"], MODELS)
            elif "url" in entry:
                print(f"downloading {entry['name']} ...")
                download(entry["url"], path)

    # 2. verify / pin
    for entry in entries:
        path = MODELS / entry["file"]
        name = entry["name"]
        if not path.exists():
            hint = f" (produce it with {entry['export']})" if "export" in entry else ""
            print(f"MISSING   {name:24s} {entry['file']}{hint}")
            continue
        actual = sha256_file(path)
        expected = entry.get("sha256") or ""
        if not expected:
            if args.pin:
                entry["sha256"] = actual
                entry["size_bytes"] = path.stat().st_size
                changed = True
                print(f"PINNED    {name:24s} {actual[:16]}...  ({path.stat().st_size / 1e6:.1f} MB)")
            else:
                print(f"UNPINNED  {name:24s} {actual[:16]}...  (run with --pin to record)")
        elif actual != expected:
            print(f"MISMATCH  {name:24s} expected {expected[:16]}... got {actual[:16]}...")
            rc = 1
        else:
            print(f"OK        {name:24s} {actual[:16]}...")

    if changed:
        MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {MANIFEST}")
    return rc


if __name__ == "__main__":
    sys.exit(main())

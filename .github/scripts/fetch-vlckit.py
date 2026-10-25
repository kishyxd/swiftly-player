#!/usr/bin/env python3
"""Download VideoLAN's official VLCKit xcframework and trim it to the slices
the three Apple targets need.

The full zip is ~916 MB and expands to ~2.9 GB. The app needs three device
slices (ios-arm64, tvos-arm64, macos-arm64_x86_64) and none of the debug
symbols, so the trimmed framework is ~210 MB.

The download runs in parallel byte ranges: VideoLAN throttles a single
connection hard (the upstream repository's own fetch script warns about
~40 KB/s), so the pieces are fetched concurrently and the result is verified
against the SHA256 the upstream repository already documents for this file.
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

URL = "https://download.videolan.org/cocoapods/unstable/VLCKit-4.0-20260805-1123.zip"
SHA256 = "c0c3ae1665053db5898581efc8ee920f526643526297f7fc643599532dc2ccf5"
SIZE = 916146006
KEEP = ("ios-arm64", "tvos-arm64", "macos-arm64_x86_64")
PIECES = 8

# The work directory needs ~1.2 GB (the zip plus the extracted slices). On the
# GitHub runner RUNNER_TEMP is on the big SSD; elsewhere fall back to the
# current directory rather than /tmp, which is often a small tmpfs.
_BASE = Path(os.environ.get("RUNNER_TEMP") or os.environ.get("VENDOR_WORK") or ".")
WORK = Path(tempfile.mkdtemp(prefix="vlckit-", dir=str(_BASE)))


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_piece(args):
    index, start, end, dest = args
    want = end - start + 1
    for attempt in range(1, 6):
        rc = subprocess.run(
            ["curl", "-sSL", "--retry", "3", "--max-time", "900",
             "-H", f"Range: bytes={start}-{end}", "-o", str(dest), URL],
            capture_output=True,
        )
        size = dest.stat().st_size if dest.exists() else 0
        if rc.returncode == 0 and size == want:
            return index, True, ""
        err = rc.stderr.decode("utf8", "replace")[-200:]
        print(f"  piece {index}: attempt {attempt} failed "
              f"(rc={rc.returncode}, size={size}, want={want}) {err}")
    return index, False, "size or status mismatch"


def download_parallel(dest):
    dest = Path(dest)
    if dest.exists():
        dest.unlink()
    part_dir = dest.parent / (dest.name + ".parts")
    shutil.rmtree(part_dir, ignore_errors=True)
    part_dir.mkdir(parents=True)
    step = (SIZE + PIECES - 1) // PIECES
    jobs = []
    for i in range(PIECES):
        start = i * step
        end = min(SIZE - 1, start + step - 1)
        if start > end:
            continue
        jobs.append((i, start, end, part_dir / f"part{i:02d}"))
    print(f"Downloading {SIZE} bytes in {len(jobs)} parallel pieces ...", flush=True)
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        for index, ok, err in pool.map(fetch_piece, jobs):
            if not ok:
                print(f"Parallel download failed on piece {index}: {err}")
                return False
    with open(dest, "wb") as out:
        for _, _, _, p in jobs:
            with open(p, "rb") as f:
                shutil.copyfileobj(f, out, 1 << 20)
    shutil.rmtree(part_dir, ignore_errors=True)
    return True


def download_single(dest):
    dest = Path(dest)
    print("Falling back to a single-connection download ...", flush=True)
    rc = subprocess.run(
        ["curl", "-sSL", "--retry", "5", "--max-time", "3600", "-o", str(dest), URL],
        capture_output=True,
    )
    if rc.returncode != 0:
        print("curl failed:", rc.stderr.decode("utf8", "replace")[-500:])
        return False
    return dest.exists() and dest.stat().st_size == SIZE


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    print(f"work directory: {WORK}")
    zpath = WORK / "VLCKit.zip"
    if not (zpath.exists() and zpath.stat().st_size == SIZE):
        if not download_parallel(zpath):
            if not download_single(zpath):
                print("ERROR: the VLCKit zip could not be downloaded.")
                return 1
    got = sha256_of(zpath)
    if got != SHA256:
        print(f"ERROR: SHA256 mismatch\n  expected {SHA256}\n  got      {got}")
        return 1
    print(f"SHA256 ok: {got}")

    out = WORK / "VLCKit.xcframework"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)

    # Extract only the slices, without their dSYMs. `unzip` is used rather
    # than Python's zipfile because the macOS slice contains symlinks
    # (Versions/Current) that Python's zipfile does not preserve.
    rc = subprocess.run(
        ["unzip", "-q", "-o", str(zpath), "VLCKit.xcframework/*",
         "-x", "*dSYMs*", "-d", str(WORK)],
        capture_output=True,
    )
    if rc.returncode != 0:
        print("ERROR: unzip failed:", rc.stderr.decode("utf8", "replace")[-500:])
        return 1
    extracted = WORK / "VLCKit.xcframework"
    for child in list(extracted.iterdir()):
        if child.name == "Info.plist":
            continue
        if child.name not in KEEP:
            print("  dropping slice", child.name)
            shutil.rmtree(child)
    print("  kept slices:", sorted(p.name for p in extracted.iterdir() if p.is_dir()))

    # The xcframework's Info.plist has to list exactly the slices that are
    # still on disk, and the debug symbol paths have to go with them.
    import plistlib
    info_path = extracted / "Info.plist"
    with info_path.open("rb") as f:
        info = plistlib.load(f)
    info["AvailableLibraries"] = [
        lib for lib in info["AvailableLibraries"] if lib["LibraryIdentifier"] in KEEP
    ]
    for lib in info["AvailableLibraries"]:
        lib.pop("DebugSymbolsPath", None)
    with info_path.open("wb") as f:
        plistlib.dump(info, f)
    print("  Info.plist now lists:",
          [lib["LibraryIdentifier"] for lib in info["AvailableLibraries"]])

    total = sum(p.stat().st_size for p in extracted.rglob("*") if p.is_file())
    print(f"Trimmed xcframework: {total / 1e6:.1f} MB")

    target = Path("Vendor/VLCKit.xcframework")
    shutil.rmtree(target, ignore_errors=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(extracted), str(target))
    print(f"Placed at {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

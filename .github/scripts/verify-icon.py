#!/usr/bin/env python3
"""Verify that the icon inside a built .app is the FTV artwork.

The reference is the owner's own file. It is compared **pixel by pixel**,
not by file hash: the app icon goes through `actool`, which re-encodes and
re-scales it, so the bytes in the bundle are never the bytes in the source
PNG. The comparison is a mean absolute difference per channel; 0.00 means the
two images are identical pixel for pixel.

Three ways to look at the icon, one per platform:

  * **macOS** - the `.icns` files in `Contents/Resources`. The 1024x1024 entry
    (`ic10`) is the one that carries the owner's artwork. The bundle holds
    the artwork unmasked, so it is compared against the reference directly.

  * **iOS** - the icon lives in `Assets.car`, and `actool` stores it with
    Apple's icon shape (a rounded "squircle") baked in, so the car cannot be
    compared against the owner's flat PNG directly. The workflow renders the
    car with Apple's own `iconutil` and renders a *reference* car - compiled
    from the owner's canonical PNG by the same `actool` - the same way, and
    the two renderings are compared here. Apple renders both, so an
    identical result means the built app carries the owner's artwork.
    The bundle additionally ships a fallback PNG for SpringBoard; that one
    is the flat artwork and is compared against the owner's PNG as well.

  * **tvOS** - the icon is a *brand* asset (a layer stack), which no public
    tool renders. What is verifiable is the layer's own content, and
    `assetutil --info` reports a SHA-1 digest for every rendition. The
    workflow dumps the metadata of the built car and of a reference car
    compiled from the reference PNG, and the two are compared here.

No third-party modules: the PNG decoding is done here with `zlib` from the
standard library, so the script runs on a bare runner.

Usage:
  verify-icon.py <reference.png> <bundle> [<reference.png> <bundle> ...]
      Compare the reference against every icon rendition in a built bundle.

  verify-icon.py --png-dir <dir> <reference.png>
      Compare the reference against every PNG in a directory (a rendered
      asset catalog, or the loose PNGs of a bundle).

  verify-icon.py --car-digest <built.json> <reference.json> <rendition>
      Compare the SHA-1 digest of one rendition between two `assetutil
      --info` dumps.
"""
import json
import os
import struct
import sys
import zlib


# ---------------------------------------------------------------- PNG reading

def png_chunks(data):
    """Yield (type, payload) for every chunk of a PNG byte string."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return
    off = 8
    while off + 8 <= len(data):
        length = struct.unpack(">I", data[off:off + 4])[0]
        ctype = data[off + 4:off + 8]
        payload = data[off + 8:off + 8 + length]
        if len(payload) < length:
            return
        yield ctype, payload
        off += 12 + length
        if ctype == b"IEND":
            return


def paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def is_cgbi(data):
    """True for Apple's own PNG encoding (`CgBI` chunk, raw deflate, BGRA)."""
    return b"CgBI" in data[:64]


def decode_cgbi(data):
    """Decode an Apple `CgBI` PNG into (width, height, [r,g,b] rows).

    `CgBI` PNGs differ from the PNG spec in three ways: the image data is a
    raw DEFLATE stream (no zlib header), the samples are BGRA instead of
    RGBA, and there are always four bytes per pixel.
    """
    off = 8
    idat = bytearray()
    ihdr = None
    while off + 8 <= len(data):
        length = struct.unpack(">I", data[off:off + 4])[0]
        ctype = data[off + 4:off + 8]
        payload = data[off + 8:off + 8 + length]
        if len(payload) < length:
            return None
        if ctype == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", payload[:13])
        elif ctype == b"IDAT":
            idat += payload
        off += 12 + length
        if ctype == b"IEND":
            break
    if ihdr is None or ihdr[2] != 8:
        return None
    width, height = ihdr[0], ihdr[1]
    try:
        raw = zlib.decompressobj(-15).decompress(bytes(idat))
    except zlib.error:
        return None
    bpp = 4
    stride = width * bpp
    if len(raw) < (stride + 1) * height:
        return None
    rows = []
    prev = bytearray(stride)
    pos = 0
    for _ in range(height):
        ftype = raw[pos]
        pos += 1
        line = bytearray(raw[pos:pos + stride])
        pos += stride
        if ftype == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif ftype == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ftype == 3:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                upleft = prev[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + paeth(left, prev[i], upleft)) & 0xFF
        elif ftype != 0:
            return None
        prev = line
        # BGRA -> RGB
        rgb = bytearray(width * 3)
        for x in range(width):
            b, g, r = line[x * 4:x * 4 + 3]
            rgb[x * 3] = r
            rgb[x * 3 + 1] = g
            rgb[x * 3 + 2] = b
        rows.append(bytes(rgb))
    return width, height, rows


def decode_png(data):
    """Decode an 8-bit non-interlaced PNG into (width, height, [r,g,b] rows).

    Apple's own `CgBI` encoding is handled as well. Returns None for
    anything it does not understand.
    """
    if is_cgbi(data):
        return decode_cgbi(data)
    width = height = None
    depth = ctype = None
    idat = bytearray()
    palette = b""
    for ctype_bytes, payload in png_chunks(data):
        if ctype_bytes == b"IHDR":
            width, height, depth, ctype = struct.unpack(">IIBB", payload[:10])
        elif ctype_bytes == b"PLTE":
            palette = payload
        elif ctype_bytes == b"IDAT":
            idat += payload
        elif ctype_bytes == b"IEND":
            break
    if width is None or depth != 8 or ctype not in (0, 2, 3, 4, 6):
        return None
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    try:
        raw = zlib.decompress(bytes(idat))
    except zlib.error:
        return None
    stride = width * channels
    if len(raw) < (stride + 1) * height:
        return None
    rows = []
    prev = bytearray(stride)
    pos = 0
    for _ in range(height):
        ftype = raw[pos]
        pos += 1
        line = bytearray(raw[pos:pos + stride])
        pos += stride
        if ftype == 1:
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 0xFF
        elif ftype == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ftype == 3:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                upleft = prev[i - channels] if i >= channels else 0
                line[i] = (line[i] + paeth(left, prev[i], upleft)) & 0xFF
        elif ftype != 0:
            return None
        prev = line
        rows.append(bytes(line))

    # Normalise everything to RGB.
    out = []
    for line in rows:
        rgb = bytearray(width * 3)
        for x in range(width):
            if ctype == 2:
                rgb[x * 3:x * 3 + 3] = line[x * 3:x * 3 + 3]
            elif ctype == 6:
                rgb[x * 3:x * 3 + 3] = line[x * 4:x * 4 + 3]
            elif ctype == 0:
                v = line[x]
                rgb[x * 3] = rgb[x * 3 + 1] = rgb[x * 3 + 2] = v
            elif ctype == 4:
                v = line[x * 2]
                rgb[x * 3] = rgb[x * 3 + 1] = rgb[x * 3 + 2] = v
            elif ctype == 3:
                idx = line[x]
                rgb[x * 3:x * 3 + 3] = palette[idx * 3:idx * 3 + 3]
        out.append(bytes(rgb))
    return width, height, out


def png_size(data):
    for ctype_bytes, payload in png_chunks(data):
        if ctype_bytes == b"IHDR":
            return struct.unpack(">II", payload[:8])
    return None


def area_resize(width, height, rows, new_w, new_h):
    """Box-filter resize (area average), so a downscaled rendition can be
    compared against a downscaled reference without nearest-neighbour noise."""
    if (width, height) == (new_w, new_h):
        return rows
    out = []
    for y in range(new_h):
        y0 = y * height // new_h
        y1 = max(y0 + 1, (y + 1) * height // new_h)
        line = bytearray(new_w * 3)
        for x in range(new_w):
            x0 = x * width // new_w
            x1 = max(x0 + 1, (x + 1) * width // new_w)
            tot = [0, 0, 0]
            count = 0
            for sy in range(y0, y1):
                row = rows[sy]
                for sx in range(x0, x1):
                    i = sx * 3
                    tot[0] += row[i]
                    tot[1] += row[i + 1]
                    tot[2] += row[i + 2]
                    count += 1
            i = x * 3
            line[i] = tot[0] // count
            line[i + 1] = tot[1] // count
            line[i + 2] = tot[2] // count
        out.append(bytes(line))
    return out


def mean_diff(a_rows, b_rows, width, height):
    total = 0
    for y in range(height):
        ra, rb = a_rows[y], b_rows[y]
        for x in range(width):
            i = x * 3
            total += abs(ra[i] - rb[i]) + abs(ra[i + 1] - rb[i + 1]) + abs(ra[i + 2] - rb[i + 2])
    return total / (width * height * 3)


# ------------------------------------------------------------- icon location

def icns_entries(path):
    """Return [(tag, png_bytes)] for the PNG-carrying entries of a .icns."""
    data = open(path, "rb").read()
    if data[:4] != b"icns":
        return []
    out = []
    off = 8
    while off + 8 <= len(data):
        tag = data[off:off + 4]
        length = struct.unpack(">I", data[off + 4:off + 8])[0]
        if length < 8 or off + length > len(data):
            break
        payload = data[off + 8:off + length]
        if payload[:8] == b"\x89PNG\r\n\x1a\n":
            out.append((tag.decode("latin1"), payload))
        off += length
    return out


def car_pngs(path):
    """Return the PNG streams embedded in an Assets.car.

    CoreUI stores the bitmap data of a rendition as a plain PNG inside the
    car, so scanning for the PNG signature finds them. The stream ends at the
    IEND chunk, which is found by walking the chunk lengths.

    (Xcode 26 stores most renditions LZFSE-compressed instead, so this scan
    usually finds nothing on a current toolchain. It is kept because it is
    the only way to read a car on a machine without Apple's tools.)
    """
    data = open(path, "rb").read()
    out = []
    start = 0
    while True:
        idx = data.find(b"\x89PNG\r\n\x1a\n", start)
        if idx < 0:
            break
        start = idx + 8
        off = idx + 8
        while off + 8 <= len(data):
            length = struct.unpack(">I", data[off:off + 4])[0]
            ctype = data[off + 4:off + 8]
            if off + 12 + length > len(data):
                break
            off += 12 + length
            if ctype == b"IEND":
                out.append(data[idx:off])
                break
    return out


def dir_pngs(path):
    """Return [(label, png_bytes)] for every PNG below a directory."""
    out = []
    for root, dirs, files in os.walk(path):
        dirs.sort()
        for name in sorted(files):
            if not name.lower().endswith(".png"):
                continue
            full = os.path.join(root, name)
            try:
                data = open(full, "rb").read()
            except OSError:
                continue
            if data[:8] != b"\x89PNG\r\n\x1a\n":
                continue
            label = os.path.relpath(full, path)
            out.append((label, data))
    return out


def bundle_renditions(bundle):
    """Return [(label, png_bytes)] for every icon rendition in a built bundle."""
    out = []
    resources = os.path.join(bundle, "Contents", "Resources")
    if os.path.isdir(resources):
        for name in sorted(os.listdir(resources)):
            if not name.endswith(".icns"):
                continue
            for tag, png in icns_entries(os.path.join(resources, name)):
                out.append((f"{name} [{tag}]", png))
        car = os.path.join(resources, "Assets.car")
        if os.path.exists(car):
            for png in car_pngs(car):
                out.append(("Assets.car", png))
        return out
    # An iOS or tvOS bundle keeps its resources at the top level.
    for name in sorted(os.listdir(bundle)):
        if not name.lower().endswith(".png"):
            continue
        full = os.path.join(bundle, name)
        if not os.path.isfile(full):
            continue
        data = open(full, "rb").read()
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            continue
        out.append((name, data))
    car = os.path.join(bundle, "Assets.car")
    if os.path.exists(car):
        for png in car_pngs(car):
            out.append(("Assets.car", png))
    return out


# ------------------------------------------------------------------- verdicts

def compare(reference, candidates):
    """Compare a reference image against a list of candidate renditions."""
    ref = decode_png(open(reference, "rb").read())
    if ref is None:
        print(f"ERROR: the reference {reference} could not be decoded.")
        return None
    ref_w, ref_h, ref_rows = ref
    print(f"reference: {reference} {ref_w}x{ref_h}")

    best = None
    exact = []
    for label, png in candidates:
        decoded = decode_png(png)
        if decoded is None:
            continue
        w, h, rows = decoded
        if (w, h) == (ref_w, ref_h):
            diff = mean_diff(rows, ref_rows, w, h)
            exact.append((label, w, h, diff))
            if best is None or diff < best[3]:
                best = (label, w, h, diff)
            continue
        # A smaller rendition: compare it against the reference scaled to
        # the same size, so a match is still recognisable.
        scaled = area_resize(ref_w, ref_h, ref_rows, w, h)
        diff = mean_diff(rows, scaled, w, h)
        if best is None or diff < best[3]:
            best = (label, w, h, diff)

    for label, w, h, diff in exact:
        print(f"  {label} {w}x{h}: mean diff {diff:.2f}  (exact size match)")
    if best is not None:
        label, w, h, diff = best
        print(f"  closest rendition: {label} {w}x{h}, mean diff {diff:.2f}")
        # 0.00 means pixel-identical. A small number is the same artwork
        # re-encoded and re-scaled by actool. A large number is the
        # wrong art.
        if diff > 12.0:
            print("  VERDICT: NOT the FTV artwork")
            return 1
        print("  VERDICT: FTV artwork")
        return 0
    # Nothing comparable was found. That is not a mismatch - it means the
    # check could not read the icon - and it must not be reported as one.
    print("  VERDICT: inconclusive - no comparable rendition found")
    return 1


def car_digest(built_json, reference_json, rendition):
    """Compare the SHA-1 digest of one rendition between two car dumps.

    The two catalogues do not hold the same set of renditions - the built
    one carries the whole app's assets, the reference one only the icon -
    so the renditions are matched by their key (name, idiom, scale and
    pixel size) and each matching group is compared.

    A key can hold more than one rendition: actool stores the icon twice,
    once as ARGB and once as ARGB-16, and the two have different digests.
    The whole group is therefore compared, digest for digest, rather than
    just the first entry.
    """
    def load(path):
        with open(path) as fp:
            return json.load(fp)

    def index(entries, name):
        """{rendition key: [entry, ...]} for every rendition called `name`."""
        found = {}
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("Name") != name:
                continue
            key = (entry.get("RenditionName"), entry.get("Idiom"),
                   entry.get("Scale"), entry.get("PixelWidth"),
                   entry.get("PixelHeight"))
            found.setdefault(key, []).append(entry)
        return found

    built = index(load(built_json), rendition)
    reference = index(load(reference_json), rendition)
    if not built:
        print(f"ERROR: the rendition {rendition!r} is not in {built_json}.")
        return 1
    if not reference:
        print(f"ERROR: the rendition {rendition!r} is not in {reference_json}.")
        return 1

    common = sorted(set(built) & set(reference), key=lambda k: tuple(
        "" if v is None else v for v in k))
    if not common:
        print(f"ERROR: {rendition!r} has no rendition in common between "
              f"the built car and the reference car.")
        return 1

    for key in common:
        name, idiom, scale, width, height = key
        b = sorted(built[key], key=lambda e: e.get("SHA1Digest") or "")
        r = sorted(reference[key], key=lambda e: e.get("SHA1Digest") or "")
        where = f"{width}x{height} " if width and height else ""
        print(f"  {rendition!r} {name or '(unnamed)'} {where}{idiom}@{scale}x")
        if len(b) != len(r):
            print(f"  VERDICT: NOT the FTV artwork "
                  f"(the built car holds {len(b)} rendition(s), "
                  f"the reference {len(r)})")
            return 1
        for be, re_ in zip(b, r):
            print(f"    {be.get('Encoding')} sha1 {be.get('SHA1Digest')}")
            if be.get("SHA1Digest") != re_.get("SHA1Digest"):
                print(f"  VERDICT: NOT the FTV artwork "
                      f"(built digest {be.get('SHA1Digest')}, "
                      f"reference digest {re_.get('SHA1Digest')})")
                return 1
    print(f"  {len(common)} rendition group(s) identical to the reference")
    print("  VERDICT: FTV artwork")
    return 0


def main():
    args = sys.argv[1:]
    if args and args[0] == "--png-dir":
        if len(args) != 3:
            print(__doc__)
            return 2
        directory, reference = args[1], args[2]
        if not os.path.isdir(directory):
            print(f"ERROR: {directory} is not a directory.")
            return 1
        candidates = dir_pngs(directory)
        if not candidates:
            print(f"ERROR: no PNGs found in {directory}.")
            return 1
        print(f"bundle:    {directory}")
        return compare(reference, candidates)

    if args and args[0] == "--car-digest":
        if len(args) != 4:
            print(__doc__)
            return 2
        return car_digest(args[1], args[2], args[3])

    if len(args) < 2 or len(args) % 2 != 0:
        print(__doc__)
        return 2

    exit_code = 0
    for i in range(0, len(args), 2):
        reference = args[i]
        bundle = args[i + 1]
        if not os.path.isdir(bundle):
            print(f"ERROR: {bundle} is not a directory.")
            return 1
        print(f"bundle:    {bundle}")
        renditions = bundle_renditions(bundle)
        if not renditions:
            print("  no icon renditions found in the bundle")
            print()
            exit_code = 1
            continue
        result = compare(reference, renditions)
        if result:
            exit_code = 1
        print()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

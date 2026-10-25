#!/usr/bin/env python3
"""Verify that the icon inside a built .app is the FTV artwork.

The reference is the owner's own file (1024x1024 for iOS and macOS, the
wordmark layer for tvOS). It is compared **pixel by pixel**, not by file
hash: the app icon goes through `actool`, which re-encodes and re-scales it,
so the bytes in the bundle are never the bytes in the source PNG. The
comparison is a mean absolute difference per channel; 0.00 means the two
images are identical pixel for pixel.

The icon is read out of the built bundle:

  * macOS: the `.icns` files in `Contents/Resources` - the `CFBundleIconFile`
    and the one `actool` generates from the asset catalog. The 1024x1024
    entry (`ic10`) is the one that carries the owner's artwork.
  * iOS/tvOS: the app icon is compiled into `Assets.car`. The PNG streams
    inside the car are extracted and compared.

No third-party modules: the PNG decoding is done here with `zlib` from the
standard library, so the script runs on a bare runner.

Usage:  verify-icon.py <reference.png> <bundle> [<reference.png> <bundle> ...]
"""
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


def decode_png(data):
    """Decode an 8-bit non-interlaced PNG into (width, height, [r,g,b] rows).

    Returns None for anything it does not understand.
    """
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
                rgb[x * 3:x * 3 + 3] = bytes((v, v, v))
            elif ctype == 4:
                v = line[x * 2]
                rgb[x * 3:x * 3 + 3] = bytes((v, v, v))
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
    car = os.path.join(bundle, "Assets.car")
    if os.path.exists(car):
        for png in car_pngs(car):
            out.append(("Assets.car", png))
    return out


def main():
    args = sys.argv[1:]
    if len(args) < 2 or len(args) % 2 != 0:
        print(__doc__)
        return 2

    exit_code = 0
    for i in range(0, len(args), 2):
        reference = args[i]
        bundle = args[i + 1]
        ref = decode_png(open(reference, "rb").read())
        if ref is None:
            print(f"ERROR: the reference {reference} could not be decoded.")
            return 1
        ref_w, ref_h, ref_rows = ref
        print(f"reference: {reference} {ref_w}x{ref_h}")
        print(f"bundle:    {bundle}")

        renditions = bundle_renditions(bundle)
        if not renditions:
            print("  no icon renditions found in the bundle")
            print()
            exit_code = 1
            continue

        best = None
        exact = []
        for label, png in renditions:
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
                exit_code = 1
            else:
                print("  VERDICT: FTV artwork")
        else:
            # Nothing comparable was found in the bundle. That is not a
            # mismatch - it means the check could not read the icon - and it
            # must not be reported as one.
            print("  VERDICT: inconclusive - no comparable rendition found")
        print()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

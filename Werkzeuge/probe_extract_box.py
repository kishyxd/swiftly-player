#!/usr/bin/env python3
"""Move the preview box body out of the GeometryReader closure.

PROBE ONLY - not for main. The Swift type checker times out on the
GeometryReader closure in `previewBox` on a slow machine. This rewrites it so
the closure is a single call and the bindings live in a @ViewBuilder
function that takes a concrete CGSize.

usage: probe_extract_box.py <path to PlayerScreen.swift>
"""
import sys


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else "Sources/iOS/PlayerScreen.swift"
    s = open(path).read()

    marker = "    private var previewBox: some View {"
    if marker not in s:
        print("MARKER NOT FOUND")
        return 1
    i = s.index(marker)
    j = s.index("\n    }\n", i) + len("\n    }\n")

    new = '''    private var previewBox: some View {
        GeometryReader { g in
            previewBoxContent(in: g.size)
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }

    /// **The whole box, as its own function.** The solver gets one call here
    /// instead of a closure full of bindings and a modifier chain, which is
    /// what it could not finish.
    @ViewBuilder
    private func previewBoxContent(in size: CGSize) -> some View {
        let image: CGImage? = preview(position)
        let width: CGFloat = pad ? 200 : 160
        let height: CGFloat = width * 9 / 16
        let share: Double = duration > 0 ? min(max(position / duration, 0), 1) : 0
        let name: String = ChapterBar.chapter(at: position, in: chapter)?.name ?? ""
        let half: CGFloat = image != nil ? width / 2 : max(name.isEmpty ? 40 : boxWidth / 2, 40)
        let x: CGFloat = min(max(size.width * share, half), max(size.width - half, half))
        previewContent(image: image, name: name, width: width, height: height)
            .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { boxWidth = $0 }
            .frame(maxWidth: width)
            .fixedSize(horizontal: false, vertical: true)
            .position(x: x, y: -((image == nil ? 0 : height + 6) + font + 6) / 2 - 2)
    }
'''

    open(path, "w").write(s[:i] + new + s[j:])
    print("patched", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

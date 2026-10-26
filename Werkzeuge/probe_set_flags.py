#!/usr/bin/env python3
"""Set OTHER_SWIFT_FLAGS for the Swiftly-iOS target in project.yml.

PROBE ONLY. usage: probe_set_flags.py <flags string>
"""
import re
import sys

P = "/home/ai/projects/swiftly-src/project.yml"

FLAGS = sys.argv[1] if len(sys.argv) > 1 else ""

s = open(P, encoding="utf-8").read()

# the line inside the Swiftly-iOS target's settings block
new_line = f'        OTHER_SWIFT_FLAGS: "{FLAGS}"'

if "OTHER_SWIFT_FLAGS" in s:
    s = re.sub(r'^        OTHER_SWIFT_FLAGS: ".*"$', new_line, s, count=1, flags=re.M)
else:
    # insert it right after the iOS entitlements line
    anchor = "        CODE_SIGN_ENTITLEMENTS: Sources/iOS/Swiftly.entitlements"
    s = s.replace(anchor, anchor + "\n" + new_line, 1)

open(P, "w", encoding="utf-8").write(s)
print("set OTHER_SWIFT_FLAGS:", FLAGS[:160])

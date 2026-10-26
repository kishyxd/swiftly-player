#!/usr/bin/env python3
"""
!! THIS ROUTE DOES NOT WORK. DO NOT USE IT TO UPLOAD A BUILD. !!

Kept only as a record of what was tried, and because the attribute names
and the four-resource shape are the only reference I have for the ASC
buildUploads API. The failure is silent and looks like success:

  * POST /v1/buildUploads           -> 201, a slot
  * POST /v1/buildUploadFiles      -> 201, the presigned multipart urls
  * PUT  each part                 -> 200 for every part, ETags match
  * PATCH /v1/buildUploadFiles/{id} -> 200 with an EMPTY attributes object,
                                       409 for anything else:
          "The attribute 'uploadOperations' can not be included in a
           'UPDATE' operation"

...and then the file sits in "AWAITING_UPLOAD" FOREVER. No build is ever
created. It does not time out and it does not error - it just never
happens. Do not spend time on it again.

USE altool INSTEAD, on a macOS runner:
  xcrun altool --upload-app --file <the.ipa> --type ios \
    -u "$APPLE_ID" -p "$APPLE_APP_SPEC_PW" --team-id "$APPLE_TEAM_ID"
It takes about 5 minutes for the build to appear in GET /v1/builds.

The working upload lives in .github/workflows/upload-ftvplayer-ipa.yml.
"""
import json
import os
import plistlib
import sys
import time
import zipfile

import jwt
import requests

KEY_PATH = os.environ.get("ASC_KEY_PATH", "/home/ai/.hermes/keys/asc/AuthKey_FTM4X3K3KV.p8")
KEY_ID = os.environ.get("ASC_KEY_ID", "FTM4X3K3KV")
ISSUER = os.environ.get("ASC_ISSUER_ID", "30a0ff0f-7a4f-4350-891e-af8defc453c7")
B = "https://api.appstoreconnect.apple.com"

_raw = open(KEY_PATH, "rb").read()


def token():
    now = int(time.time())
    return jwt.encode(
        {"iss": ISSUER, "iat": now, "exp": now + 1200, "aud": "appstoreconnect-v1"},
        _raw, algorithm="ES256", headers={"kid": KEY_ID, "typ": "JWT"},
    )


def api(method, path, **kw):
    """Every call retries: Apple returns 401 sporadically for a valid key."""
    last = None
    headers = dict(kw.pop("headers", None) or {})
    for attempt in range(8):
        try:
            hh = dict(headers)
            hh["Authorization"] = f"Bearer {token()}"
            timeout = kw.get("timeout", 120)
            r = requests.request(method, B + path, headers=hh, timeout=timeout, **kw)
            if r.status_code == 401:
                time.sleep(2 + attempt * 2)
                continue
            return r
        except Exception as e:  # network flake
            last = e
            time.sleep(2 + attempt * 2)
    raise last if last else RuntimeError(f"{method} {path} never came back")


def get(path, **kw):
    return api("GET", path, **kw)


def post(path, payload, **kw):
    return api("POST", path, json=payload, headers={"Content-Type": "application/json"}, **kw)


def patch(path, payload, **kw):
    return api("PATCH", path, json=payload, headers={"Content-Type": "application/json"}, **kw)


def read_ipa(ipa):
    """The version and the build number come out of the ipa itself.
    The Info.plist inside a built .app is a BINARY plist, so a regex finds
    nothing and silently falls back - parse it properly."""
    zf = zipfile.ZipFile(ipa)
    plist_name = next(n for n in zf.namelist() if n.endswith(".app/Info.plist"))
    with zf.open(plist_name) as fh:
        plist = plistlib.load(fh)
    return plist


def main():
    ipa = sys.argv[1]
    app_id = sys.argv[2] if len(sys.argv) > 2 else "6827263915"
    size = os.path.getsize(ipa)
    with open(ipa, "rb") as f:
        data = f.read()
    print(f"the ipa: {ipa}  {size} bytes")

    plist = read_ipa(ipa)
    version = plist.get("CFBundleShortVersionString", "1.0.0")
    build_number = str(plist.get("CFBundleVersion", "1"))
    print(f"the version: {version} ({build_number})")
    print(f"  bundle:  {plist.get('CFBundleIdentifier')}")
    print(f"  display: {plist.get('CFBundleDisplayName')}")

    # 1) the slot
    r = post("/v1/buildUploads", {
        "data": {
            "type": "buildUploads",
            "attributes": {
                "cfBundleShortVersionString": version,
                "cfBundleVersion": build_number,
                "platform": "IOS",
            },
            "relationships": {"app": {"data": {"type": "apps", "id": app_id}}},
        }
    })
    if r.status_code not in (200, 201):
        print("the build upload FAILED", r.status_code, r.text[:600])
        return 1
    upload_id = r.json()["data"]["id"]
    print(f"the build upload id: {upload_id}")

    # 2) the file, and with it the presigned urls
    r = post("/v1/buildUploadFiles", {
        "data": {
            "type": "buildUploadFiles",
            "attributes": {
                "fileName": os.path.basename(ipa),
                "fileSize": size,
                "uti": "com.apple.ipa",
                "assetType": "ASSET",
            },
            "relationships": {
                "buildUpload": {"data": {"type": "buildUploads", "id": upload_id}}
            },
        }
    })
    if r.status_code not in (200, 201):
        print("the build upload file FAILED", r.status_code, r.text[:600])
        return 1
    j = r.json()["data"]
    file_id = j["id"]
    ops = j["attributes"].get("uploadOperations") or []
    print(f"the file id: {file_id}  ({len(ops)} part(s))")
    if not ops:
        print("no upload operations came back")
        return 1

    # 3) the bytes
    for op in ops:
        off = op.get("offset", 0)
        length = op.get("length", size)
        chunk = data[off:off + length]
        headers = {h["name"]: h["value"] for h in (op.get("requestHeaders") or [])}
        rr = requests.request(op.get("method", "PUT"), op["url"],
                              data=chunk, headers=headers, timeout=600)
        print(f"  part {op.get('partNumber','?')} offset={off} len={length}: {rr.status_code}")
        if rr.status_code not in (200, 201, 204):
            print("   FAILED", rr.status_code, rr.text[:400])
            return 1

    # 4) the confirmation.
    # Only 'uploadOperations' (and the delivery state) may be sent in an
    # UPDATE. Sending the create-time attributes back gets:
    #   "The attribute 'fileName' can not be included in a 'UPDATE' operation"
    # so the payload is reduced on a 409 and retried.
    def confirm(attributes):
        return patch(f"/v1/buildUploadFiles/{file_id}", {
            "data": {
                "type": "buildUploadFiles",
                "id": file_id,
                "attributes": attributes,
                "relationships": {
                    "buildUpload": {"data": {"type": "buildUploads", "id": upload_id}}
                },
            }
        })

    r2 = confirm({"uploadOperations": ops})
    if r2.status_code == 409:
        # fall back to the minimal form
        r2 = confirm({"uploadOperations": ops,
                      "assetDeliveryState": {"UPLOAD_COMPLETE": True}})
    if r2.status_code not in (200, 201):
        print("the confirmation FAILED", r2.status_code, r2.text[:800])
        return 1
    print("the upload was accepted. Apple is processing the build now.")

    # wait for it to come up
    for i in range(40):
        time.sleep(15)
        rb = get("/v1/builds", params={"filter[app]": app_id, "limit": 10})
        for b in rb.json().get("data", []):
            a = b["attributes"]
            print(f"  build {a.get('version')} ({a.get('buildNumber')}) id={b['id']} "
                  f"state={a.get('processingState')} expired={a.get('expired')}")
            if a.get("processingState") == "VALID":
                print("  the build is VALID")
                print(f"BUILD_ID={b['id']}")
                return 0
    print("the build did not become VALID in time")
    return 1


if __name__ == "__main__":
    sys.exit(main())

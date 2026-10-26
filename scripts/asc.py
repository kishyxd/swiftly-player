#!/usr/bin/env python3
"""
App Store Connect helper for the FTV app.

Uses the App Store Connect API key (ES256 JWT) instead of the fastlane /
portal session login, which Apple keeps rejecting.

Key lives at: /home/ai/.hermes/keys/asc/AuthKey_FTM4X3K3KV.p8
GitHub secrets: ASC_KEY_P8 (base64), ASC_KEY_ID, ASC_ISSUER_ID
"""
import base64
import os
import time

import jwt
import requests

KEY_PATH = "/home/ai/.hermes/keys/asc/AuthKey_FTM4X3K3KV.p8"
KEY_ID = "FTM4X3K3KV"
ISSUER_ID = "30a0ff0f-7a4f-4350-891e-af8defc453c7"
BASE = "https://api.appstoreconnect.apple.com"
APP_ID = "6823967654"          # FTV (com.kxvn.plezy)
FTVPLAYER_BUNDLE = "XS2GY3CGTU"  # com.kxvn.ftvplayer


def _raw_key():
    if os.environ.get("ASC_KEY_P8"):
        return base64.b64decode(os.environ["ASC_KEY_P8"])
    with open(KEY_PATH, "rb") as fh:
        return fh.read()


def token(raw=None, kid=None, issuer=None):
    raw = raw if raw is not None else _raw_key()
    now = int(time.time())
    return jwt.encode(
        {"iss": issuer or ISSUER_ID, "iat": now, "exp": now + 1200,
         "aud": "appstoreconnect-v1"},
        raw, algorithm="ES256",
        headers={"kid": kid or KEY_ID, "typ": "JWT"})


def session():
    """Return (headers, raw_key) with a fresh bearer token."""
    raw = _raw_key()
    return {"Authorization": f"Bearer {token(raw)}"}, raw


def call(method, path, raw=None, kid=None, issuer=None, **kw):
    """Make an ASC API call, refreshing the token once on a 401."""
    raw = raw if raw is not None else _raw_key()
    r = None
    for attempt in range(5):
        headers = {"Authorization": f"Bearer {token(raw, kid, issuer)}"}
        if method == "GET":
            r = requests.get(BASE + path, headers=headers, timeout=60, **kw)
        elif method == "POST":
            headers["Content-Type"] = "application/json"
            r = requests.post(BASE + path, headers=headers, timeout=60, **kw)
        elif method == "PATCH":
            headers["Content-Type"] = "application/json"
            r = requests.patch(BASE + path, headers=headers, timeout=60, **kw)
        elif method == "DELETE":
            headers["Content-Type"] = "application/json"
            r = requests.delete(BASE + path, headers=headers, timeout=60, **kw)
        else:
            raise ValueError(method)
        if r.status_code not in (401, 403):
            return r
        time.sleep(3 + attempt * 3)
    raise RuntimeError(f"{method} {path} failed after 5 attempts: {r}")


def builds(app=APP_ID, expired=None):
    """All builds for an app. expired=True/False filters."""
    params = {"filter[app]": app, "limit": 200}
    if expired is not None:
        params["filter[expired]"] = "true" if expired else "false"
    r = call("GET", "/v1/builds", params=params)
    r.raise_for_status()
    return r.json()["data"]


def beta_groups(app=APP_ID):
    r = call("GET", "/v1/betaGroups", params={"filter[app]": app, "limit": 50})
    r.raise_for_status()
    return r.json()["data"]


def group_builds(group_id):
    r = call("GET", f"/v1/betaGroups/{group_id}/relationships/builds")
    r.raise_for_status()
    return [b["id"] for b in r.json().get("data", [])]


def expire_build(build_id):
    r = call("PATCH", f"/v1/builds/{build_id}",
             json={"data": {"type": "builds", "id": build_id,
                            "attributes": {"expired": True}}})
    return r.status_code in (200, 204)


def remove_builds_from_group(group_id, build_ids):
    r = call("DELETE", f"/v1/betaGroups/{group_id}/relationships/builds",
             json={"data": [{"type": "builds", "id": b} for b in build_ids]})
    return r.status_code in (200, 204)


def enforce_one_build(keep_builds=("1167", "157"), app=APP_ID):
    """Expire every build except the keep list, and drop expired builds
    from the beta groups. Returns (expired_ok, expired_failed)."""
    keep = {str(b) for b in keep_builds}
    all_builds = builds(app)
    expired_ids = []
    ok = bad = 0
    for b in all_builds:
        ver = b["attributes"]["version"]
        if ver in keep:
            print(f"KEEP {ver}")
            continue
        expired_ids.append(b["id"])
        if b["attributes"]["expired"]:
            print(f"ALREADY_EXPIRED {ver}")
            continue
        if expire_build(b["id"]):
            print(f"EXPIRED {ver}")
            ok += 1
        else:
            print(f"EXPIRE_FAIL {ver}")
            bad += 1
        time.sleep(1)
    for g in beta_groups(app):
        gid = g["id"]
        current = set(group_builds(gid))
        drop = [b for b in expired_ids if b in current]
        if drop:
            remove_builds_from_group(gid, drop)
            print(f"GROUP {g['attributes']['name']} dropped {len(drop)}")
            time.sleep(1)
    return ok, bad


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "enforce":
        keep = sys.argv[2].split(",") if len(sys.argv) > 2 else ["1167", "157"]
        print(enforce_one_build(keep))
    else:
        for b in builds():
            a = b["attributes"]
            print(f"{a['version']:<8} expired={a['expired']} {a['processingState']} {b['id']}")

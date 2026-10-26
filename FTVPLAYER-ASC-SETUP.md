# FTV Player (Swiftly) — App Store Connect setup state

**Created 2026-10-26.** Everything below was created with the App Store Connect
API key (ES256 JWT), not the fastlane/portal session login.

## App identity

| Thing | ID | Value |
|---|---|---|
| iOS bundle id | `XS2GY3CGTU` | `com.kxvn.ftvplayer` |
| tvOS extension bundle id | `66R554A9PW` | `com.kxvn.ftvplayer.topshelf` |
| iOS store profile | `92T837MH8Q` | `KXVN Store FTV Player` |
| tvOS store profile | `NN7YMKB22P` | `KXVN Store FTV Player Top Shelf` |
| distribution cert | `8B37H5226V` | `Apple Distribution: Kishan Manbahal` |

Both profiles: `IOS_APP_STORE`, `ACTIVE`, expire **2027-10-17**, no
`ProvisionedDevices` (store profiles install via TestFlight only).

Profile files on the VPS:
- `/home/ai/projects/udid-capture/signing/kxvn_store_ftvplayer.mobileprovision`
  → `application-identifier = 6VS7BF6R33.com.kxvn.ftvplayer`
- `/home/ai/projects/udid-capture/signing/kxvn_store_ftvplayer_topshelf.mobileprovision`
  → `application-identifier = 6VS7BF6R33.com.kxvn.ftvplayer.topshelf`

## The ONE thing left: the app record

`POST /v1/apps` is **not allowed** by the public API — the `apps` resource
only permits `GET_COLLECTION, GET_INSTANCE, UPDATE`. Same for
`preReleaseVersions` (GET only). Creating a betaGroup or appStoreVersion
against a bundle id instead of an app id → 409 `app has an invalid id format`.

**So the app record must be created by hand in App Store Connect:**
My Apps → ➕ → New App → name `FTV Player` → bundle id `com.kxvn.ftvplayer`
→ SKU `ftvplayer` → primary language English → access: full access.

After that the whole rest is scriptable with the key.

## The build (verified working 2026-10-26)

`.github/workflows/build-ftvplayer-ios.yml` builds the app on a `macos-15`
runner. Four things it has to get right, each learned the hard way:

1. **Xcode 26.3, not the runner's default 16.4.** The project uses Swift 6.2
   features (`@MainActor` on a protocol conformance) and 16.4's compiler
   rejects them with ~2000 errors that are all the same root cause. Xcode 26
   is installed alongside the default; the workflow picks the newest 26.x.
2. **The constraint solver needs four budgets raised, on the app target
   only.** `OTHER_SWIFT_FLAGS` in the `Swiftly-iOS` target's `settings.base`:
   ```
   $(inherited) -Xfrontend -solver-scope-threshold=2147483647 \
   -Xfrontend -solver-trail-threshold=2147483647 \
   -Xfrontend -solver-expression-time-threshold=2147483647 \
   -solver-memory-threshold 2147483647
   ```
   Without them the build fails with 87 "unable to type-check this expression
   in reasonable time" errors; with scope+trail alone, 6; with all four, 0 and
   BUILD SUCCEEDED. The thresholds are 32-bit — a larger value gives a DRIVER
   error and a misleading zero-error count. `-solver-memory-threshold` takes
   a SPACE and cannot go through `-Xfrontend`.
3. **MANUAL signing with the distribution certificate.** Automatic signing
   with the ASC API key produces an "Apple Development: Created via API"
   identity and a DEVELOPMENT profile, which App Store Connect rejects. The
   workflow imports the distribution p12 into a temporary keychain and uses
   `CODE_SIGN_STYLE=Manual` + `PROVISIONING_PROFILE_SPECIFIER="KXVN Store
   FTV Player"`.
4. **No `xcodebuild -exportArchive`** — it needs an account session and
   fails with `error: exportArchive Failed to Use Accounts`. The archive is
   already signed, so the .ipa is zipped from it directly (root must be
   `Payload/`).

Secrets used: `ASC_DIST_P12_B64`, `ASC_DIST_P12_PASSWORD`,
`ASC_PROFILE_FTVPLAYER_B64`, plus the existing `ASC_KEY_P8`, `ASC_KEY_ID`,
`ASC_ISSUER_ID`, `APPLE_ID`, `APPLE_APP_SPEC_PW`, `APPLE_TEAM_ID`.

The p12 was regenerated from the local `distribution_private.key` +
`apple_distribution.pem` with a known password, because the original
password was not recoverable. The cert is unchanged:
`CN=Apple Distribution: Kishan Manbahal (6VS7BF6R33)`, expires 2027-10-17.

## Build prerequisites for the iOS target

`project.yml` is already set up for this app:
- `bundleIdPrefix: com.kxvn`
- iOS + macOS + tvOS `PRODUCT_BUNDLE_IDENTIFIER: com.kxvn.ftvplayer`
- tvOS extension `com.kxvn.ftvplayer.topshelf`
- `CFBundleDisplayName: FTV Player`, `CFBundleName: FTV Player`
- `SWIFT_ACTIVE_COMPILATION_CONDITIONS: $(inherited) FTV_EDITION` — the flag
  that makes the app boot straight into `ftv.kxvn.io` with
  `request.kxvn.io` pre-filled
- `MARKETING_VERSION: "1.0.9"`, `CURRENT_PROJECT_VERSION: "30"`

### Two things to fix before building
1. **`DEVELOPMENT_TEAM: 63L6TSM2Y9`** in `project.yml:42` is the UPSTREAM
   (paulherter) team. It must be `6VS7BF6R33` (Kishan's paid team) or the
   signing uses the wrong certificate and the profile won't match.
2. **Build number** must exceed every build already in ASC. This is a NEW
   app record so it starts at 1 — but `CURRENT_PROJECT_VERSION` is currently
   `30`, which is fine (must be > 0 and unique per version).

### Vendor/VLCKit.xcframework — 2.7 GB, not in git
`Werkzeuge/vlckit-fetch.sh` pulls the official VideoLAN build (861 MB zip).
Measured 2026-10-26: **44 MB/s** from this VPS, so the download is ~20 s.
The project links `Vendor/VLCKit-gepatcht.xcframework` (the patched build);
`Werkzeuge/vlckit-build/build.sh` + `merge-xcframework.sh` rebuild it from
source with the patches in `Werkzeuge/vlckit-patches/`. Building the patched
framework is a long macOS job (clone VLCKit, apply patches, build 3 platform
slices) — hours, not minutes.

**Fastest path for a first TestFlight build:** use the UNPATCHED official
`VLCKit.xcframework` and point the framework reference at it. The trade is
known MKV-over-HTTP seeking (seeks read from the start of the file, 30-90 s
stalls) — unacceptable for long-form media, fine for a first signed build
that proves the pipeline.

## CI shape that has to exist

There is NO iOS build workflow in this repo. `check.yml` only validates the
project (it explicitly does not build — the 2.7 GB framework makes a full
build too expensive per push). A real iOS build needs:

1. `runs-on: macos-15` (or macos-14) — Xcode + xcodegen
2. fetch or build `Vendor/VLCKit*.xcframework`
3. `xcodegen generate`
4. `xcodebuild -scheme Swiftly-iOS -destination 'generic/platform=iOS' build`
   with `DEVELOPMENT_TEAM=6VS7BF6R33` and automatic signing against the
   `com.kxvn.ftvplayer` profile
5. export an .ipa, upload to the FTV Player app record

The existing `upload-testflight.yml` uploads a PRE-BUILT ipa from a GitHub
release asset — it does not build. It points at `ftv-restore-1169.ipa`
(bundle `com.kxvn.plezy`), which is the PLEZY-based FTV app, not Swiftly.

## Naming collision warning

The `FTV` display name and fish icon are SPENT — they belong to the
existing FTV (Plezy-based) client that is already on TestFlight as
`com.kxvn.plezy` / "FTV". This Swiftly-based build uses the name
**"FTV Player"**, which is a different string. Two apps named "FTV" and
"FTV Player" side by side on a home screen reads as a bug, and Apple
guideline 5.2.5 has already bitten this project once (a build was rejected
over "Mac" in a display name). Decide explicitly:
- **SUPERSEDE** the Plezy-based FTV with this one, or
- give this one a distinct name/icon.

## Sources
- `scripts/asc.py` — the API helper (token mint, builds, groups, expire, enforce)
- `.github/workflows/asc-enforce-one-build.yml` — daily one-build enforcement
- `Werkzeuge/vlckit-fetch.sh`, `Werkzeuge/vlckit-build/` — the framework
- `Documentation/Building.md` — upstream's build instructions

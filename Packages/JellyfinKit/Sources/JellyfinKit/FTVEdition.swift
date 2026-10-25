import Foundation

/// **The FTV edition's fixed configuration.**
///
/// Everything the owner wants every installation to start with, in one place: the
/// server the app signs in to, the Seerr instance it asks for titles from, and the
/// settings every new install begins with.
///
/// **Why a configuration and not a constant per screen.** The FTV edition is not
/// "Swiftly with a different logo": it is one app that belongs to one server. The
/// server, the Seerr instance and the starting settings are the same for everybody
/// who installs it, so they belong together and are written down once. A screen that
/// asks for the Seerr address and the code that stores the starting settings read
/// the same values from here, so the two can never drift apart.
///
/// **The values are the ones the FTV Plezy build uses** (`--dart-define=FTV_SERVER`
/// and `--dart-define=FTV_SEERR_URL` in its workflow): the media server
/// `ftv.kxvn.io` and the request instance `request.kxvn.io`.
///
/// ## How the build decides whether this applies
///
/// `isEnabled` is true when the app was built as the FTV edition. It is set by the
/// build flag `FTV_EDITION`, which the Apple and desktop workflows pass; an upstream
/// build without that flag keeps the old behaviour (ask for a server, ask for a Seerr
/// address, keep the upstream defaults).
///
/// The Android app has its own equivalent, `BuildConfig.FTV_MODE`, because it is a
/// separate code base (Kotlin, not Swift). Both are set from the same place in the
/// build, so the two agree.
public enum FTVEdition {

    /// Whether this build is the FTV edition.
    ///
    /// **A compile-time flag, not a runtime setting.** A user cannot turn the FTV
    /// edition off, and the FTV edition cannot be built without it: the whole point
    /// is that it always points at the owner's server.
    public static var isEnabled: Bool {
        #if FTV_EDITION
        return true
        #else
        return false
        #endif
    }

    /// The one media server this app signs in to.
    ///
    /// Empty in a non-FTV build: there is no preset then, the app asks.
    public static var serverURL: String {
        #if FTV_EDITION
        return "https://ftv.kxvn.io"
        #else
        return ""
        #endif
    }

    /// The one request instance this app asks for titles from.
    ///
    /// Pre-filled in the Seerr settings so a new user only has to sign in; it stays
    /// editable, because somebody who runs their own Seerr must be able to point the
    /// app at it.
    public static var seerrURL: String {
        #if FTV_EDITION
        return "https://request.kxvn.io"
        #else
        return ""
        #endif
    }

    // MARK: - The settings a new install starts with

    /// **Direct Play forced on.** The server is the owner's own, so there is no
    /// reason to transcode: the original file plays as it is.
    public static var alwaysDirectPlay: Bool { true }

    /// **No bitrate limit.** The same reason: nothing is transcoded, so nothing has
    /// to be cut down either.
    public static var bitratesLimit: Int { 0 }

    /// **Progress on the tiles.** A show that is half watched should look half
    /// watched in the grid, not only in the detail page.
    public static var progressOnTiles: Bool { true }

    /// **Ten seconds back, thirty seconds forward.** The upstream values; they are
    /// written down here so the whole starting configuration stands in one list.
    public static var backSeconds: Int { 10 }
    public static var forwardSeconds: Int { 30 }

    /// **The accent colour the FTV edition starts with.**
    ///
    /// Upstream starts on turquoise (`Look.original`). The FTV mark is violet, and
    /// the whole app is FTV's, so it starts on violet: the accent is what the eye
    /// reads as "this app", and on a fresh install it should be the FTV colour.
    ///
    /// A user can still pick another accent; this is only what a new install begins
    /// with.
    public static var accentID: String? {
        #if FTV_EDITION
        return "violet"
        #else
        return nil
        #endif
    }
}

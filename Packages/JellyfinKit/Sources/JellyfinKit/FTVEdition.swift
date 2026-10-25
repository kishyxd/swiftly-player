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
/// The **values** live here, in the package, so that every platform reads the same
/// ones. The **decision** to use them is made in the app layer, because only the app
/// target knows its own build flags: `FTV_EDITION` for the Swift builds (set in
/// `project.yml` and in the Linux and Windows `Package.swift`), `BuildConfig.FTV_MODE`
/// for Android (which already had it).
///
/// **The package cannot hold the flag itself.** A Swift package target compiles with
/// its own settings and does not inherit the app target's compilation conditions, so
/// a `#if` written in this file would be false on every platform - the whole
/// configuration would have been dead code. That is why the flag is read where it is
/// set, and the values are read from here.
public enum FTVEdition {

    /// Whether this build is the FTV edition.
    ///
    /// **The package cannot answer this.** A Swift package target compiles with its
    /// own settings and does not inherit the app target's compilation conditions,
    /// so a flag set for the app never reaches here. The app layer therefore
    /// decides for itself - it knows its own build flags - and this file holds only
    /// the values.
    ///
    /// **The values are here and not in the app, so that they cannot differ per
    /// platform.** One list, read by every platform, is the whole point of this
    /// file; a second copy in the Kotlin app would drift from it.
    public static var serverURL: String { "https://ftv.kxvn.io" }

    /// The one request instance this app asks for titles from.
    ///
    /// Pre-filled in the Seerr settings so a new user only has to sign in; it stays
    /// editable, because somebody who runs their own Seerr must be able to point the
    /// app at it.
    public static var seerrURL: String { "https://request.kxvn.io" }

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
    public static var accentID: String? { "violet" }
}

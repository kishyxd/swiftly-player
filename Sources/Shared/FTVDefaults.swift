import Foundation
import JellyfinKit

/// **The FTV edition's starting settings, written into the store on the first launch.**
///
/// The settings of the app live in `UserDefaults` under the same keys on every
/// Apple platform (`immerDirectPlay`, `fortschritt`, ...). Upstream reads each of
/// them with a default: `store.object(forKey: "immerDirectPlay") as? Bool ?? true`.
/// That default is what an install that never touched the setting gets.
///
/// The FTV edition wants a different starting point for some of them, and it wants
/// it **the same for every install**. Writing the values into the store on the first
/// launch does that: the store is the single place the app reads, so afterwards the
/// user can change any of them like any other setting, and what they change is kept.
///
/// **Why not simply change the default in the reading code?** Because the default
/// is read at the moment a setting is used, and it is written in more than twenty
/// places across the platforms. A list that is written down once and applied once
/// is one place to look, and it cannot be half-applied on one platform.
///
/// **Only on a fresh install.** The marker key says "the FTV defaults have already
/// been written"; without it the values would be written again on every launch and
/// would undo what the user changed. An install that already has settings keeps
/// them: the FTV defaults are a starting point, not a cage.
///
/// The values themselves are in `FTVEdition` (the package), so the same list serves
/// the Apple, Linux and Windows builds.
enum FTVDefaults {

    /// The marker: the FTV starting settings have been written.
    ///
    /// A name of its own, so it cannot collide with a setting key.
    private static let appliedKey = "ftv.startingSettings.written"

    /// The version of the FTV starting settings.
    ///
    /// **The first version is not the last.** The forward skip was thirty seconds
    /// and is now ten; the home page gained the "Collections" row and the genres.
    /// An install that already has the settings of the first version gets the
    /// changes - but only where it has not made a choice of its own.
    private static let versionKey = "ftv.startingSettings.version"

    /// The current version of the FTV starting settings.
    private static let currentVersion = 2

    /// Writes the FTV starting settings, once, on the first launch.
    ///
    /// Does nothing outside an FTV build, and nothing on an install that has already
    /// been through here.
    static func applyOnFirstLaunch(_ store: UserDefaults = .standard) {
        // **The FTV edition decides for itself.** The flag is set for this app
        // target (project.yml), which is where it can be read; the package that
        // holds the values does not see it.
        #if FTV_EDITION
        let version = store.integer(forKey: versionKey)
        guard version < currentVersion else { return }

        // **A fresh install gets the whole list; an install that already has the
        // first version gets only what changed** - and only where the value is
        // still the one FTV wrote.
        let fresh = store.object(forKey: appliedKey) == nil
        if fresh {
            // **Only the keys the user has never set.** A setting that is already
            // in the store belongs to the user, whatever the FTV defaults say.
            if store.object(forKey: "immerDirectPlay") == nil {
                store.set(FTVEdition.alwaysDirectPlay, forKey: "immerDirectPlay")
            }
            if store.object(forKey: "bitratenGrenze") == nil {
                store.set(FTVEdition.bitratesLimit, forKey: "bitratenGrenze")
            }
            if store.object(forKey: "fortschritt") == nil {
                store.set(FTVEdition.progressOnTiles, forKey: "fortschritt")
            }
            if store.object(forKey: "zurueckSek") == nil {
                store.set(FTVEdition.backSeconds, forKey: "zurueckSek")
            }
        }

        // **The forward skip was thirty seconds and is now ten.**
        //
        // On a fresh install it is simply written where the user has nothing;
        // on an install that already carries the FTV settings it is only
        // changed where it still is the thirty seconds FTV wrote - a user who
        // set another value keeps it.
        if fresh {
            if store.object(forKey: "vorSek") == nil {
                store.set(FTVEdition.forwardSeconds, forKey: "vorSek")
            }
        } else if (store.object(forKey: "vorSek") as? Int) == 30 {
            store.set(FTVEdition.forwardSeconds, forKey: "vorSek")
        }

        // **The genres of the home page**, as chips above the rows. Both are new
        // keys, so an install that already has them keeps its own choice.
        if store.object(forKey: "startGenres") == nil {
            store.set(FTVEdition.startGenres, forKey: "startGenres")
        }
        if store.object(forKey: "genreChips") == nil {
            store.set(FTVEdition.genreChips, forKey: "genreChips")
        }

        // **The accent colour** is not a plain setting: it lives in the look
        // selection, which is stored as encoded data. It is only written when the
        // user has not picked anything yet, so a look they chose is kept.
        if let accentID = FTVEdition.accentID,
           store.data(forKey: LookStorageKey.selection) == nil {
            let selection = LookSelection(lookID: Look.original.id, accentID: accentID)
            if let data = selection.encoded {
                store.set(data, forKey: LookStorageKey.selection)
            }
        }

        store.set(true, forKey: appliedKey)
        store.set(currentVersion, forKey: versionKey)
        #endif
    }
}

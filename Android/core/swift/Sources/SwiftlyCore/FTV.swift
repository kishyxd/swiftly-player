import Foundation
import JellyfinKit

// MARK: - The FTV edition, the bridge for Kotlin
//
// **The values live in the package** (`FTVEdition`), so that every platform reads
// the same ones: the server, the Seerr instance, the home page and the skip
// lengths are written down once. Kotlin asks for them here instead of keeping a
// second list that could drift from the one the other platforms read.
//
// The answer is JSON, like every other answer across the bridge.

private struct FTVHomeJSON: Encodable {
    let server: String
    let seerr: String
    let genres: [String]
    let genreChips: Bool
    /// The library rows of the home page, in the package's own form
    /// (`StartLibrary`: `id`, `name`, `sammlung`).
    let collections: [StartLibrary]
    let backSeconds: Int
    let forwardSeconds: Int
}

extension Kern {

    /// **What the FTV edition starts with**, as the package holds it.
    ///
    /// Empty values are the upstream ones; this build decides whether it uses
    /// them (`BuildConfig.FTV_MODE` on Android).
    public static func ftvHomeDefaults() -> String {
        let json = FTVHomeJSON(server: FTVEdition.serverURL,
                               seerr: FTVEdition.seerrURL,
                               genres: FTVEdition.startGenres,
                               genreChips: FTVEdition.genreChips,
                               collections: FTVEdition.collectionsLibraries,
                               backSeconds: FTVEdition.backSeconds,
                               forwardSeconds: FTVEdition.forwardSeconds)
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        return (try? String(decoding: encoder.encode(json), as: UTF8.self)) ?? "{}"
    }
}

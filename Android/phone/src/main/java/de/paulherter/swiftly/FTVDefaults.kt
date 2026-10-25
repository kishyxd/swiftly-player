package de.paulherter.swiftly

/**
 * **The FTV edition's starting settings, written into the store on the first launch.**
 *
 * The settings live in the `swiftly` SharedPreferences under the same keys the other
 * platforms use (`immerDirectPlay`, `fortschritt`, ...). Upstream reads each of them
 * with a default: `bool("immerDirectPlay", true)` — the guideline is what an install
 * that never touched the setting gets.
 *
 * The FTV edition wants a different starting point for some of them, and it wants it
 * **the same for every install**. Writing the values into the store on the first
 * launch does that: the store is the single place the app reads, so afterwards the
 * user can change any of them like any other setting, and what they change is kept.
 *
 * **Only on a fresh install.** The marker key says "the FTV defaults have already
 * been written"; without it the values would be written again on every launch and
 * would undo what the user changed. An install that already has settings keeps them:
 * the FTV defaults are a starting point, not a cage.
 *
 * **The same list as the other platforms** (`FTVEdition` in the Swift package): the
 * values are the ones the FTV Plezy build uses.
 */
internal object FTVDefaults {

    /** The marker: the FTV starting settings have been written. */
    private const val APPLIED_KEY = "ftv.startingSettings.written"

    /**
     * Writes the FTV starting settings, once, on the first launch.
     *
     * Does nothing outside an FTV build (`BuildConfig.FTV_MODE`), and nothing on an
     * install that has already been through here.
     */
    fun applyOnFirstLaunch(store: Store) {
        if (!BuildConfig.FTV_MODE) return
        if (store.rememberValue(APPLIED_KEY) != null) return

        // **Only the keys the user has never set.** A setting that is already in
        // the store belongs to the user, whatever the FTV defaults say.
        write(store, "immerDirectPlay", "1")   // Direct Play forced
        write(store, "fortschritt", "1")       // progress on the tiles
        write(store, "bitratenGrenze", "0")    // no bitrate limit
        write(store, "zurueckSek", "10")       // ten seconds back
        write(store, "vorSek", "30")           // thirty seconds forward

        store.remember(APPLIED_KEY, "1")
    }

    /** Writes a value only if the key is not in the store yet. */
    private fun write(store: Store, key: String, value: String) {
        if (store.rememberValue(key) == null) store.remember(key, value)
    }
}

package de.paulherter.swiftly

import de.paulherter.swiftly.core.Kern
import org.json.JSONObject

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
     * The version of the FTV starting settings.
     *
     * **The first version is not the last.** The forward skip was thirty seconds
     * and is now ten; the home page gained the "Collections" row and the genres.
     * An install that already has the settings of the first version gets the
     * changes - but only where it has not made a choice of its own.
     */
    private const val VERSION_KEY = "ftv.startingSettings.version"

    /** The current version of the FTV starting settings. */
    private const val CURRENT_VERSION = 2

    /**
     * **What the FTV edition starts with, as the package holds it.**
     *
     * The values live in `FTVEdition` in the Swift package and travel across the
     * bridge (`Kern.ftvHomeDefaults`), so that every platform reads the same
     * ones: the server, the home page and the skip lengths are written down
     * once. A second list here would drift from it.
     */
    private val defaults: JSONObject by lazy {
        runCatching { JSONObject(Kern.ftvHomeDefaults()) }.getOrElse { JSONObject() }
    }

    /**
     * The FTV server's "Collections" library, as the first row of the home page.
     *
     * The ID is the server's own, in the form the API hands it out.
     */
    internal val FTV_COLLECTIONS: StartLibraryItem? by lazy {
        val c = defaults.optJSONArray("collections")?.optJSONObject(0) ?: return@lazy null
        val id = c.optString("id")
        if (id.isEmpty()) null else StartLibraryItem(id, c.optString("name"), c.optBoolean("sammlung", false))
    }

    /** The genres the home page starts with, in the order they are shown. */
    internal val FTV_HOME_GENRES: List<String> by lazy {
        val g = defaults.optJSONArray("genres")
        if (g == null) emptyList() else (0 until g.length()).map { g.optString(it) }
    }

    /** How far a step back and a step forward go, in seconds. */
    internal val FTV_BACK_SECONDS: Int by lazy { defaults.optInt("backSeconds", 10) }
    internal val FTV_FORWARD_SECONDS: Int by lazy { defaults.optInt("forwardSeconds", 10) }

    /**
     * Writes the FTV starting settings, once, on the first launch.
     *
     * Does nothing outside an FTV build (`BuildConfig.FTV_MODE`), and nothing on an
     * install that has already been through here.
     */
    fun applyOnFirstLaunch(store: Store) {
        if (!BuildConfig.FTV_MODE) return
        val version = store.rememberValue(VERSION_KEY)?.toIntOrNull() ?: 0
        if (version >= CURRENT_VERSION) return

        // **A fresh install gets the whole list; an install that already has the
        // first version gets only what changed** - and only where the value is
        // still the one FTV wrote.
        val fresh = store.rememberValue(APPLIED_KEY) == null
        if (fresh) {
            // **Only the keys the user has never set.** A setting that is already
            // in the store belongs to the user, whatever the FTV defaults say.
            write(store, "immerDirectPlay", "1")   // Direct Play forced
            write(store, "fortschritt", "1")       // progress on the tiles
            write(store, "bitratenGrenze", "0")    // no bitrate limit
            write(store, "zurueckSek", FTV_BACK_SECONDS.toString())     // ten seconds back
            write(store, "vorSek", FTV_FORWARD_SECONDS.toString())     // ten seconds forward
        } else if (store.rememberValue("vorSek") == "30") {
            // **The forward skip was thirty seconds and is now ten.** Only
            // where it still is the thirty seconds FTV wrote: a user who set
            // another value keeps it.
            store.remember("vorSek", FTV_FORWARD_SECONDS.toString())
        }

        // **The genres of the home page**, as chips above the rows. Both are new
        // keys, so an install that already has them keeps its own choice.
        if (store.rememberValue("startGenres") == null) {
            store.remember("startGenres", org.json.JSONArray(FTV_HOME_GENRES).toString())
        }
        if (store.rememberValue("genreChips") == null) store.remember("genreChips", "1")

        store.remember(APPLIED_KEY, "1")
        store.remember(VERSION_KEY, CURRENT_VERSION.toString())
    }

    /** Writes a value only if the key is not in the store yet. */
    private fun write(store: Store, key: String, value: String) {
        if (store.rememberValue(key) == null) store.remember(key, value)
    }
}

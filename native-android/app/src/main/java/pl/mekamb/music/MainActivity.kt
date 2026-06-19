package pl.mekamb.music

import android.app.Activity
import android.app.Dialog
import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.ColorDrawable
import android.graphics.drawable.GradientDrawable
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.text.InputType
import android.text.TextUtils
import android.util.LruCache
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.Window
import android.view.WindowInsets
import android.view.inputmethod.EditorInfo
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.HorizontalScrollView
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.File
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.security.MessageDigest
import java.util.Locale
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicInteger
import kotlin.math.roundToInt

class MainActivity : Activity() {
    private enum class MusicTab(val label: String) {
        Library("Library"),
        Albums("Albums"),
        Liked("Liked"),
        Settings("Settings")
    }

    private enum class SearchMode(val label: String) {
        Library("Library"),
        Torrent("Torrent"),
        Indexers("Indexers");

        val searchesRemoteSources: Boolean
            get() = this == Torrent || this == Indexers
    }

    private enum class RepeatMode(val label: String) {
        Off("Repeat Off"),
        All("Repeat All"),
        One("Repeat One");

        val isActive: Boolean
            get() = this != Off
    }

    private enum class TorrentSource(val raw: String, val importPath: String) {
        PirateBay("piratebay", "/imports/piratebay"),
        ThirteenThirtySevenX("1337x", "/imports/1337x"),
        Indexer("indexer", "/imports/indexer");

        companion object {
            fun from(raw: String?): TorrentSource {
                return entries.firstOrNull { it.raw == raw } ?: PirateBay
            }
        }
    }

    private data class ApiTrack(
        val id: String,
        val title: String,
        val artist: String?,
        val album: String?,
        val originalFilename: String?,
        val mediaType: String?,
        val durationSeconds: Double?,
        val sizeBytes: Long?,
        val createdAt: String?
    ) {
        val displayArtist: String get() = artist?.takeIf { it.isNotBlank()  } ?: "Unknown Artist"
        val displayAlbum: String get() = album?.takeIf { it.isNotBlank() } ?: "Unknown Album"
    }

    private data class Album(
        val id: String,
        val title: String,
        val artist: String,
        val tracks: List<ApiTrack>
    )

    private data class TorrentResult(
        val name: String,
        val torrentId: String,
        val source: TorrentSource,
        val infoHash: String?,
        val magnetLink: String?,
        val sourceUrl: String?,
        val seeders: String?,
        val leechers: String?,
        val sizeBytes: Long?,
        val sizeLabel: String?,
        val uploader: String?
    )

    private class ApiException(message: String) : Exception(message)

    private val executor = Executors.newSingleThreadExecutor()
    private val artworkExecutor = Executors.newFixedThreadPool(6)
    private val mainHandler = Handler(Looper.getMainLooper())
    private val progressTick = object : Runnable {
        override fun run() {
            updateMiniPlayer()
            mainHandler.postDelayed(this, 1000)
        }
    }

    private val bgTopColor = Color.rgb(9, 13, 24)
    private val bgColor = Color.rgb(4, 6, 12)
    private val surfaceColor = Color.rgb(16, 21, 32)
    private val elevatedColor = Color.rgb(25, 32, 47)
    private val chipColor = Color.rgb(34, 43, 61)
    private val strokeColor = Color.rgb(48, 60, 82)
    private val textColor = Color.rgb(248, 250, 252)
    private val mutedColor = Color.rgb(157, 168, 188)
    private val accentColor = Color.rgb(76, 217, 132)
    private val accentAltColor = Color.rgb(90, 169, 255)
    private val dangerColor = Color.rgb(244, 99, 99)

    private lateinit var root: LinearLayout
    private lateinit var searchHeader: LinearLayout
    private lateinit var searchModeBar: LinearLayout
    private lateinit var searchInput: EditText
    private lateinit var statusText: TextView
    private lateinit var tabBar: LinearLayout
    private lateinit var content: LinearLayout
    private lateinit var miniArtwork: FrameLayout
    private lateinit var miniTitle: TextView
    private lateinit var miniSubtitle: TextView
    private lateinit var miniProgress: ProgressBar
    private lateinit var playButton: TextView

    private var selectedTab = MusicTab.Library
    private var searchMode = SearchMode.Library
    private var shuffleEnabled = false
    private var repeatMode = RepeatMode.Off
    private var selectedAlbumId: String? = null
    private var isLoading = false
    private var statusMessage: String? = null

    private var tracks: List<ApiTrack> = emptyList()
    private var albums: List<Album> = emptyList()
    private var likedTrackIds: Set<String> = emptySet()
    private var torrents: List<TorrentResult> = emptyList()
    private val artworkCache = object : LruCache<String, Bitmap>(32 * 1024) {
        override fun sizeOf(key: String, value: Bitmap): Int = value.byteCount / 1024
    }
    private val missingArtworkIds = mutableSetOf<String>()
    private val requestedArtworkIds = mutableSetOf<String>()
    private val playbackRequestId = AtomicInteger(0)

    private var mediaPlayer: MediaPlayer? = null
    private var currentTrack: ApiTrack? = null
    private var playbackQueue: List<ApiTrack> = emptyList()
    private var currentIndex = -1
    private var isPlaying = false
    private var miniArtworkTrackId: String? = null

    private val prefs by lazy { getSharedPreferences("mekamb_music_android", Context.MODE_PRIVATE) }
    private val artworkDiskDir by lazy { File(cacheDir, "artwork/v1").apply { mkdirs() } }
    private var apiEndpoint: String
        get() = prefs.getString("api_endpoint", "") ?: ""
        set(value) = prefs.edit().putString("api_endpoint", value).apply()
    private var apiToken: String
        get() = prefs.getString("api_token", "") ?: ""
        set(value) = prefs.edit().putString("api_token", value).apply()
    private var prowlarrApiKey: String
        get() = prefs.getString("prowlarr_api_key", "") ?: ""
        set(value) = prefs.edit().putString("prowlarr_api_key", value).apply()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = bgColor
        window.navigationBarColor = bgColor
        buildLayout()
        render()
        refreshLibrary()
    }

    override fun onDestroy() {
        mainHandler.removeCallbacks(progressTick)
        mediaPlayer?.release()
        mediaPlayer = null
        artworkExecutor.shutdownNow()
        executor.shutdownNow()
        super.onDestroy()
    }

    private fun buildLayout() {
        root = LinearLayout(this).apply {
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
            )
            orientation = LinearLayout.VERTICAL
            background = GradientDrawable(
                GradientDrawable.Orientation.TOP_BOTTOM,
                intArrayOf(bgTopColor, bgColor)
            )
        }

        searchHeader = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(10), dp(16), dp(10))
            background = rounded(Color.rgb(18, 24, 36), 0)
        }

        val searchRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(12), 0, dp(10), 0)
            background = rounded(Color.argb(24, 255, 255, 255), dp(16))
        }
        searchRow.addView(label("⌕", 20f, mutedColor, Typeface.BOLD), LinearLayout.LayoutParams(dp(24), dp(46)))
        searchInput = EditText(this).apply {
            setTextColor(textColor)
            setHintTextColor(mutedColor)
            hint = "Search library..."
            setSingleLine(true)
            imeOptions = EditorInfo.IME_ACTION_SEARCH
            inputType = InputType.TYPE_CLASS_TEXT
            textSize = 15f
            setPadding(dp(8), 0, dp(8), 0)
            background = ColorDrawable(Color.TRANSPARENT)
            setOnFocusChangeListener { _, hasFocus ->
                if (hasFocus || searchMode.searchesRemoteSources || text.toString().isNotBlank()) {
                    searchModeBar.visibility = View.VISIBLE
                }
            }
            setOnEditorActionListener { _, actionId, _ ->
                if (actionId == EditorInfo.IME_ACTION_SEARCH) {
                    handleSearch()
                    true
                } else {
                    false
                }
            }
        }
        searchRow.addView(searchInput, LinearLayout.LayoutParams(0, dp(46), 1f))
        searchRow.addView(iconButton("×", primary = false) {
            searchInput.setText("")
            torrents = emptyList()
            searchMode = SearchMode.Library
            render()
        }, LinearLayout.LayoutParams(dp(34), dp(34)))
        searchHeader.addView(searchRow, matchWrapParams())

        searchModeBar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
            visibility = View.GONE
        }
        SearchMode.entries.forEach { mode ->
            searchModeBar.addView(modeChip(mode), LinearLayout.LayoutParams(0, dp(34), 1f).apply {
                leftMargin = dp(3)
                rightMargin = dp(3)
            })
        }
        searchHeader.addView(searchModeBar, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(34)).apply {
            topMargin = dp(10)
        })
        root.addView(searchHeader, matchWrapParams())

        statusText = label("", 13f, mutedColor, Typeface.NORMAL).apply {
            visibility = View.GONE
            setPadding(dp(13), dp(10), dp(13), dp(10))
            background = rounded(elevatedColor, dp(14), strokeColor, 1)
        }
        root.addView(statusText, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
            leftMargin = dp(16)
            rightMargin = dp(16)
            topMargin = dp(8)
        })

        val scroll = ScrollView(this).apply {
            isFillViewport = false
            overScrollMode = View.OVER_SCROLL_IF_CONTENT_SCROLLS
        }
        content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, dp(2), 0, dp(12))
        }
        scroll.addView(content, ViewGroup.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        ))
        root.addView(scroll, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))

        root.addView(playerBar(), LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(120)))

        tabBar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
            setPadding(dp(4), dp(4), dp(4), dp(4))
            background = rounded(surfaceColor, dp(18), strokeColor, 1)
        }
        root.addView(tabBar, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(64)).apply {
            leftMargin = dp(10)
            rightMargin = dp(10)
            topMargin = dp(8)
            bottomMargin = dp(8)
        })
        setContentView(root)
        applySystemBarInsets(root)
    }

    private fun applySystemBarInsets(view: View) {
        view.setOnApplyWindowInsetsListener { target, insets ->
            val topInset: Int
            val bottomInset: Int
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.R) {
                val systemBars = insets.getInsets(WindowInsets.Type.systemBars())
                topInset = systemBars.top
                bottomInset = systemBars.bottom
            } else {
                @Suppress("DEPRECATION")
                topInset = insets.systemWindowInsetTop
                @Suppress("DEPRECATION")
                bottomInset = insets.systemWindowInsetBottom
            }
            target.setPadding(0, topInset, 0, bottomInset)
            insets
        }
        view.requestApplyInsets()
    }

    private fun playerBar(): View {
        val holder = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(10), dp(16), dp(12))
            background = rounded(Color.rgb(19, 25, 37), 0)
            minimumHeight = dp(120)
        }
        miniProgress = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            max = 1000
            progress = 0
            progressTintList = ColorStateList.valueOf(accentAltColor)
            progressBackgroundTintList = ColorStateList.valueOf(Color.rgb(44, 53, 72))
        }
        holder.addView(miniProgress, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(4)))

        val modeRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(4), dp(10), dp(4), dp(7))
        }
        modeRow.addView(iconText("⇄", if (shuffleEnabled) accentAltColor else mutedColor) {
            shuffleEnabled = !shuffleEnabled
            updateMiniPlayer()
        }, LinearLayout.LayoutParams(dp(34), dp(28)))
        modeRow.addView(space(1, 1), weightParams(1f))
        modeRow.addView(label(repeatMode.label, 11f, mutedColor, Typeface.NORMAL), wrapParams())
        modeRow.addView(space(1, 1), weightParams(1f))
        modeRow.addView(iconText(repeatIcon(), if (repeatMode.isActive) accentAltColor else mutedColor) {
            repeatMode = when (repeatMode) {
                RepeatMode.Off -> RepeatMode.All
                RepeatMode.All -> RepeatMode.One
                RepeatMode.One -> RepeatMode.Off
            }
            updateMiniPlayer()
        }, LinearLayout.LayoutParams(dp(34), dp(28)))
        holder.addView(modeRow, matchWrapParams())

        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setOnClickListener { showExpandedPlayer() }
        }
        miniArtwork = FrameLayout(this).apply {
            addView(artTile("M", "Music", dp(46)), FrameLayout.LayoutParams(dp(46), dp(46)))
        }
        row.addView(miniArtwork, LinearLayout.LayoutParams(dp(46), dp(46)).apply {
            rightMargin = dp(12)
        })
        val textColumn = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        miniTitle = label("Nothing playing", 15f, textColor, Typeface.BOLD)
        miniSubtitle = label("Choose a track", 12f, mutedColor, Typeface.NORMAL)
        textColumn.addView(miniTitle, matchWrapParams())
        textColumn.addView(miniSubtitle, matchWrapParams())
        row.addView(textColumn, weightParams(1f))
        row.addView(iconText("⏮", textColor) { playPrevious() }, LinearLayout.LayoutParams(dp(34), dp(38)))
        row.addView(space(dp(4), 1))
        playButton = iconButton("▶", accent = accentAltColor) { togglePlayback() }
        row.addView(playButton, LinearLayout.LayoutParams(dp(42), dp(42)))
        row.addView(space(dp(4), 1))
        row.addView(iconText("⏭", textColor) { playNext() }, LinearLayout.LayoutParams(dp(34), dp(38)))
        row.addView(space(dp(4), 1))
        row.addView(iconText("☰", textColor) { showExpandedPlayer() }, LinearLayout.LayoutParams(dp(30), dp(38)))
        holder.addView(row, matchWrapParams())
        return holder
    }

    private fun showExpandedPlayer() {
        val dialog = Dialog(this)
        dialog.requestWindowFeature(Window.FEATURE_NO_TITLE)
        val screen = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(dp(22), dp(18), dp(22), dp(24))
            background = GradientDrawable(
                GradientDrawable.Orientation.TOP_BOTTOM,
                intArrayOf(elevatedColor, bgColor)
            )
        }

        val topRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        topRow.addView(label("Now Playing", 14f, textColor, Typeface.BOLD), weightParams(1f))
        topRow.addView(iconButton("⌄", primary = false) { dialog.dismiss() }, LinearLayout.LayoutParams(dp(44), dp(40)))
        screen.addView(topRow, matchWrapParams())

        val track = currentTrack
        val artworkSize = (resources.displayMetrics.widthPixels - dp(72)).coerceAtMost(dp(340))
        val artwork = if (track == null) {
            artTile("M", "Music", artworkSize)
        } else {
            artworkTile(track, track.title, track.displayArtist, artworkSize)
        }
        screen.addView(artwork, LinearLayout.LayoutParams(artworkSize, artworkSize).apply {
            topMargin = dp(24)
            bottomMargin = dp(26)
        })

        val infoBlock = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_VERTICAL
        }
        infoBlock.addView(
            label(track?.title ?: "Nothing playing", 24f, textColor, Typeface.BOLD).apply {
                maxLines = 2
                ellipsize = TextUtils.TruncateAt.END
            },
            matchWrapParams()
        )
        infoBlock.addView(
            label(
                track?.displayArtist ?: "Choose a track",
                16f,
                mutedColor,
                Typeface.BOLD
            ).apply {
                maxLines = 1
                ellipsize = TextUtils.TruncateAt.END
            },
            matchWrapParams()
        )
        infoBlock.addView(
            label(
                track?.displayAlbum ?: "",
                14f,
                mutedColor,
                Typeface.NORMAL
            ).apply {
                maxLines = 1
                ellipsize = TextUtils.TruncateAt.END
            },
            matchWrapParams()
        )
        val infoRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        infoRow.addView(infoBlock, weightParams(1f))
        if (track != null) {
            infoRow.addView(iconText(if (likedTrackIds.contains(track.id)) "♥" else "♡", if (likedTrackIds.contains(track.id)) Color.rgb(255, 105, 180) else textColor) {
                toggleLike(track)
            }, LinearLayout.LayoutParams(dp(48), dp(48)))
        }
        screen.addView(infoRow, matchWrapParams())

        val expandedProgress = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            max = 1000
            progress = miniProgress.progress
            progressTintList = ColorStateList.valueOf(Color.WHITE)
            progressBackgroundTintList = ColorStateList.valueOf(Color.rgb(44, 53, 72))
        }
        screen.addView(expandedProgress, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(5)).apply {
            topMargin = dp(26)
            bottomMargin = dp(22)
        })

        val controls = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
        }
        controls.addView(iconText("⇄", if (shuffleEnabled) accentAltColor else textColor) {
            shuffleEnabled = !shuffleEnabled
            updateMiniPlayer()
        }, LinearLayout.LayoutParams(dp(46), dp(52)).apply { rightMargin = dp(10) })
        controls.addView(iconButton("⏮", primary = false) {
            playPrevious()
            dialog.dismiss()
            mainHandler.postDelayed({ showExpandedPlayer() }, 250)
        }, LinearLayout.LayoutParams(dp(52), dp(52)).apply { rightMargin = dp(10) })
        lateinit var expandedPlay: TextView
        expandedPlay = iconButton(if (isPlaying) "⏸" else "▶", accent = Color.WHITE, textColorOverride = Color.BLACK) {
            togglePlayback()
            expandedPlay.text = if (isPlaying) "⏸" else "▶"
            expandedProgress.progress = miniProgress.progress
        }
        controls.addView(expandedPlay, LinearLayout.LayoutParams(dp(68), dp(68)).apply {
            leftMargin = dp(4)
            rightMargin = dp(4)
        })
        controls.addView(iconButton("⏭", primary = false) {
            playNext()
            dialog.dismiss()
            mainHandler.postDelayed({ showExpandedPlayer() }, 250)
        }, LinearLayout.LayoutParams(dp(52), dp(52)).apply { leftMargin = dp(10) })
        controls.addView(iconText(repeatIcon(), if (repeatMode.isActive) accentAltColor else textColor) {
            repeatMode = when (repeatMode) {
                RepeatMode.Off -> RepeatMode.All
                RepeatMode.All -> RepeatMode.One
                RepeatMode.One -> RepeatMode.Off
            }
            updateMiniPlayer()
        }, LinearLayout.LayoutParams(dp(46), dp(52)).apply { leftMargin = dp(10) })
        screen.addView(controls, matchWrapParams())

        val actions = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
        }
        actions.addView(button("Queue", primary = false, compact = true) {}, LinearLayout.LayoutParams(0, dp(42), 1f).apply {
            rightMargin = dp(6)
        })
        actions.addView(button("Up Next", primary = false, compact = true) {}, LinearLayout.LayoutParams(0, dp(42), 1f).apply {
            leftMargin = dp(6)
        })
        screen.addView(actions, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(42)).apply {
            topMargin = dp(28)
        })

        dialog.setContentView(screen)
        dialog.window?.apply {
            setBackgroundDrawable(ColorDrawable(Color.TRANSPARENT))
            setLayout(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
        }
        dialog.show()
        dialog.window?.setLayout(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
    }

    private fun handleSearch() {
        if (searchMode.searchesRemoteSources) {
            searchSources()
        } else {
            render()
        }
    }

    private fun render() {
        updateStatus()
        renderTabs()
        renderSearchModes()
        updateSearchHint()
        content.removeAllViews()
        if (isLoading) {
            content.addView(sectionTitle("Loading..."))
            content.addView(ProgressBar(this), centerParams())
            updateMiniPlayer()
            return
        }
        if (searchMode.searchesRemoteSources) {
            renderSources()
        } else {
            when (selectedTab) {
                MusicTab.Library -> renderLibrary()
                MusicTab.Albums -> renderAlbums()
                MusicTab.Liked -> renderLiked()
                MusicTab.Settings -> renderSettings()
            }
        }
        updateMiniPlayer()
    }

    private fun renderTabs() {
        tabBar.removeAllViews()
        MusicTab.entries.forEach { tab ->
            val selected = selectedTab == tab
            val tabButton = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                gravity = Gravity.CENTER
                background = rounded(if (selected) accentColor else Color.TRANSPARENT, dp(14))
                setOnClickListener {
                    selectedTab = tab
                    searchMode = SearchMode.Library
                    selectedAlbumId = null
                    statusMessage = null
                    render()
                }
            }
            tabButton.addView(ImageView(this).apply {
                setImageResource(tab.iconRes())
                imageTintList = ColorStateList.valueOf(if (selected) Color.BLACK else mutedColor)
                scaleType = ImageView.ScaleType.CENTER
            }, LinearLayout.LayoutParams(dp(22), dp(22)))
            tabButton.addView(label(tab.label, 11f, if (selected) Color.BLACK else mutedColor, Typeface.BOLD).apply {
                gravity = Gravity.CENTER
                includeFontPadding = false
            }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(16)).apply {
                topMargin = dp(2)
            })
            tabBar.addView(tabButton, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f).apply {
                leftMargin = dp(2)
                rightMargin = dp(2)
            })
        }
    }

    private fun MusicTab.iconRes(): Int {
        return when (this) {
            MusicTab.Library -> R.drawable.ic_tab_library
            MusicTab.Albums -> R.drawable.ic_tab_albums
            MusicTab.Liked -> R.drawable.ic_tab_liked
            MusicTab.Settings -> R.drawable.ic_tab_settings
        }
    }

    private fun renderSearchModes() {
        searchModeBar.removeAllViews()
        SearchMode.entries.forEach { mode ->
            searchModeBar.addView(modeChip(mode), LinearLayout.LayoutParams(0, dp(34), 1f).apply {
                leftMargin = dp(3)
                rightMargin = dp(3)
            })
        }
        searchModeBar.visibility = if (searchMode.searchesRemoteSources || searchInput.text.toString().isNotBlank() || searchInput.hasFocus()) {
            View.VISIBLE
        } else {
            View.GONE
        }
    }

    private fun modeChip(mode: SearchMode): TextView {
        return TextView(this).apply {
            text = mode.label
            gravity = Gravity.CENTER
            textSize = 12f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(if (searchMode == mode) Color.BLACK else mutedColor)
            background = rounded(if (searchMode == mode) accentAltColor else Color.argb(28, 255, 255, 255), dp(10))
            setOnClickListener {
                searchMode = mode
                if (!mode.searchesRemoteSources) torrents = emptyList()
                handleSearch()
            }
        }
    }

    private fun updateSearchHint() {
        searchInput.hint = when {
            searchMode == SearchMode.Torrent -> "Search torrents..."
            searchMode == SearchMode.Indexers -> "Search indexers..."
            selectedTab == MusicTab.Albums -> "Search albums..."
            selectedTab == MusicTab.Settings -> "Search is disabled in settings"
            else -> "Search library..."
        }
        searchInput.isEnabled = selectedTab != MusicTab.Settings
    }

    private fun updateStatus() {
        val message = statusMessage
        if (message.isNullOrBlank()) {
            statusText.visibility = View.GONE
            statusText.text = ""
        } else {
            statusText.visibility = View.VISIBLE
            statusText.text = message
            statusText.setTextColor(if (message.startsWith("Error")) dangerColor else mutedColor)
        }
    }

    private fun renderLibrary() {
        val visible = filteredTracks(tracks)
        content.addView(sectionTitle("Made For You").withHorizontalPagePadding())
        if (!canUseApi()) {
            content.addView(messageCard("Set API endpoint and token in Settings. For a phone or emulator, use your Mac/server LAN IP, not localhost."))
        }
        if (visible.isEmpty()) {
            content.addView(messageCard("No tracks found. Refresh after importing music on the backend."))
            return
        }
        if (searchInput.text.toString().trim().isNotEmpty()) {
            content.addView(sectionTitle("Search Results").withHorizontalPagePadding())
            visible.take(40).forEach { track ->
                content.addView(trackRow(track, visible))
            }
            return
        }
        content.addView(dailyMixShelf())
        content.addView(trackShelf("Recommended For You", recommendedTracks()))
        content.addView(trackShelf("Recently Added", recentlyAddedTracks()))
        val likedPreview = tracks.filter { likedTrackIds.contains(it.id) }.take(16)
        if (likedPreview.isNotEmpty()) {
            content.addView(trackShelf("Your Liked Mix", likedPreview))
        }
    }

    private fun renderLiked() {
        val liked = filteredTracks(tracks.filter { likedTrackIds.contains(it.id) })
        content.addView(sectionTitle("Liked Songs").withHorizontalPagePadding())
        content.addView(summaryPill("${likedTrackIds.size} saved tracks"))
        if (liked.isEmpty()) {
            content.addView(messageCard("Liked songs will show up here."))
            return
        }
        liked.forEach { track ->
            content.addView(trackRow(track, liked))
        }
    }

    private fun renderAlbums() {
        val albumId = selectedAlbumId
        if (albumId != null) {
            val album = albums.firstOrNull { it.id == albumId }
            if (album == null) {
                selectedAlbumId = null
                renderAlbums()
                return
            }
            content.addView(button("Back to albums", primary = false) {
                selectedAlbumId = null
                render()
            }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(44)).apply {
                leftMargin = dp(16)
                rightMargin = dp(16)
                topMargin = dp(10)
            })
            val hero = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.BOTTOM
                setPadding(dp(16), dp(16), dp(16), dp(12))
            }
            hero.addView(artworkTile(album.tracks.firstOrNull(), album.title, album.artist, dp(132)), LinearLayout.LayoutParams(dp(132), dp(132)).apply {
                rightMargin = dp(16)
            })
            val copy = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
            copy.addView(label(album.title, 22f, textColor, Typeface.BOLD).apply {
                maxLines = 2
                ellipsize = TextUtils.TruncateAt.END
            }, matchWrapParams())
            copy.addView(label(album.artist, 14f, mutedColor, Typeface.NORMAL).singleLineEnd(), matchWrapParams())
            copy.addView(label("${album.tracks.size} songs", 12f, mutedColor, Typeface.NORMAL), matchWrapParams())
            val albumActions = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
            }
            albumActions.addView(iconButton("▶", accent = accentAltColor) {
                album.tracks.firstOrNull()?.let { playTrack(it, album.tracks) }
            }, LinearLayout.LayoutParams(dp(46), dp(42)).apply { rightMargin = dp(10) })
            albumActions.addView(iconText("⇄", textColor) {
                shuffleEnabled = true
                album.tracks.shuffled().firstOrNull()?.let { playTrack(it, album.tracks.shuffled()) }
            }, LinearLayout.LayoutParams(dp(42), dp(42)))
            copy.addView(albumActions, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(46)).apply {
                topMargin = dp(8)
            })
            hero.addView(copy, weightParams(1f))
            content.addView(hero, matchWrapParams())
            album.tracks.forEach { track ->
                content.addView(trackRow(track, album.tracks))
            }
            return
        }

        val query = searchInput.text.toString().trim().lowercase(Locale.getDefault())
        val visible = albums.filter {
            query.isEmpty() ||
                it.title.lowercase(Locale.getDefault()).contains(query) ||
                it.artist.lowercase(Locale.getDefault()).contains(query)
        }
        content.addView(sectionTitle("Albums").withHorizontalPagePadding())
        if (visible.isEmpty()) {
            content.addView(messageCard("No albums found."))
            return
        }
        visible.chunked(2).forEach { rowAlbums ->
            val gridRow = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.TOP
                setPadding(dp(16), 0, dp(16), 0)
            }
            rowAlbums.forEachIndexed { index, album ->
                gridRow.addView(albumGridCard(album), LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply {
                    rightMargin = if (index == 0) dp(7) else 0
                    leftMargin = if (index == 1) dp(7) else 0
                })
            }
            if (rowAlbums.size == 1) {
                gridRow.addView(space(1, 1), LinearLayout.LayoutParams(0, 1, 1f).apply { leftMargin = dp(7) })
            }
            content.addView(gridRow, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
                topMargin = dp(7)
                bottomMargin = dp(7)
            })
        }
    }

    private fun renderSources() {
        content.addView(sectionTitle(if (searchMode == SearchMode.Indexers) "Indexer Search" else "Torrent Search").withHorizontalPagePadding())

        if (searchInput.text.toString().trim().isEmpty()) {
            content.addView(messageCard("Search for an artist, album, or track. Imports run on the FastAPI backend, just like the iOS app."))
        }
        if (torrents.isEmpty()) {
            return
        }
        torrents.forEach { torrent ->
            content.addView(torrentRow(torrent))
        }
    }

    private fun renderSettings() {
        content.addView(sectionTitle("Backend"))
        content.addView(messageCard("Connect the Android app to your private Mekamb backend."))
        val endpointField = editField("API endpoint", apiEndpoint, false)
        val tokenField = editField("API token", apiToken, true)
        val prowlarrField = editField("Prowlarr API key for indexer search", prowlarrApiKey, true)
        content.addView(endpointField, fieldParams())
        content.addView(tokenField, fieldParams())
        content.addView(prowlarrField, fieldParams())
        val buttons = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
        }
        buttons.addView(button("Save") {
            val previousEndpoint = apiEndpoint
            val previousToken = apiToken
            apiEndpoint = endpointField.text.toString().trim()
            apiToken = tokenField.text.toString().trim()
            prowlarrApiKey = prowlarrField.text.toString().trim()
            if (previousEndpoint != apiEndpoint || previousToken != apiToken) {
                clearArtworkState()
            }
            statusMessage = "Settings saved."
            render()
        }, LinearLayout.LayoutParams(0, dp(44), 1f).apply { rightMargin = dp(4) })
        buttons.addView(button("Test", primary = false) {
            apiEndpoint = endpointField.text.toString().trim()
            apiToken = tokenField.text.toString().trim()
            prowlarrApiKey = prowlarrField.text.toString().trim()
            testConnection()
        }, LinearLayout.LayoutParams(0, dp(44), 1f).apply { leftMargin = dp(4) })
        content.addView(buttons, matchWrapParams())
        content.addView(button("Refresh library", primary = false) {
            refreshLibrary()
        }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(44)).apply {
            topMargin = dp(10)
            bottomMargin = dp(4)
        })
        content.addView(messageCard("On a real Android phone, localhost means the phone itself. Use your Mac/server LAN IP, for example http://192.168.1.50:8000. Plain HTTP is enabled for private LAN development."))
    }

    private fun trackRow(track: ApiTrack, queue: List<ApiTrack>): View {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(12), dp(12), dp(12), dp(12))
            background = rounded(surfaceColor, dp(18), strokeColor, 1)
            setOnClickListener { playTrack(track, queue) }
        }
        row.addView(artworkTile(track, track.title, track.displayArtist, dp(52)), LinearLayout.LayoutParams(dp(52), dp(52)).apply {
            rightMargin = dp(12)
        })
        val meta = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        meta.addView(label(track.title, 16f, textColor, Typeface.BOLD).singleLineEnd(), matchWrapParams())
        meta.addView(label("${track.displayArtist} · ${track.displayAlbum}", 13f, mutedColor, Typeface.NORMAL).singleLineEnd(), matchWrapParams())
        row.addView(meta, weightParams(1f))
        row.addView(label(track.durationText(), 12f, mutedColor, Typeface.NORMAL), LinearLayout.LayoutParams(dp(42), ViewGroup.LayoutParams.WRAP_CONTENT).apply {
            rightMargin = dp(8)
        })
        row.addView(iconText(if (likedTrackIds.contains(track.id)) "♥" else "♡", if (likedTrackIds.contains(track.id)) Color.rgb(255, 105, 180) else mutedColor) {
            toggleLike(track)
        }, LinearLayout.LayoutParams(dp(32), dp(36)))
        return row.withCardMargin()
    }

    private fun torrentRow(torrent: TorrentResult): View {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(14), dp(13), dp(14), dp(13))
            background = rounded(surfaceColor, dp(18), strokeColor, 1)
        }
        row.addView(label(torrent.name, 16f, textColor, Typeface.BOLD).singleLineEnd(), matchWrapParams())
        val size = torrent.sizeBytes?.let { formatBytes(it) } ?: torrent.sizeLabel ?: "unknown size"
        val peers = "Seeders ${torrent.seeders ?: "0"} · Leechers ${torrent.leechers ?: "0"}"
        row.addView(label("${torrent.source.raw} · $size · $peers", 13f, mutedColor, Typeface.NORMAL).singleLineEnd(), matchWrapParams())
        row.addView(button("Import") { importTorrent(torrent) }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(42)).apply {
            topMargin = dp(10)
        })
        return row.withCardMargin()
    }

    private fun refreshLibrary() {
        if (!canUseApi()) {
            statusMessage = "Set API endpoint and token in Settings."
            render()
            return
        }
        runIo(
            task = {
                val loadedTracks = loadAllTracks()
                val loadedLikes = loadAllLikedTrackIds()
                Pair(loadedTracks, loadedLikes)
            },
            success = { (loadedTracks, loadedLikes) ->
                tracks = loadedTracks.sortedWith(trackComparator())
                likedTrackIds = loadedLikes
                albums = buildAlbums(tracks)
                missingArtworkIds.clear()
                statusMessage = "Library refreshed: ${tracks.size} songs."
                render()
                prefetchAlbumArtwork()
            }
        )
    }

    private fun searchSources() {
        val query = searchInput.text.toString().trim()
        if (!canUseApi()) {
            statusMessage = "Set API endpoint and token in Settings."
            render()
            return
        }
        if (query.isEmpty()) {
            torrents = emptyList()
            render()
            return
        }
        runIo(
            task = {
                val encoded = encodeQuery(query)
                val headers = if (searchMode == SearchMode.Indexers && prowlarrApiKey.isNotBlank()) {
                    mapOf("X-Prowlarr-Api-Key" to prowlarrApiKey)
                } else {
                    emptyMap()
                }
                val path = if (searchMode == SearchMode.Indexers) {
                    "/sources/indexers/search?q=$encoded"
                } else {
                    "/sources/search?q=$encoded"
                }
                val response = request(path, extraHeaders = headers)
                val items = JSONObject(response).optJSONArray("items") ?: JSONArray()
                parseTorrents(items).sortedByDescending { it.seeders?.toIntOrNull() ?: 0 }
            },
            success = { results ->
                torrents = results
                statusMessage = "Found ${results.size} source results."
                render()
            }
        )
    }

    private fun importTorrent(torrent: TorrentResult) {
        runIo(
            showLoading = false,
            task = {
                if (torrent.source == TorrentSource.Indexer) {
                    val infoHash = torrent.infoHash ?: throw ApiException("Indexer result is missing an info hash.")
                    val magnetLink = torrent.magnetLink ?: throw ApiException("Indexer result is missing a magnet link.")
                    val body = JSONObject()
                        .put("name", torrent.name)
                        .put("torrent_id", torrent.torrentId)
                        .put("info_hash", infoHash)
                        .put("magnet_link", magnetLink)
                        .put("uploader", torrent.uploader)
                        .put("source_url", torrent.sourceUrl)
                        .toString()
                    request(torrent.source.importPath, method = "POST", body = body)
                } else {
                    request("${torrent.source.importPath}/${encodePath(torrent.torrentId)}", method = "POST")
                }
            },
            success = {
                statusMessage = "Import queued: ${torrent.name}"
                render()
            }
        )
    }

    private fun toggleLike(track: ApiTrack) {
        val willLike = !likedTrackIds.contains(track.id)
        likedTrackIds = if (willLike) likedTrackIds + track.id else likedTrackIds - track.id
        render()
        runIo(
            showLoading = false,
            task = {
                val method = if (willLike) "PUT" else "DELETE"
                request("/tracks/${encodePath(track.id)}/like", method = method)
            },
            success = {
                statusMessage = if (willLike) "Liked ${track.title}." else "Removed like from ${track.title}."
                render()
            },
            error = {
                likedTrackIds = if (willLike) likedTrackIds - track.id else likedTrackIds + track.id
                statusMessage = "Error: ${it.message ?: "Could not update like."}"
                render()
            }
        )
    }

    private fun testConnection() {
        if (normalizedEndpoint().isBlank()) {
            statusMessage = "Error: enter an API endpoint first."
            render()
            return
        }
        runIo(
            task = { request("/health", requiresAuth = false) },
            success = {
                statusMessage = "Connection OK."
                render()
            }
        )
    }

    private fun playTrack(track: ApiTrack, queue: List<ApiTrack>) {
        if (!canUseApi()) {
            statusMessage = "Set API endpoint and token before streaming."
            updateStatus()
            return
        }
        if (endpointUrl("/tracks/${encodePath(track.id)}/stream") == null) {
            statusMessage = "Error: bad API endpoint."
            updateStatus()
            return
        }

        val requestId = playbackRequestId.incrementAndGet()
        mediaPlayer?.release()
        mediaPlayer = null
        isPlaying = false
        currentTrack = track
        playbackQueue = queue.ifEmpty { tracks }
        currentIndex = playbackQueue.indexOfFirst { it.id == track.id }
        statusMessage = "Loading ${track.title}..."
        updateStatus()
        updateMiniPlayer()

        executor.execute {
            val audioFile = runCatching { downloadTrackForPlayback(track) }
            mainHandler.post {
                if (requestId != playbackRequestId.get()) return@post
                audioFile.fold(
                    onSuccess = { file -> startCachedTrack(track, file, requestId) },
                    onFailure = { error ->
                        isPlaying = false
                        statusMessage = "Error: ${error.message ?: "playback download failed."}"
                        updateStatus()
                        updateMiniPlayer()
                    }
                )
            }
        }
    }

    private fun startCachedTrack(track: ApiTrack, audioFile: File, requestId: Int) {
        mediaPlayer?.release()
        mediaPlayer = MediaPlayer().apply {
            setWakeMode(this@MainActivity, PowerManager.PARTIAL_WAKE_LOCK)
            setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                    .build()
            )
            setDataSource(audioFile.absolutePath)
            setOnPreparedListener {
                if (requestId != playbackRequestId.get()) {
                    it.release()
                    return@setOnPreparedListener
                }
                it.start()
                this@MainActivity.isPlaying = true
                statusMessage = null
                updateStatus()
                mainHandler.removeCallbacks(progressTick)
                mainHandler.post(progressTick)
                updateMiniPlayer()
            }
            setOnCompletionListener {
                when (repeatMode) {
                    RepeatMode.One -> playTrack(track, playbackQueue.ifEmpty { tracks })
                    RepeatMode.Off -> {
                        val queue = playbackQueue.ifEmpty { tracks }
                        if (currentIndex >= 0 && currentIndex < queue.lastIndex) {
                            playNext()
                        } else {
                            this@MainActivity.isPlaying = false
                            updateMiniPlayer()
                        }
                    }
                    RepeatMode.All -> playNext()
                }
            }
            setOnErrorListener { _, what, extra ->
                this@MainActivity.isPlaying = false
                statusMessage = "Error: playback failed ($what/$extra)."
                updateStatus()
                updateMiniPlayer()
                true
            }
            prepareAsync()
        }
        currentTrack = track
        updateMiniPlayer()
    }

    private fun togglePlayback() {
        val player = mediaPlayer
        if (player == null) {
            tracks.firstOrNull()?.let { playTrack(it, tracks) }
            return
        }
        if (player.isPlaying) {
            player.pause()
            isPlaying = false
        } else {
            player.start()
            isPlaying = true
        }
        updateMiniPlayer()
    }

    private fun playNext() {
        val queue = playbackQueue.ifEmpty { tracks }
        if (queue.isEmpty()) return
        val nextIndex = if (shuffleEnabled && queue.size > 1) {
            queue.indices.filter { it != currentIndex }.random()
        } else {
            if (currentIndex < 0) 0 else (currentIndex + 1) % queue.size
        }
        playTrack(queue[nextIndex], queue)
    }

    private fun playPrevious() {
        val queue = playbackQueue.ifEmpty { tracks }
        if (queue.isEmpty()) return
        val previousIndex = if (currentIndex <= 0) queue.lastIndex else currentIndex - 1
        playTrack(queue[previousIndex], queue)
    }

    private fun updateMiniPlayer() {
        val track = currentTrack
        if (track == null) {
            miniTitle.text = "Nothing playing"
            miniSubtitle.text = "Choose a track"
            playButton.text = "▶"
            updateMiniArtwork(null)
            miniProgress.progress = 0
            return
        }
        miniTitle.text = track.title
        miniSubtitle.text = "${track.displayArtist} · ${track.displayAlbum}"
        playButton.text = if (isPlaying) "⏸" else "▶"
        updateMiniArtwork(track)
        val player = mediaPlayer
        val duration = player?.duration?.takeIf { it > 0 } ?: 0
        miniProgress.progress = if (duration > 0) {
            ((player?.currentPosition ?: 0).toDouble() / duration.toDouble() * 1000.0).roundToInt()
        } else {
            0
        }
    }

    private fun updateMiniArtwork(track: ApiTrack?) {
        if (!::miniArtwork.isInitialized) return
        val nextId = track?.id
        if (miniArtworkTrackId == nextId) return
        miniArtworkTrackId = nextId
        miniArtwork.removeAllViews()
        val artwork = if (track == null) {
            artTile("M", "Music", dp(46))
        } else {
            artworkTile(track, track.title, track.displayArtist, dp(46))
        }
        miniArtwork.addView(artwork, FrameLayout.LayoutParams(dp(46), dp(46)))
    }

    private fun <T> runIo(
        showLoading: Boolean = true,
        task: () -> T,
        success: (T) -> Unit,
        error: ((Exception) -> Unit)? = null
    ) {
        if (showLoading) {
            isLoading = true
            render()
        }
        executor.execute {
            try {
                val result = task()
                mainHandler.post {
                    if (showLoading) isLoading = false
                    success(result)
                }
            } catch (exception: Exception) {
                mainHandler.post {
                    if (showLoading) isLoading = false
                    if (error != null) {
                        error(exception)
                    } else {
                        statusMessage = "Error: ${exception.message ?: exception.javaClass.simpleName}"
                        render()
                    }
                }
            }
        }
    }

    private fun loadAllTracks(): List<ApiTrack> {
        val loaded = mutableListOf<ApiTrack>()
        val limit = 100
        var offset = 0
        while (true) {
            val response = JSONObject(request("/tracks?limit=$limit&offset=$offset"))
            val items = response.optJSONArray("items") ?: JSONArray()
            loaded += parseTracks(items)
            if (items.length() < limit) break
            offset += limit
        }
        return loaded
    }

    private fun loadAllLikedTrackIds(): Set<String> {
        val liked = mutableSetOf<String>()
        val limit = 100
        var offset = 0
        while (true) {
            val response = JSONObject(request("/tracks/liked?limit=$limit&offset=$offset"))
            val items = response.optJSONArray("items") ?: JSONArray()
            for (index in 0 until items.length()) {
                val item = items.optJSONObject(index) ?: continue
                val track = item.optJSONObject("track") ?: continue
                track.optCleanString("id")?.let { liked += it }
            }
            if (items.length() < limit) break
            offset += limit
        }
        return liked
    }

    private fun downloadTrackForPlayback(track: ApiTrack): File {
        val endpoint = endpointUrl("/tracks/${encodePath(track.id)}/stream")
            ?: throw ApiException("Bad API endpoint. Use http://IP:8000.")
        val connection = URL(endpoint).openConnection() as HttpURLConnection
        connection.requestMethod = "GET"
        connection.connectTimeout = 20_000
        connection.readTimeout = 45_000
        connection.setRequestProperty("Accept", track.mediaType ?: "audio/*")
        connection.setRequestProperty("Authorization", "Bearer $apiToken")
        val status = connection.responseCode
        if (status !in 200..299) {
            val detail = connection.errorStream?.bufferedReader()?.use { it.readText() }
            connection.disconnect()
            throw ApiException(detail?.takeIf { it.isNotBlank() } ?: "stream error $status")
        }

        val directory = File(cacheDir, "playback").apply { mkdirs() }
        val output = File(directory, "${track.id}.${playbackExtension(track)}")
        connection.inputStream.use { input ->
            output.outputStream().use { fileOutput ->
                input.copyTo(fileOutput)
            }
        }
        connection.disconnect()
        if (output.length() <= 0L) {
            output.delete()
            throw ApiException("empty audio file")
        }
        return output
    }

    private fun request(
        path: String,
        method: String = "GET",
        body: String? = null,
        extraHeaders: Map<String, String> = emptyMap(),
        requiresAuth: Boolean = true
    ): String {
        val endpoint = endpointUrl(path) ?: throw ApiException("Bad API endpoint. Use http://IP:8000.")
        val connection = URL(endpoint).openConnection() as HttpURLConnection
        connection.requestMethod = method
        connection.connectTimeout = 20_000
        connection.readTimeout = 20_000
        connection.setRequestProperty("Accept", "application/json")
        if (requiresAuth) {
            connection.setRequestProperty("Authorization", "Bearer $apiToken")
        }
        extraHeaders.forEach { (name, value) -> connection.setRequestProperty(name, value) }
        if (body != null) {
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json")
            OutputStreamWriter(connection.outputStream).use { it.write(body) }
        }
        val status = connection.responseCode
        val stream = if (status in 200..299) connection.inputStream else connection.errorStream
        val payload = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
        connection.disconnect()
        if (status !in 200..299) {
            val detail = runCatching { JSONObject(payload).optString("detail") }.getOrNull()
            throw ApiException(detail?.takeIf { it.isNotBlank() } ?: "API error $status")
        }
        return payload
    }

    private fun playbackExtension(track: ApiTrack): String {
        val filenameExtension = track.originalFilename
            ?.substringAfterLast('.', "")
            ?.lowercase(Locale.getDefault())
            ?.filter { it.isLetterOrDigit() }
            ?.takeIf { it.length in 2..5 }
        if (filenameExtension != null) return filenameExtension
        return when (track.mediaType?.lowercase(Locale.getDefault())) {
            "audio/mpeg" -> "mp3"
            "audio/mp4", "audio/aac", "audio/x-m4a" -> "m4a"
            "audio/flac", "audio/x-flac" -> "flac"
            "audio/ogg" -> "ogg"
            "audio/wav", "audio/x-wav" -> "wav"
            else -> "audio"
        }
    }

    private fun parseTracks(items: JSONArray): List<ApiTrack> {
        val parsed = mutableListOf<ApiTrack>()
        for (index in 0 until items.length()) {
            val item = items.optJSONObject(index) ?: continue
            val id = item.optCleanString("id") ?: continue
            parsed += ApiTrack(
                id = id,
                title = item.optCleanString("title") ?: item.optCleanString("original_filename") ?: "Untitled",
                artist = item.optCleanString("artist"),
                album = item.optCleanString("album"),
                originalFilename = item.optCleanString("original_filename"),
                mediaType = item.optCleanString("media_type"),
                durationSeconds = item.optNullableDouble("duration_seconds"),
                sizeBytes = item.optNullableLong("size_bytes"),
                createdAt = item.optCleanString("created_at")
            )
        }
        return parsed
    }

    private fun parseTorrents(items: JSONArray): List<TorrentResult> {
        val parsed = mutableListOf<TorrentResult>()
        for (index in 0 until items.length()) {
            val item = items.optJSONObject(index) ?: continue
            val name = item.optCleanString("name") ?: continue
            val torrentId = item.optCleanString("torrent_id") ?: continue
            parsed += TorrentResult(
                name = name,
                torrentId = torrentId,
                source = TorrentSource.from(item.optCleanString("source")),
                infoHash = item.optCleanString("info_hash"),
                magnetLink = item.optCleanString("magnet_link"),
                sourceUrl = item.optCleanString("source_url"),
                seeders = item.optCleanString("seeders"),
                leechers = item.optCleanString("leechers"),
                sizeBytes = item.optNullableLong("size_bytes"),
                sizeLabel = item.optCleanString("size"),
                uploader = item.optCleanString("uploader")
            )
        }
        return parsed
    }

    private fun buildAlbums(sourceTracks: List<ApiTrack>): List<Album> {
        return sourceTracks
            .groupBy { normalizedAlbumId(it.displayAlbum) }
            .map { (id, albumTracks) ->
                val first = albumTracks.first()
                Album(
                    id = id,
                    title = first.displayAlbum,
                    artist = dominantArtist(albumTracks),
                    tracks = albumTracks.sortedWith(trackComparator())
                )
            }
            .sortedWith(compareBy({ it.title.lowercase(Locale.getDefault()) }, { it.artist.lowercase(Locale.getDefault()) }))
    }

    private fun dominantArtist(albumTracks: List<ApiTrack>): String {
        return albumTracks
            .groupingBy { it.displayArtist }
            .eachCount()
            .maxByOrNull { it.value }
            ?.key ?: "Unknown Artist"
    }

    private fun filteredTracks(source: List<ApiTrack>): List<ApiTrack> {
        val query = searchInput.text.toString().trim().lowercase(Locale.getDefault())
        if (query.isEmpty()) return source
        return source.filter {
            it.title.lowercase(Locale.getDefault()).contains(query) ||
                it.displayArtist.lowercase(Locale.getDefault()).contains(query) ||
                it.displayAlbum.lowercase(Locale.getDefault()).contains(query)
        }
    }

    private fun trackComparator(): Comparator<ApiTrack> {
        return compareBy<ApiTrack>(
            { it.displayArtist.lowercase(Locale.getDefault()) },
            { it.displayAlbum.lowercase(Locale.getDefault()) },
            { leadingTrackNumber(it.originalFilename ?: it.title) ?: Int.MAX_VALUE },
            { it.title.lowercase(Locale.getDefault()) }
        )
    }

    private fun leadingTrackNumber(value: String): Int? {
        val match = Regex("""^\D*(\d{1,3})""").find(value) ?: return null
        return match.groupValues.getOrNull(1)?.toIntOrNull()
    }

    private fun normalizedAlbumId(album: String): String {
        return album.trim().lowercase(Locale.getDefault()).replace(Regex("""\s+"""), " ")
    }

    private fun canUseApi(): Boolean {
        return normalizedEndpoint().isNotBlank() && apiToken.isNotBlank()
    }

    private fun normalizedEndpoint(): String {
        val trimmed = apiEndpoint.trim().trimEnd('/')
        if (trimmed.isBlank()) return ""
        return if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) trimmed else "http://$trimmed"
    }

    private fun endpointUrl(path: String): String? {
        val base = normalizedEndpoint()
        if (base.isBlank()) return null
        return base + path
    }

    private fun encodeQuery(value: String): String {
        return URLEncoder.encode(value, "UTF-8").replace("+", "%20")
    }

    private fun encodePath(value: String): String {
        return URLEncoder.encode(value, "UTF-8").replace("+", "%20")
    }

    private fun ApiTrack.durationText(): String {
        val seconds = durationSeconds?.takeIf { it.isFinite() && it > 0 }?.roundToInt() ?: return "0:00"
        return "${seconds / 60}:${(seconds % 60).toString().padStart(2, '0')}"
    }

    private fun formatBytes(bytes: Long): String {
        if (bytes <= 0) return "0 B"
        val units = listOf("B", "KB", "MB", "GB", "TB")
        var value = bytes.toDouble()
        var index = 0
        while (value >= 1024 && index < units.lastIndex) {
            value /= 1024
            index += 1
        }
        return if (index == 0) "${value.toLong()} ${units[index]}" else String.format(Locale.US, "%.1f %s", value, units[index])
    }

    private fun JSONObject.optCleanString(name: String): String? {
        if (!has(name) || isNull(name)) return null
        return optString(name).takeIf { it.isNotBlank() }
    }

    private fun JSONObject.optNullableDouble(name: String): Double? {
        if (!has(name) || isNull(name)) return null
        return optDouble(name).takeIf { !it.isNaN() }
    }

    private fun JSONObject.optNullableLong(name: String): Long? {
        if (!has(name) || isNull(name)) return null
        return optLong(name)
    }

    private fun sectionTitle(value: String): TextView {
        return label(value, 20f, textColor, Typeface.BOLD).apply {
            setPadding(0, dp(14), 0, dp(8))
        }
    }

    private fun statsRow(): View {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
        }
        row.addView(metricCard(tracks.size.toString(), "Songs"), LinearLayout.LayoutParams(0, dp(70), 1f).apply {
            rightMargin = dp(6)
        })
        row.addView(metricCard(albums.size.toString(), "Albums"), LinearLayout.LayoutParams(0, dp(70), 1f).apply {
            leftMargin = dp(3)
            rightMargin = dp(3)
        })
        row.addView(metricCard(likedTrackIds.size.toString(), "Liked"), LinearLayout.LayoutParams(0, dp(70), 1f).apply {
            leftMargin = dp(6)
        })
        return row.apply {
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
                bottomMargin = dp(8)
            }
        }
    }

    private fun metricCard(value: String, caption: String): LinearLayout {
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(dp(10), dp(8), dp(10), dp(8))
            background = rounded(elevatedColor, dp(18), strokeColor, 1)
            addView(label(value, 19f, textColor, Typeface.BOLD), wrapParams())
            addView(label(caption, 12f, mutedColor, Typeface.NORMAL), wrapParams())
        }
    }

    private fun dailyMixShelf(): View {
        val mixes = dailyMixes()
        if (mixes.isEmpty()) return space(1, 1)
        val section = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, dp(8), 0, dp(8))
        }
        section.addView(sectionTitle("Daily Mixes").withHorizontalPagePadding())
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(dp(16), 0, dp(16), 0)
        }
        mixes.forEach { mix ->
            row.addView(dailyMixCard(mix.first, mix.second), LinearLayout.LayoutParams(dp(156), ViewGroup.LayoutParams.WRAP_CONTENT).apply {
                rightMargin = dp(14)
            })
        }
        section.addView(horizontalScroll(row), matchWrapParams())
        return section
    }

    private fun trackShelf(title: String, shelfTracks: List<ApiTrack>): View {
        if (shelfTracks.isEmpty()) return space(1, 1)
        val section = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, dp(8), 0, dp(8))
        }
        section.addView(sectionTitle(title).withHorizontalPagePadding())
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(dp(16), 0, dp(16), 0)
        }
        shelfTracks.take(24).forEach { track ->
            row.addView(trackRecommendationCard(track, shelfTracks), LinearLayout.LayoutParams(dp(132), ViewGroup.LayoutParams.WRAP_CONTENT).apply {
                rightMargin = dp(14)
            })
        }
        section.addView(horizontalScroll(row), matchWrapParams())
        return section
    }

    private fun dailyMixCard(title: String, mixTracks: List<ApiTrack>): View {
        val first = mixTracks.firstOrNull()
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setOnClickListener { first?.let { playTrack(it, mixTracks) } }
            addView(artworkTile(first, title, first?.displayArtist ?: "Mix", dp(156)), LinearLayout.LayoutParams(dp(156), dp(156)))
            addView(label(title, 14f, textColor, Typeface.BOLD).apply {
                maxLines = 1
                ellipsize = TextUtils.TruncateAt.END
                setPadding(0, dp(8), 0, 0)
            }, matchWrapParams())
            addView(label(mixTracks.take(3).joinToString(", ") { it.displayArtist }, 12f, mutedColor, Typeface.NORMAL).apply {
                maxLines = 2
                ellipsize = TextUtils.TruncateAt.END
            }, matchWrapParams())
        }
    }

    private fun trackRecommendationCard(track: ApiTrack, queue: List<ApiTrack>): View {
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setOnClickListener { playTrack(track, queue) }
            addView(artworkTile(track, track.title, track.displayArtist, dp(132)), LinearLayout.LayoutParams(dp(132), dp(132)))
            addView(label(track.title, 14f, textColor, Typeface.BOLD).apply {
                maxLines = 2
                ellipsize = TextUtils.TruncateAt.END
                setPadding(0, dp(8), 0, 0)
            }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(48)))
            addView(label(track.displayArtist, 12f, mutedColor, Typeface.NORMAL).singleLineEnd(), matchWrapParams())
        }
    }

    private fun albumGridCard(album: Album): View {
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(10), dp(10), dp(10), dp(10))
            background = rounded(Color.argb(16, 255, 255, 255), dp(18))
            setOnClickListener {
                selectedAlbumId = album.id
                render()
            }
            addView(artworkTile(album.tracks.firstOrNull(), album.title, album.artist, dp(142)), LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(142)))
            addView(label(album.title, 14f, textColor, Typeface.BOLD).apply {
                maxLines = 1
                ellipsize = TextUtils.TruncateAt.END
                setPadding(0, dp(8), 0, 0)
            }, matchWrapParams())
            addView(label("${album.artist} · ${album.tracks.size} songs", 12f, mutedColor, Typeface.NORMAL).singleLineEnd(), matchWrapParams())
        }
    }

    private fun horizontalScroll(row: View): HorizontalScrollView {
        return HorizontalScrollView(this).apply {
            isHorizontalScrollBarEnabled = false
            overScrollMode = View.OVER_SCROLL_IF_CONTENT_SCROLLS
            addView(row, LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        }
    }

    private fun recommendedTracks(): List<ApiTrack> {
        val likedArtists = tracks
            .filter { likedTrackIds.contains(it.id) }
            .map { it.displayArtist }
            .toSet()
        val personalized = tracks.filter { it.displayArtist in likedArtists && !likedTrackIds.contains(it.id) }
        return (personalized + tracks).distinctBy { it.id }.take(24)
    }

    private fun recentlyAddedTracks(): List<ApiTrack> {
        return tracks.sortedByDescending { it.createdAt ?: "" }.take(24)
    }

    private fun dailyMixes(): List<Pair<String, List<ApiTrack>>> {
        return tracks
            .groupBy { it.displayArtist }
            .filter { it.value.size >= 2 }
            .toList()
            .sortedByDescending { it.second.size }
            .take(6)
            .mapIndexed { index, entry -> "Daily Mix ${index + 1}" to entry.second.take(12) }
    }

    private fun summaryPill(value: String): View {
        return label(value, 13f, mutedColor, Typeface.BOLD).apply {
            setPadding(dp(12), dp(8), dp(12), dp(8))
            background = rounded(chipColor, dp(999), strokeColor, 1)
        }.withCardMargin()
    }

    private fun messageCard(value: String): TextView {
        return label(value, 14f, mutedColor, Typeface.NORMAL).apply {
            setPadding(dp(14), dp(12), dp(14), dp(12))
            background = rounded(elevatedColor, dp(18), strokeColor, 1)
        }.withCardMargin() as TextView
    }

    private fun label(value: String, size: Float, color: Int, style: Int): TextView {
        return TextView(this).apply {
            text = value
            textSize = size
            setTextColor(color)
            typeface = Typeface.DEFAULT_BOLD.takeIf { style == Typeface.BOLD } ?: Typeface.DEFAULT
            setLineSpacing(0f, 1.08f)
        }
    }

    private fun TextView.singleLineEnd(): TextView {
        setSingleLine(true)
        ellipsize = TextUtils.TruncateAt.END
        return this
    }

    private fun artworkTile(track: ApiTrack?, title: String, subtitle: String, size: Int): View {
        val holder = FrameLayout(this).apply {
            layoutParams = LinearLayout.LayoutParams(size, size)
        }
        holder.addView(artTile(title, subtitle, size), FrameLayout.LayoutParams(size, size))

        val trackId = track?.id
        if (trackId.isNullOrBlank() || !canUseApi() || missingArtworkIds.contains(trackId)) {
            return holder
        }

        val cacheKey = artworkCacheKey(trackId)
        val imageView = ImageView(this).apply {
            tag = cacheKey
            visibility = View.GONE
            scaleType = ImageView.ScaleType.CENTER_CROP
            background = rounded(surfaceColor, dp(16))
            clipToOutline = true
        }
        holder.addView(imageView, FrameLayout.LayoutParams(size, size))
        bindArtwork(imageView, trackId, cacheKey, size)
        return holder
    }

    private fun bindArtwork(imageView: ImageView, trackId: String, cacheKey: String, size: Int) {
        artworkCache.get(cacheKey)?.let { cached ->
            imageView.setImageBitmap(cached)
            imageView.visibility = View.VISIBLE
            return
        }
        readCachedArtwork(cacheKey, size)?.let { cached ->
            artworkCache.put(cacheKey, cached)
            imageView.setImageBitmap(cached)
            imageView.visibility = View.VISIBLE
            return
        }
        if (missingArtworkIds.contains(cacheKey) || !requestedArtworkIds.add(cacheKey)) {
            return
        }
        artworkExecutor.execute {
            val bitmap = runCatching {
                fetchArtworkBitmap(trackId, cacheKey, size)
            }.getOrNull()
            mainHandler.post {
                requestedArtworkIds -= cacheKey
                if (imageView.tag != cacheKey) return@post
                if (bitmap == null) {
                    missingArtworkIds += cacheKey
                } else {
                    artworkCache.put(cacheKey, bitmap)
                    imageView.setImageBitmap(bitmap)
                    imageView.visibility = View.VISIBLE
                }
            }
        }
    }

    private fun clearArtworkState() {
        artworkCache.evictAll()
        missingArtworkIds.clear()
        requestedArtworkIds.clear()
    }

    private fun prefetchAlbumArtwork() {
        if (!canUseApi()) return
        val tracksToWarm = albums
            .mapNotNull { it.tracks.firstOrNull() }
            .distinctBy { it.id }
            .take(120)
        if (tracksToWarm.isEmpty()) return

        artworkExecutor.execute {
            tracksToWarm.forEach { track ->
                val cacheKey = artworkCacheKey(track.id)
                if (artworkCache.get(cacheKey) != null || artworkCacheFile(cacheKey).isFile) {
                    return@forEach
                }
                val bitmap = runCatching { fetchArtworkBitmap(track.id, cacheKey, dp(160)) }.getOrNull()
                if (bitmap != null) {
                    artworkCache.put(cacheKey, bitmap)
                }
            }
        }
    }

    private fun fetchArtworkBitmap(trackId: String, cacheKey: String, size: Int): Bitmap? {
        val endpoint = endpointUrl("/tracks/${encodePath(trackId)}/artwork") ?: return null
        val connection = URL(endpoint).openConnection() as HttpURLConnection
        connection.requestMethod = "GET"
        connection.connectTimeout = 12_000
        connection.readTimeout = 12_000
        connection.setRequestProperty("Accept", "image/*")
        connection.setRequestProperty("Authorization", "Bearer $apiToken")
        val status = connection.responseCode
        if (status !in 200..299) {
            connection.disconnect()
            return null
        }
        val bytes = connection.inputStream.use { it.readBytes() }
        connection.disconnect()
        val bitmap = decodeArtwork(bytes, size * 2) ?: return null
        writeCachedArtwork(cacheKey, bytes)
        return bitmap
    }

    private fun readCachedArtwork(cacheKey: String, size: Int): Bitmap? {
        val file = artworkCacheFile(cacheKey)
        if (!file.isFile || file.length() <= 0L) return null
        val bytes = runCatching { file.readBytes() }.getOrNull() ?: return null
        return decodeArtwork(bytes, size * 2)
    }

    private fun writeCachedArtwork(cacheKey: String, bytes: ByteArray) {
        if (bytes.isEmpty()) return
        val file = artworkCacheFile(cacheKey)
        val temp = File(file.parentFile, "${file.name}.tmp")
        runCatching {
            temp.writeBytes(bytes)
            if (!temp.renameTo(file)) {
                file.delete()
                temp.renameTo(file)
            }
        }.onFailure {
            temp.delete()
        }
    }

    private fun artworkCacheFile(cacheKey: String): File {
        return File(artworkDiskDir, "$cacheKey.img")
    }

    private fun artworkCacheKey(trackId: String): String {
        val identity = "${normalizedEndpoint()}|${apiToken.trim()}|$trackId"
        val digest = MessageDigest.getInstance("SHA-256").digest(identity.toByteArray(Charsets.UTF_8))
        return digest.joinToString("") { "%02x".format(it) }
    }

    private fun decodeArtwork(bytes: ByteArray, targetSize: Int): Bitmap? {
        if (bytes.isEmpty()) return null
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return null

        val options = BitmapFactory.Options().apply {
            inSampleSize = artworkSampleSize(bounds.outWidth, bounds.outHeight, targetSize)
        }
        return BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options)
    }

    private fun artworkSampleSize(width: Int, height: Int, targetSize: Int): Int {
        var sampleSize = 1
        var halfWidth = width / 2
        var halfHeight = height / 2
        while (halfWidth / sampleSize >= targetSize && halfHeight / sampleSize >= targetSize) {
            sampleSize *= 2
        }
        return sampleSize
    }

    private fun artTile(title: String, subtitle: String, size: Int): TextView {
        val seed = (title + subtitle).fold(0) { total, char -> total + char.code }
        val colors = listOf(accentColor, accentAltColor, Color.rgb(255, 178, 92), Color.rgb(226, 107, 255))
        val start = colors[seed % colors.size]
        val end = colors[(seed + 1) % colors.size]
        return TextView(this).apply {
            text = title.trim().firstOrNull()?.uppercaseChar()?.toString() ?: "M"
            gravity = Gravity.CENTER
            textSize = 19f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Color.BLACK)
            background = GradientDrawable(GradientDrawable.Orientation.TL_BR, intArrayOf(start, end)).apply {
                cornerRadius = dp(16).toFloat()
            }
            layoutParams = LinearLayout.LayoutParams(size, size)
        }
    }

    private fun editField(hintText: String, value: String, secret: Boolean): EditText {
        return EditText(this).apply {
            hint = hintText
            setText(value)
            setTextColor(textColor)
            setHintTextColor(mutedColor)
            setSingleLine(true)
            inputType = if (secret) {
                InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            } else {
                InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
            }
            textSize = 15f
            setPadding(dp(14), 0, dp(14), 0)
            background = rounded(surfaceColor, dp(16), strokeColor, 1)
        }
    }

    private fun button(value: String, compact: Boolean = false, primary: Boolean = true, action: () -> Unit): TextView {
        return TextView(this).apply {
            text = value
            gravity = Gravity.CENTER
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(if (primary) Color.BLACK else textColor)
            textSize = if (compact) 12f else 14f
            setPadding(dp(if (compact) 10 else 14), 0, dp(if (compact) 10 else 14), 0)
            background = rounded(if (primary) accentColor else chipColor, dp(999), if (primary) Color.TRANSPARENT else strokeColor, if (primary) 0 else 1)
            setOnClickListener { action() }
        }
    }

    private fun iconButton(value: String, primary: Boolean = true, action: () -> Unit): TextView {
        return iconButton(value, primary, if (primary) accentColor else chipColor, if (primary) Color.BLACK else textColor, action)
    }

    private fun iconButton(value: String, primary: Boolean = true, accent: Int, textColorOverride: Int = if (primary) Color.BLACK else textColor, action: () -> Unit): TextView {
        return TextView(this).apply {
            text = value
            gravity = Gravity.CENTER
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(textColorOverride)
            textSize = if (value.length > 1) 18f else 21f
            background = rounded(
                if (primary) accent else chipColor,
                dp(999),
                if (primary) Color.TRANSPARENT else strokeColor,
                if (primary) 0 else 1,
            )
            setOnClickListener { action() }
        }
    }

    private fun iconText(value: String, color: Int, action: () -> Unit): TextView {
        return TextView(this).apply {
            text = value
            gravity = Gravity.CENTER
            typeface = Typeface.DEFAULT_BOLD
            textSize = 21f
            setTextColor(color)
            setOnClickListener { action() }
        }
    }

    private fun repeatIcon(): String {
        return when (repeatMode) {
            RepeatMode.One -> "↻1"
            RepeatMode.Off, RepeatMode.All -> "↻"
        }
    }

    private fun rounded(color: Int, radius: Int, stroke: Int = Color.TRANSPARENT, strokeWidth: Int = 0): GradientDrawable {
        return GradientDrawable().apply {
            setColor(color)
            cornerRadius = radius.toFloat()
            if (strokeWidth > 0) {
                setStroke(dp(strokeWidth), stroke)
            }
        }
    }

    private fun space(width: Int, height: Int): View {
        return View(this).apply {
            layoutParams = LinearLayout.LayoutParams(width, height)
        }
    }

    private fun View.withCardMargin(): View {
        layoutParams = cardParams()
        return this
    }

    private fun View.withHorizontalPagePadding(): View {
        layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
            leftMargin = dp(16)
            rightMargin = dp(16)
        }
        return this
    }

    private fun cardParams(): LinearLayout.LayoutParams {
        return LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
            leftMargin = dp(16)
            rightMargin = dp(16)
            topMargin = dp(6)
            bottomMargin = dp(6)
        }
    }

    private fun fieldParams(): LinearLayout.LayoutParams {
        return LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(48)).apply {
            bottomMargin = dp(10)
        }
    }

    private fun matchWrapParams(): LinearLayout.LayoutParams {
        return LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
    }

    private fun wrapParams(): LinearLayout.LayoutParams {
        return LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT)
    }

    private fun weightParams(weight: Float): LinearLayout.LayoutParams {
        return LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, weight)
    }

    private fun centerParams(): LinearLayout.LayoutParams {
        return LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
            gravity = Gravity.CENTER_HORIZONTAL
            topMargin = dp(24)
        }
    }

    private fun dp(value: Int): Int {
        return (value * resources.displayMetrics.density).roundToInt()
    }
}

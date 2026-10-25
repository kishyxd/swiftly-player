package de.paulherter.swiftly.shared

import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

/**
 * The FTV edition's wordmark: the fish-and-TV mark, the same artwork as the app icon and the
 * TV banner.
 *
 * Upstream draws the "Swiftly" script as two vector paths (`MarksPaths.wordmark`), which is why
 * the signature takes a colour and a gradient. The FTV mark is a picture, not a path, so the
 * colour arguments stay for source compatibility and no longer tint anything: the fish is
 * purple and the letters white wherever the mark appears.
 */
@Composable
fun Wordmark(height: Dp = 32.dp, font: Color = Theme.font, accent: Color = Color(MarksPaths.accent),
             gradient: List<Color>? = null) {
    // The mark is 1024 x 1024 px, so the width follows from the height.
    val width = height * (1024f / 1024f)
    Image(
        painter = painterResource(R.drawable.ftv_wordmark),
        contentDescription = null,
        contentScale = ContentScale.Fit,
        modifier = Modifier.width(width).height(height)
    )
}

package pl.mekamb.music.ui.components

import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.FavoriteBorder
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import pl.mekamb.music.data.ImportStatus
import pl.mekamb.music.ui.theme.MekambColors
import kotlin.math.roundToInt

@Composable
fun SectionTitle(text: String, modifier: Modifier = Modifier) {
    Text(text, modifier = modifier, color = MekambColors.TextPrimary, fontSize = 17.sp, fontWeight = FontWeight.ExtraBold)
}

@Composable
fun ScreenTitle(text: String, modifier: Modifier = Modifier) {
    Text(text, modifier = modifier, color = MekambColors.TextPrimary, fontSize = 23.sp, fontWeight = FontWeight.ExtraBold)
}

/** Three animated bars shown on the currently-playing track row, mirroring the prototype's
 * `@keyframes eqa/eqb/eqc` pulsing equalizer indicator. */
@Composable
fun EqualizerBars(color: Color = MekambColors.Accent, modifier: Modifier = Modifier) {
    val transition = rememberInfiniteTransition(label = "eq")
    val h1 by transition.animateFloat(5f, 13f, infiniteRepeatable(tween(900, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "eq1")
    val h2 by transition.animateFloat(11f, 4f, infiniteRepeatable(tween(800, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "eq2")
    val h3 by transition.animateFloat(7f, 14f, infiniteRepeatable(tween(1000, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "eq3")
    Row(modifier.height(14.dp), horizontalArrangement = Arrangement.spacedBy(2.dp), verticalAlignment = Alignment.Bottom) {
        Box(Modifier.width(3.dp).height(h1.dp).background(color, RoundedCornerShape(1.dp)))
        Box(Modifier.width(3.dp).height(h2.dp).background(color, RoundedCornerShape(1.dp)))
        Box(Modifier.width(3.dp).height(h3.dp).background(color, RoundedCornerShape(1.dp)))
    }
}

/** Leading slot for album/mix track rows: a tabular track number, or [EqualizerBars] in place of
 * the number for whichever row is currently playing. */
@Composable
fun TrackIndexOrEqualizer(number: Int, isCurrent: Boolean, modifier: Modifier = Modifier) {
    Box(modifier.width(26.dp), contentAlignment = Alignment.CenterStart) {
        if (isCurrent) {
            EqualizerBars()
        } else {
            Text("$number", color = MekambColors.TextFaint, fontSize = 13.sp)
        }
    }
}

@Composable
fun LikeButton(isLiked: Boolean, onToggle: () -> Unit, modifier: Modifier = Modifier, size: Dp = 18.dp) {
    val interactionSource = remember { MutableInteractionSource() }
    Icon(
        imageVector = if (isLiked) Icons.Filled.Favorite else Icons.Filled.FavoriteBorder,
        contentDescription = if (isLiked) "Unlike" else "Like",
        tint = if (isLiked) MekambColors.Like else MekambColors.TextMuted,
        modifier = modifier
            .size(size + 14.dp)
            .clip(CircleShape)
            .clickable(interactionSource = interactionSource, indication = null) { onToggle() }
            .padding(7.dp),
    )
}

/** A single generic list row used for tracks everywhere (Album/Artist/Liked/Mix/Library): a
 * leading slot (artwork or track-number/equalizer), title + subtitle, and an optional trailing
 * slot (heart, duration, chevron, ≡ menu…). */
@Composable
fun TrackRow(
    title: String,
    subtitle: String,
    isCurrent: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    leading: @Composable () -> Unit,
    trailing: (@Composable () -> Unit)? = null,
) {
    Row(
        modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .clickable(onClick = onClick)
            .padding(vertical = 7.dp, horizontal = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(11.dp),
    ) {
        leading()
        Box(Modifier.weight(1f)) {
            Column {
                Text(
                    title,
                    color = if (isCurrent) MekambColors.Accent else MekambColors.TextPrimary,
                    fontSize = 13.5.sp,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    subtitle,
                    color = MekambColors.TextMuted,
                    fontSize = 11.5.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.padding(top = 2.dp),
                )
            }
        }
        trailing?.invoke()
    }
}

@Composable
fun FilterChipRow(options: List<String>, selected: String, onSelect: (String) -> Unit, modifier: Modifier = Modifier) {
    Row(modifier, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        options.forEach { option ->
            val active = option == selected
            Box(
                Modifier
                    .clip(RoundedCornerShape(16.dp))
                    .background(if (active) MekambColors.Accent.copy(alpha = 0.16f) else MekambColors.SurfaceAlt)
                    .clickable { onSelect(option) }
                    .padding(horizontal = 13.dp, vertical = 7.dp),
            ) {
                Text(
                    option,
                    color = if (active) MekambColors.Accent else MekambColors.TextMuted,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.SemiBold,
                )
            }
        }
    }
}

@Composable
fun MixBadge(modifier: Modifier = Modifier) {
    Box(
        modifier
            .clip(RoundedCornerShape(5.dp))
            .background(Color.Black.copy(alpha = 0.65f))
            .padding(horizontal = 6.dp, vertical = 2.dp),
    ) {
        Text("MIX", color = MekambColors.Accent, fontSize = 8.5.sp, fontWeight = FontWeight.ExtraBold)
    }
}

@Composable
fun ImportStatusChip(status: ImportStatus, modifier: Modifier = Modifier) {
    val color = when (status) {
        ImportStatus.Imported -> MekambColors.Success
        ImportStatus.Failed, ImportStatus.Canceled -> MekambColors.Danger
        else -> MekambColors.Accent
    }
    Box(modifier.clip(RoundedCornerShape(6.dp)).background(color.copy(alpha = 0.15f)).padding(horizontal = 8.dp, vertical = 4.dp)) {
        Text(
            status.raw.replace('_', ' ').uppercase(),
            color = color,
            fontSize = 9.5.sp,
            fontWeight = FontWeight.ExtraBold,
            letterSpacing = 0.5.sp,
        )
    }
}

fun formatDuration(seconds: Double?): String {
    val total = (seconds ?: 0.0).roundToInt().coerceAtLeast(0)
    val m = total / 60
    val s = total % 60
    return "$m:${s.toString().padStart(2, '0')}"
}

@Composable
fun BackIconButton(onClick: () -> Unit, modifier: Modifier = Modifier, tint: Color = MekambColors.TextPrimary, background: Color = Color(0x66101014)) {
    Box(
        modifier
            .size(34.dp)
            .clip(RoundedCornerShape(10.dp))
            .background(background)
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back", tint = tint, modifier = Modifier.size(17.dp))
    }
}

@Composable
fun BigPlayButton(isPlaying: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier, size: Dp = 54.dp) {
    Box(
        modifier
            .size(size)
            .clip(CircleShape)
            .background(MekambColors.Accent)
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Icon(
            if (isPlaying) Icons.Filled.Pause else Icons.Filled.PlayArrow,
            contentDescription = if (isPlaying) "Pause" else "Play",
            tint = MekambColors.BackgroundAlt,
            modifier = Modifier.size(size * 0.4f),
        )
    }
}

@Composable
fun CircleIconButton(icon: androidx.compose.ui.graphics.vector.ImageVector, onClick: () -> Unit, modifier: Modifier = Modifier, tint: Color = MekambColors.TextMuted, size: Dp = 42.dp) {
    Box(
        modifier
            .size(size)
            .clip(CircleShape)
            .background(Color.Transparent)
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Icon(icon, contentDescription = null, tint = tint, modifier = Modifier.size(size * 0.42f))
    }
}

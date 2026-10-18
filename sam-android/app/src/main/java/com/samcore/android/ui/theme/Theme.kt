package com.samcore.android.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable

// Dark-first per PDR §7 ("dark mode is the signature experience; light mode is
// designed intentionally") — this slice implements dark only; light is a
// deliberate follow-up, not an oversight.
private val SamDarkColors = darkColorScheme(
    primary = SamOrange,
    onPrimary = SamCharcoal,
    secondary = SamOrangeDim,
    background = SamCharcoal,
    surface = SamCharcoalElevated,
    onBackground = SamWarmWhite,
    onSurface = SamWarmWhite,
    surfaceVariant = SamCharcoalElevated,
    onSurfaceVariant = SamNeutralGray,
    error = SamError,
)

@Composable
fun SamTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = SamDarkColors,
        typography = SamTypography,
        content = content,
    )
}

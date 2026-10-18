package com.samcore.android.ui.theme

import androidx.compose.ui.graphics.Color

// Sampled directly from SAM_LOGO.png — not guessed. See PDR §7: orange is the
// identity/active-state accent, not a full-screen fill.
val SamOrange = Color(0xFFFD6902)
val SamOrangeDim = Color(0xFFC65402) // pressed/disabled state, derived (darker) from the sampled value

// PDR §7: "Deep charcoal/near-black and warm white/neutral surfaces." Dark-first
// per §7 ("dark mode is the signature experience"); values chosen to match
// Material3's own dark-surface guidance rather than pure black.
val SamCharcoal = Color(0xFF121212)
val SamCharcoalElevated = Color(0xFF1C1C1C)
val SamWarmWhite = Color(0xFFF5F1EC)
val SamNeutralGray = Color(0xFFB3ADA6)

val SamError = Color(0xFFCF6679)

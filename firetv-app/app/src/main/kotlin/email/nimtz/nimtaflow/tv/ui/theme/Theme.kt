package email.nimtz.nimtaflow.tv.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

// NimtaFlow brand colours — dark TV palette
val BgDark    = Color(0xFF0F0F13)
val Surface   = Color(0xFF18181B)
val SurfaceHi = Color(0xFF27272A)
val OnSurface = Color(0xFFE4E4E7)
val Muted     = Color(0xFFA1A1AA)
val Accent    = Color(0xFFA78BFA)   // violet-400
val AccentDim = Color(0xFF7C3AED)   // violet-600

private val DarkColors = darkColorScheme(
    primary   = Accent,
    secondary = AccentDim,
    background = BgDark,
    surface    = Surface,
    onPrimary  = Color.White,
    onBackground = OnSurface,
    onSurface    = OnSurface,
)

@Composable
fun NimtaFlowTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = DarkColors,
        content     = content,
    )
}

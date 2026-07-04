package email.nimtz.nimtaflow.tv.ui.player

import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.key.*
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.media3.common.MediaItem
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import coil.compose.AsyncImage
import coil.request.ImageRequest
import email.nimtz.nimtaflow.tv.api.APIClient
import email.nimtz.nimtaflow.tv.api.Photo
import email.nimtz.nimtaflow.tv.ui.theme.*

/**
 * Full-screen photo/video viewer. Swipe (or D-pad LEFT/RIGHT) to navigate.
 * Videos use ExoPlayer. Photos use Coil.
 * BACK key / menu button dismisses.
 */
@Composable
fun MediaViewerScreen(
    photos: List<Photo>,
    startIndex: Int,
    api: APIClient,
    token: String,
    onDismiss: () -> Unit,
) {
    val pagerState = rememberPagerState(initialPage = startIndex) { photos.size }

    Box(
        Modifier
            .fillMaxSize()
            .background(Color.Black)
            .onKeyEvent { e ->
                if (e.type == KeyEventType.KeyDown && e.key == Key.Back) {
                    onDismiss(); true
                } else false
            }
    ) {
        HorizontalPager(state = pagerState, modifier = Modifier.fillMaxSize()) { idx ->
            val photo = photos[idx]
            if (photo.isVideo) {
                VideoItem(api.streamUrl(photo.id))
            } else {
                PhotoItem(photo.id, api, token)
            }
        }

        // Close button (top-right)
        IconButton(
            onClick = onDismiss,
            modifier = Modifier.align(Alignment.TopEnd).padding(16.dp),
        ) {
            Icon(Icons.Default.Close, "Schließen", tint = Color.White, modifier = Modifier.size(32.dp))
        }

        // Page indicator (bottom-center)
        if (photos.size > 1) {
            Text(
                "${pagerState.currentPage + 1} / ${photos.size}",
                color = Color.White.copy(alpha = 0.7f),
                modifier = Modifier.align(Alignment.BottomCenter).padding(20.dp),
            )
        }
    }
}

@Composable
private fun PhotoItem(photoId: Int, api: APIClient, token: String) {
    val ctx = LocalContext.current
    AsyncImage(
        model = ImageRequest.Builder(ctx)
            .data(api.thumbUrl(photoId, "large"))
            .addHeader("Authorization", "Bearer $token")
            .crossfade(true)
            .build(),
        contentDescription = null,
        contentScale = ContentScale.Fit,
        modifier = Modifier.fillMaxSize().background(Color.Black),
    )
}

@Composable
private fun VideoItem(streamUrl: String) {
    val ctx = LocalContext.current
    val player = remember {
        ExoPlayer.Builder(ctx).build().also { p ->
            p.setMediaItem(MediaItem.fromUri(Uri.parse(streamUrl)))
            p.prepare()
            p.playWhenReady = true
        }
    }
    DisposableEffect(Unit) { onDispose { player.release() } }

    AndroidView(
        factory = { c ->
            PlayerView(c).also { pv ->
                pv.player = player
                pv.useController = true
            }
        },
        modifier = Modifier.fillMaxSize(),
    )
}

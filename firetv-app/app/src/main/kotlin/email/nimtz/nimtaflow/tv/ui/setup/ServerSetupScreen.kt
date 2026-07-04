package email.nimtz.nimtaflow.tv.ui.setup

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import email.nimtz.nimtaflow.tv.ui.theme.*

/**
 * First-run screen: user enters their NimtaFlow server URL.
 * On FireTV this is entered via the on-screen keyboard (D-pad navigable).
 * Example: http://192.168.0.193:8090  or  https://foto.example.com
 */
@Composable
fun ServerSetupScreen(onDone: (String) -> Unit) {
    var url by remember { mutableStateOf("http://") }
    var error by remember { mutableStateOf("") }
    val focus = remember { FocusRequester() }

    LaunchedEffect(Unit) { focus.requestFocus() }

    Box(
        Modifier
            .fillMaxSize()
            .background(BgDark),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            Modifier.width(640.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(24.dp),
        ) {
            Text("✦ NimtaFlow", color = Accent, fontSize = 26.sp, fontWeight = FontWeight.Bold)
            Text("Server-Adresse eingeben", color = OnSurface, fontSize = 22.sp, fontWeight = FontWeight.SemiBold)
            Text(
                "Trage die Adresse deines NimtaFlow-Servers ein.\nBeispiel: http://192.168.0.10:8090",
                color = Muted, fontSize = 14.sp,
            )

            OutlinedTextField(
                value = url,
                onValueChange = { url = it; error = "" },
                label = { Text("Server-URL", color = Muted) },
                singleLine = true,
                modifier = Modifier.fillMaxWidth().focusRequester(focus),
                keyboardOptions = KeyboardOptions(
                    keyboardType = KeyboardType.Uri,
                    imeAction = ImeAction.Done,
                ),
                keyboardActions = KeyboardActions(onDone = {
                    val trimmed = url.trim().trimEnd('/')
                    if (trimmed.startsWith("http")) onDone(trimmed)
                    else error = "URL muss mit http:// oder https:// beginnen"
                }),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedTextColor = OnSurface,
                    unfocusedTextColor = OnSurface,
                    focusedBorderColor = Accent,
                    unfocusedBorderColor = SurfaceHi,
                    cursorColor = Accent,
                ),
                isError = error.isNotEmpty(),
            )

            if (error.isNotEmpty()) {
                Text(error, color = MaterialTheme.colorScheme.error, fontSize = 13.sp)
            }

            Button(
                onClick = {
                    val trimmed = url.trim().trimEnd('/')
                    if (trimmed.startsWith("http")) onDone(trimmed)
                    else error = "URL muss mit http:// oder https:// beginnen"
                },
                colors = ButtonDefaults.buttonColors(containerColor = AccentDim),
                modifier = Modifier.fillMaxWidth().height(52.dp),
            ) {
                Text("Weiter", fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
            }
        }
    }
}

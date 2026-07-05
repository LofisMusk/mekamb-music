package pl.mekamb.music.desktop.ui.components

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.unit.dp
import pl.mekamb.music.desktop.ui.theme.MekambColors

/** Pill-shaped search input used across search/library screens. */
@Composable
fun SearchField(
    value: String,
    onValueChange: (String) -> Unit,
    placeholder: String,
    modifier: Modifier = Modifier,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        modifier = modifier,
        placeholder = { Text(text = placeholder, color = MekambColors.Muted) },
        leadingIcon = {
            Icon(imageVector = Icons.Filled.Search, contentDescription = null, tint = MekambColors.Muted)
        },
        singleLine = true,
        shape = RoundedCornerShape(20.dp),
        textStyle = TextStyle(color = MekambColors.Text),
        colors = OutlinedTextFieldDefaults.colors(
            focusedContainerColor = MekambColors.Chip,
            unfocusedContainerColor = MekambColors.Chip,
            disabledContainerColor = MekambColors.Chip,
            focusedBorderColor = MekambColors.Accent,
            unfocusedBorderColor = MekambColors.Chip,
            cursorColor = MekambColors.Accent,
            focusedTextColor = MekambColors.Text,
            unfocusedTextColor = MekambColors.Text,
        ),
    )
}

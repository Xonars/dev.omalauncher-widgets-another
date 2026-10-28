package com.apkmaker.hello_world

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            var count by rememberSaveable { mutableIntStateOf(0) }
            MaterialTheme(colorScheme = darkColorScheme()) {
                Scaffold { padding ->
                    Column(
                        Modifier.fillMaxSize().padding(padding).padding(24.dp),
                        verticalArrangement = Arrangement.spacedBy(16.dp, Alignment.CenterVertically),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Text("Hello World", style = MaterialTheme.typography.headlineLarge)
                        Text("Your first app, built on your phone.")
                        Text("Taps: $count", style = MaterialTheme.typography.headlineMedium)
                        Button(onClick = { if (count < Int.MAX_VALUE) count++ }) { Text("Say hello") }
                        OutlinedButton(onClick = { count = 0 }, enabled = count > 0) { Text("Reset") }
                        Text("Make it yours: return to APK Maker and describe a change.")
                    }
                }
            }
        }
    }
}

package com.jarvis.bridge

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log

class JarvisBridgeReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        if (intent == null) return
        val action = intent.action ?: return

        val serviceIntent = Intent(context, JarvisActionService::class.java).apply {
            this.action = action
            putExtras(intent.extras ?: android.os.Bundle())
        }

        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(serviceIntent)
            } else {
                context.startService(serviceIntent)
            }
        } catch (e: Exception) {
            Log.e("JarvisBridgeReceiver", "Failed to start service for action=$action", e)
        }
    }
}

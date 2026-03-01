package com.jarvis.bridge

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.IBinder
import android.telecom.TelecomManager
import android.telephony.SmsManager
import android.util.Log
import android.speech.tts.TextToSpeech
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import java.util.Locale

class JarvisActionService : Service(), TextToSpeech.OnInitListener {
    companion object {
        const val ACTION_TTS = "com.jarvis.TTS"
        const val ACTION_ANSWER_CALL_TTS = "com.jarvis.ANSWER_CALL_TTS"
        const val ACTION_SEND_MESSAGE = "com.jarvis.SEND_MESSAGE"

        private const val CHANNEL_ID = "jarvis_bridge_actions"
        private const val NOTIF_ID = 7101
    }

    private var tts: TextToSpeech? = null
    private var ttsReady = false

    override fun onCreate() {
        super.onCreate()
        ensureForeground()
        tts = TextToSpeech(this, this)
    }

    override fun onDestroy() {
        tts?.stop()
        tts?.shutdown()
        tts = null
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent == null) return START_NOT_STICKY

        when (intent.action) {
            ACTION_TTS -> {
                val text = intent.getStringExtra("text").orEmpty()
                speak(text)
            }
            ACTION_ANSWER_CALL_TTS -> {
                val script = intent.getStringExtra("script").orEmpty()
                answerRingingCall()
                speak(script)
            }
            ACTION_SEND_MESSAGE -> {
                val contact = intent.getStringExtra("contact").orEmpty()
                val text = intent.getStringExtra("text").orEmpty()
                sendSms(contact, text)
            }
            else -> {
                Log.w("JarvisActionService", "Unknown action: ${intent.action}")
            }
        }

        stopSelf(startId)
        return START_NOT_STICKY
    }

    override fun onInit(status: Int) {
        if (status == TextToSpeech.SUCCESS) {
            tts?.language = Locale.US
            ttsReady = true
        } else {
            Log.e("JarvisActionService", "TTS init failed: $status")
        }
    }

    private fun speak(text: String) {
        if (text.isBlank()) return
        if (!ttsReady) {
            Log.w("JarvisActionService", "TTS not ready, skipping speech")
            return
        }
        tts?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "jarvis_bridge_utt")
    }

    private fun answerRingingCall() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ANSWER_PHONE_CALLS)
            != PackageManager.PERMISSION_GRANTED
        ) {
            Log.w("JarvisActionService", "ANSWER_PHONE_CALLS permission missing")
            return
        }
        try {
            val telecomManager = getSystemService(Context.TELECOM_SERVICE) as TelecomManager
            telecomManager.acceptRingingCall()
        } catch (e: Exception) {
            Log.e("JarvisActionService", "Failed to answer call", e)
        }
    }

    private fun sendSms(contact: String, text: String) {
        if (contact.isBlank() || text.isBlank()) {
            Log.w("JarvisActionService", "SMS contact/text missing")
            return
        }
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.SEND_SMS)
            != PackageManager.PERMISSION_GRANTED
        ) {
            Log.w("JarvisActionService", "SEND_SMS permission missing")
            return
        }
        try {
            val smsManager = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                getSystemService(SmsManager::class.java)
            } else {
                @Suppress("DEPRECATION")
                SmsManager.getDefault()
            }
            smsManager.sendTextMessage(contact, null, text, null, null)
        } catch (e: Exception) {
            Log.e("JarvisActionService", "SMS send failed", e)
        }
    }

    private fun ensureForeground() {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "JARVIS Bridge Actions",
                NotificationManager.IMPORTANCE_LOW
            )
            nm.createNotificationChannel(channel)
        }

        val launchIntent = packageManager.getLaunchIntentForPackage(packageName)
        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            launchIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val notification: Notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_notify_sync)
            .setContentTitle("JARVIS Bridge")
            .setContentText("Listening for automation actions")
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .build()

        startForeground(NOTIF_ID, notification)
    }
}

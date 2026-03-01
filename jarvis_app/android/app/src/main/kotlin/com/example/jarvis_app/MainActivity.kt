package com.example.jarvis_app

import android.Manifest
import android.app.ActivityManager
import android.content.ComponentName
import android.content.ActivityNotFoundException
import android.content.BroadcastReceiver
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.media.AudioManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.provider.ContactsContract
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.speech.tts.Voice
import androidx.core.content.ContextCompat
import com.example.jarvis_app.accessibility.JarvisAccessibilityService
import com.example.jarvis_app.call.CallAssistantService
import com.example.jarvis_app.notification.JarvisNotificationListenerService
import com.example.jarvis_app.storage.CallLogDb
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodChannel
import java.net.URLEncoder
import java.util.Locale

class MainActivity : FlutterActivity() {
    private companion object {
        const val PREFS_NAME = "jarvis_prefs"
        const val KEY_CUSTOM_MESSAGE = "call_custom_message"
        const val KEY_ANSWER_DELAY = "call_answer_delay_ms"
        const val KEY_PC_IP = "call_pc_ip"
        const val KEY_AUTOSTART = "call_guard_autostart"
        const val KEY_VOICE_GENDER = "call_voice_gender"
        const val DEFAULT_CUSTOM_MESSAGE =
            "Pavan is currently busy and cannot take your call right now. Please leave a note after the beep."
        const val DEFAULT_ANSWER_DELAY = 4000L
        const val DEFAULT_PC_IP = "192.168.1.100"
        const val DEFAULT_VOICE_GENDER = "male"
    }

    private val callMethodChannel = "com.jarvis.app/call_service"
    private val callEventsChannel = "com.jarvis.app/call_events"
    private val newRecordAction = "com.jarvis.app.NEW_CALL_RECORD"

    private var callEventsSink: EventChannel.EventSink? = null
    private var callRecordReceiver: BroadcastReceiver? = null
    private var appTts: TextToSpeech? = null
    private var appTtsReady = false
    private var appTtsInitInProgress = false
    private var appTtsPendingResult: MethodChannel.Result? = null
    private var appTtsUtteranceId: String? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, callMethodChannel)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "startCallService" -> {
                        startCallService()
                        result.success(true)
                    }
                    "stopCallService" -> {
                        stopCallService()
                        result.success(true)
                    }
                    "isCallServiceRunning" -> result.success(isServiceRunning(CallAssistantService::class.java.name))
                    "getAllCallRecords" -> result.success(CallLogDb(this).getAllAsMaps())
                    "getImportantCallRecords" -> result.success(CallLogDb(this).getImportantUnreadAsMaps())
                    "markCallRead" -> {
                        val id = call.argument<Number>("id")?.toLong() ?: 0L
                        CallLogDb(this).markRead(id)
                        result.success(true)
                    }
                    "deleteCallRecord" -> {
                        val id = call.argument<Number>("id")?.toLong() ?: 0L
                        CallLogDb(this).deleteRecord(id)
                        result.success(true)
                    }
                    "setCustomMessage" -> {
                        val message = call.argument<String>("message") ?: ""
                        prefs()
                            .edit()
                            .putString(KEY_CUSTOM_MESSAGE, message)
                            .apply()
                        result.success(true)
                    }
                    "setAnswerDelay" -> {
                        val delayMs = call.argument<Number>("delay_ms")?.toLong() ?: DEFAULT_ANSWER_DELAY
                        prefs()
                            .edit()
                            .putLong(KEY_ANSWER_DELAY, delayMs)
                            .apply()
                        result.success(true)
                    }
                    "setPcIp" -> {
                        val ip = call.argument<String>("ip") ?: ""
                        prefs()
                            .edit()
                            .putString(KEY_PC_IP, ip)
                            .apply()
                        result.success(true)
                    }
                    "setCallAutostart" -> {
                        val enabled = call.argument<Boolean>("enabled") ?: false
                        prefs()
                            .edit()
                            .putBoolean(KEY_AUTOSTART, enabled)
                            .apply()
                        result.success(true)
                    }
                    "setCallVoiceGender" -> {
                        prefs()
                            .edit()
                            .putString(KEY_VOICE_GENDER, "male")
                            .apply()
                        result.success(true)
                    }
                    "getCallAutostart" -> {
                        val value = prefs().getBoolean(KEY_AUTOSTART, false)
                        result.success(value)
                    }
                    "getCallVoiceGender" -> result.success("male")
                    "getCustomMessage" -> result.success(
                        prefs().getString(KEY_CUSTOM_MESSAGE, DEFAULT_CUSTOM_MESSAGE) ?: DEFAULT_CUSTOM_MESSAGE
                    )
                    "getAnswerDelay" -> result.success(
                        prefs().getLong(KEY_ANSWER_DELAY, DEFAULT_ANSWER_DELAY)
                    )
                    "getPcIp" -> result.success(
                        prefs().getString(KEY_PC_IP, DEFAULT_PC_IP) ?: DEFAULT_PC_IP
                    )
                    "openAccessibilitySettings" -> {
                        val intent = Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)
                        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                        startActivity(intent)
                        result.success(true)
                    }
                    "openNotificationAccessSettings" -> {
                        val intent = Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)
                        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                        startActivity(intent)
                        result.success(true)
                    }
                    "openAppPermissionSettings" -> {
                        val intent = Intent(
                            Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                            Uri.fromParts("package", packageName, null),
                        )
                        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                        startActivity(intent)
                        result.success(true)
                    }
                    "isAccessibilityServiceEnabled" -> result.success(isAccessibilityServiceEnabled())
                    "isNotificationAccessEnabled" -> result.success(isNotificationAccessEnabled())
                    "speakMaleNative" -> {
                        val text = call.argument<String>("text") ?: ""
                        speakMaleNative(text, result)
                    }
                    "stopMaleNative" -> {
                        stopMaleNative()
                        result.success(true)
                    }
                    "sendWhatsAppNative" -> {
                        val recipient = call.argument<String>("recipient") ?: ""
                        val message = call.argument<String>("message") ?: ""
                        result.success(sendWhatsAppNative(recipient, message))
                    }
                    "sendInstagramNative" -> {
                        val recipient = call.argument<String>("recipient") ?: ""
                        val message = call.argument<String>("message") ?: ""
                        result.success(sendInstagramNative(recipient, message))
                    }
                    "openWhatsAppNative" -> result.success(openWhatsAppNative())
                    "openInstagramNative" -> result.success(openInstagramNative())
                    else -> result.notImplemented()
                }
            }

        EventChannel(flutterEngine.dartExecutor.binaryMessenger, callEventsChannel)
            .setStreamHandler(object : EventChannel.StreamHandler {
                override fun onListen(arguments: Any?, events: EventChannel.EventSink?) {
                    callEventsSink = events
                    registerCallRecordReceiver()
                }

                override fun onCancel(arguments: Any?) {
                    unregisterCallRecordReceiver()
                    callEventsSink = null
                }
            })
    }

    private fun prefs() = getSharedPreferences(PREFS_NAME, MODE_PRIVATE)

    private fun normalizePhone(value: String): String {
        return value.filter { it.isDigit() }
    }

    private fun hasContactsPermission(): Boolean {
        return ContextCompat.checkSelfPermission(this, Manifest.permission.READ_CONTACTS) == PackageManager.PERMISSION_GRANTED
    }

    private fun resolvePhoneFromContactName(name: String): String? {
        if (!hasContactsPermission()) return null
        val q = name.trim()
        if (q.isBlank()) return null
        val resolver = contentResolver
        val projection = arrayOf(
            ContactsContract.CommonDataKinds.Phone.NUMBER,
            ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME,
        )
        val selection = "${ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME} LIKE ?"
        val selectionArgs = arrayOf("%$q%")
        resolver.query(
            ContactsContract.CommonDataKinds.Phone.CONTENT_URI,
            projection,
            selection,
            selectionArgs,
            null,
        )?.use { cursor ->
            val numberCol = cursor.getColumnIndex(ContactsContract.CommonDataKinds.Phone.NUMBER)
            while (cursor.moveToNext()) {
                if (numberCol >= 0) {
                    val raw = cursor.getString(numberCol) ?: ""
                    val normalized = normalizePhone(raw)
                    if (normalized.length >= 7) return normalized
                }
            }
        }
        return null
    }

    private fun openWhatsAppNative(): Boolean {
        return tryStartIntents(
            listOf(
                Intent(Intent.ACTION_VIEW, Uri.parse("whatsapp://send")).apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    `package` = "com.whatsapp"
                },
                Intent(Intent.ACTION_VIEW, Uri.parse("https://wa.me/")).apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    `package` = "com.whatsapp"
                },
                Intent(Intent.ACTION_VIEW, Uri.parse("https://wa.me/")).apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                },
            ),
        )
    }

    private fun openInstagramNative(): Boolean {
        return tryStartIntents(
            listOf(
                Intent(Intent.ACTION_VIEW, Uri.parse("instagram://direct/inbox")).apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    `package` = "com.instagram.android"
                },
                Intent(Intent.ACTION_VIEW, Uri.parse("https://instagram.com/direct/inbox/")).apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    `package` = "com.instagram.android"
                },
                Intent(Intent.ACTION_VIEW, Uri.parse("https://instagram.com/")).apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                },
            ),
        )
    }

    private fun tryStartIntents(intents: List<Intent>): Boolean {
        for (intent in intents) {
            try {
                startActivity(intent)
                return true
            } catch (_: Exception) {
            }
        }
        return false
    }

    private fun isAccessibilityServiceEnabled(): Boolean {
        val enabled = Settings.Secure.getString(
            contentResolver,
            Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES,
        ) ?: return false
        val target = ComponentName(this, JarvisAccessibilityService::class.java)
        val full = target.flattenToString()
        val short = target.flattenToShortString()
        return enabled.split(':').any {
            it.equals(full, ignoreCase = true) || it.equals(short, ignoreCase = true)
        }
    }

    private fun isNotificationAccessEnabled(): Boolean {
        val enabled = Settings.Secure.getString(
            contentResolver,
            "enabled_notification_listeners",
        ) ?: return false

        val target = ComponentName(this, JarvisNotificationListenerService::class.java)
        val full = target.flattenToString()
        val short = target.flattenToShortString()
        return enabled.split(':').any {
            it.equals(full, ignoreCase = true) || it.equals(short, ignoreCase = true)
        }
    }

    private fun ensureAppTtsReady(onReady: (Boolean) -> Unit) {
        val existing = appTts
        if (appTtsReady && existing != null) {
            onReady(true)
            return
        }
        if (appTtsInitInProgress) {
            window.decorView.postDelayed({ ensureAppTtsReady(onReady) }, 80L)
            return
        }

        appTtsInitInProgress = true
        appTts = TextToSpeech(applicationContext) { status ->
            appTtsInitInProgress = false
            val tts = appTts
            if (status != TextToSpeech.SUCCESS || tts == null) {
                appTtsReady = false
                onReady(false)
                return@TextToSpeech
            }
            tts.language = Locale.US
            val voiceSet = trySetPreferredMaleVoice(tts)
            tts.setSpeechRate(0.90f)
            tts.setPitch(if (voiceSet) 0.66f else 0.60f)
            tts.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                override fun onStart(utteranceId: String?) {}

                override fun onDone(utteranceId: String?) {
                    runOnUiThread {
                        if (appTtsUtteranceId == utteranceId) {
                            appTtsPendingResult?.success(true)
                            appTtsPendingResult = null
                            appTtsUtteranceId = null
                        }
                    }
                }

                override fun onError(utteranceId: String?) {
                    runOnUiThread {
                        if (appTtsUtteranceId == utteranceId) {
                            appTtsPendingResult?.success(false)
                            appTtsPendingResult = null
                            appTtsUtteranceId = null
                        }
                    }
                }
            })
            appTtsReady = true
            onReady(true)
        }
    }

    private fun trySetPreferredMaleVoice(tts: TextToSpeech): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.LOLLIPOP) {
            return false
        }
        try {
            val voices = tts.voices ?: return false
            if (voices.isEmpty()) return false

            val exactPreferred = listOf(
                "en-us-x-iob-local",
                "en-us-x-ioc-local",
                "en-us-x-iod-local",
                "en-us-x-iol-local",
                "en-us-x-iom-local",
                "en-us-x-iob-network",
                "en-us-x-ioc-network",
                "en-us-x-iod-network",
                "en-us-x-iol-network",
                "en-us-x-iom-network",
            )
            for (preferred in exactPreferred) {
                val exact = voices.firstOrNull {
                    val name = (it.name ?: "").lowercase(Locale.US)
                    val locale = it.locale
                    name == preferred &&
                        locale != null &&
                        "en".equals(locale.language, ignoreCase = true)
                }
                if (exact != null && tts.setVoice(exact) == TextToSpeech.SUCCESS) {
                    return true
                }
            }

            val maleHints = listOf("male", "m1", "m2", "iob", "ioc", "iod", "iol", "iom")
            val femaleHints = listOf("female", "f1", "f2", "ioa", "iof", "iog", "ioh", "ioj", "iok")
            var best: Voice? = null
            var bestScore = Int.MIN_VALUE
            for (voice in voices) {
                val locale = voice.locale ?: continue
                if (!"en".equals(locale.language, ignoreCase = true)) continue
                if (voice.features?.contains("notInstalled") == true) continue
                val name = (voice.name ?: "").lowercase(Locale.US)
                var score = 0
                if ("US".equals(locale.country, ignoreCase = true)) score += 20
                if (!voice.isNetworkConnectionRequired) score += 10
                if (maleHints.any { name.contains(it) }) score += 45
                if (femaleHints.any { name.contains(it) }) score -= 70
                if (score > bestScore) {
                    bestScore = score
                    best = voice
                }
            }
            if (best != null) {
                return tts.setVoice(best) == TextToSpeech.SUCCESS
            }
        } catch (_: Exception) {
        }
        return false
    }

    private fun speakMaleNative(textRaw: String, result: MethodChannel.Result) {
        val text = textRaw.trim()
        if (text.isEmpty()) {
            result.success(false)
            return
        }

        ensureAppTtsReady { ready ->
            if (!ready) {
                result.success(false)
                return@ensureAppTtsReady
            }
            val tts = appTts
            if (tts == null) {
                result.success(false)
                return@ensureAppTtsReady
            }

            trySetPreferredMaleVoice(tts)
            tts.setSpeechRate(0.90f)
            tts.setPitch(0.66f)

            appTtsPendingResult?.success(false)
            appTtsPendingResult = result
            val utteranceId = "male_${System.currentTimeMillis()}"
            appTtsUtteranceId = utteranceId

            val speakStatus = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
                val params = Bundle().apply {
                    putInt(TextToSpeech.Engine.KEY_PARAM_STREAM, AudioManager.STREAM_MUSIC)
                }
                tts.speak(text, TextToSpeech.QUEUE_FLUSH, params, utteranceId)
            } else {
                @Suppress("DEPRECATION")
                tts.speak(text, TextToSpeech.QUEUE_FLUSH, hashMapOf(
                    TextToSpeech.Engine.KEY_PARAM_UTTERANCE_ID to utteranceId,
                ))
            }

            if (speakStatus != TextToSpeech.SUCCESS) {
                appTtsPendingResult = null
                appTtsUtteranceId = null
                result.success(false)
            }
        }
    }

    private fun stopMaleNative() {
        try {
            appTts?.stop()
        } catch (_: Exception) {
        }
        appTtsPendingResult?.success(false)
        appTtsPendingResult = null
        appTtsUtteranceId = null
    }

    private fun sendWhatsAppNative(recipientRaw: String, messageRaw: String): Map<String, Any?> {
        val message = messageRaw.trim()
        if (message.isBlank()) {
            return mapOf(
                "success" to false,
                "platform" to "whatsapp",
                "error" to "Message is empty.",
            )
        }

        val recipient = recipientRaw.trim()
        var targetNumber = normalizePhone(recipient)
        if (targetNumber.length < 7 && recipient.isNotBlank()) {
            val resolved = resolvePhoneFromContactName(recipient)
            if (resolved != null) {
                targetNumber = resolved
            } else if (!hasContactsPermission()) {
                return mapOf(
                    "success" to false,
                    "platform" to "whatsapp",
                    "error" to "Grant Contacts permission to resolve names, or use a phone number.",
                )
            }
        }
        if (targetNumber.length < 7) {
            return mapOf(
                "success" to false,
                "platform" to "whatsapp",
                "error" to "Invalid recipient. Use a phone number or saved contact name.",
            )
        }

        val encoded = URLEncoder.encode(message, "UTF-8")
        val intents = listOf(
            Intent(Intent.ACTION_VIEW, Uri.parse("whatsapp://send?phone=$targetNumber&text=$encoded")).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                `package` = "com.whatsapp"
            },
            Intent(Intent.ACTION_VIEW, Uri.parse("https://wa.me/$targetNumber?text=$encoded")).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                `package` = "com.whatsapp"
            },
            Intent(Intent.ACTION_VIEW, Uri.parse("https://wa.me/$targetNumber?text=$encoded")).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            },
        )

        return try {
            val opened = tryStartIntents(intents)
            if (opened) {
                val queued = JarvisAccessibilityService.enqueueOutgoingMessage(
                    "whatsapp",
                    if (recipient.isNotBlank()) recipient else targetNumber,
                    message,
                    false,
                )
                mapOf(
                    "success" to true,
                    "platform" to "whatsapp",
                    "to" to targetNumber,
                    "native" to true,
                    "auto_send" to queued,
                    "speech" to if (queued) {
                        "Opening WhatsApp chat with $recipient. Sending now."
                    } else {
                        "Opening WhatsApp chat with $recipient. Message is prefilled."
                    },
                )
            } else {
                mapOf(
                    "success" to false,
                    "platform" to "whatsapp",
                    "error" to "Failed to open WhatsApp.",
                )
            }
        } catch (ex: ActivityNotFoundException) {
            mapOf(
                "success" to false,
                "platform" to "whatsapp",
                "error" to (ex.message ?: "WhatsApp is not installed."),
            )
        } catch (ex: Exception) {
            mapOf(
                "success" to false,
                "platform" to "whatsapp",
                "error" to (ex.message ?: "Failed to open WhatsApp."),
            )
        }
    }

    private fun sendInstagramNative(recipientRaw: String, messageRaw: String): Map<String, Any?> {
        val recipient = recipientRaw.trim().trimStart('@')
        val message = messageRaw.trim()
        if (message.isBlank()) {
            return mapOf(
                "success" to false,
                "platform" to "instagram",
                "error" to "Message is empty.",
            )
        }
        if (message.isNotBlank()) {
            val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            clipboard.setPrimaryClip(ClipData.newPlainText("JARVIS Message", message))
        }
        val targetUrl = if (recipient.isBlank()) {
            "https://instagram.com/direct/inbox/"
        } else {
            "https://instagram.com/$recipient/"
        }
        val intents = listOf(
            Intent(Intent.ACTION_VIEW, Uri.parse("instagram://direct/inbox")).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                `package` = "com.instagram.android"
            },
            Intent(Intent.ACTION_VIEW, Uri.parse(targetUrl)).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                `package` = "com.instagram.android"
            },
            Intent(Intent.ACTION_VIEW, Uri.parse(targetUrl)).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            },
        )

        return try {
            val opened = tryStartIntents(intents)
            if (opened) {
                val queued = if (recipient.isBlank()) {
                    false
                } else {
                    JarvisAccessibilityService.enqueueOutgoingMessage(
                        "instagram",
                        recipient,
                        message,
                        false,
                    )
                }
                mapOf(
                    "success" to true,
                    "platform" to "instagram",
                    "to" to recipient,
                    "native" to true,
                    "auto_send" to queued,
                    "speech" to if (queued) {
                        if (recipient.isBlank()) {
                            "Opening Instagram inbox and sending now."
                        } else {
                            "Opening Instagram and sending to @$recipient."
                        }
                    } else {
                        if (recipient.isBlank()) {
                            "Opening Instagram inbox. Message copied to clipboard."
                        } else {
                            "Opening Instagram. Message copied to clipboard for paste to @$recipient."
                        }
                    },
                )
            } else {
                mapOf(
                    "success" to false,
                    "platform" to "instagram",
                    "error" to "Failed to open Instagram.",
                )
            }
        } catch (ex: ActivityNotFoundException) {
            mapOf(
                "success" to false,
                "platform" to "instagram",
                "error" to (ex.message ?: "Instagram is not installed."),
            )
        } catch (ex: Exception) {
            mapOf(
                "success" to false,
                "platform" to "instagram",
                "error" to (ex.message ?: "Failed to open Instagram."),
            )
        }
    }

    private fun startCallService() {
        val intent = Intent(this, CallAssistantService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent)
        } else {
            startService(intent)
        }
    }

    private fun stopCallService() {
        val intent = Intent(this, CallAssistantService::class.java)
        intent.action = CallAssistantService.ACTION_STOP
        startService(intent)
    }


    private fun registerCallRecordReceiver() {
        if (callRecordReceiver != null) return
        callRecordReceiver = object : BroadcastReceiver() {
            override fun onReceive(context: Context?, intent: Intent?) {
                val payload = hashMapOf<String, Any?>(
                    "record_id" to intent?.getLongExtra("record_id", -1L),
                    "important" to intent?.getBooleanExtra("important", false),
                )
                runOnUiThread { callEventsSink?.success(payload) }
            }
        }
        val filter = IntentFilter(newRecordAction)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(callRecordReceiver, filter, Context.RECEIVER_NOT_EXPORTED)
        } else {
            registerReceiver(callRecordReceiver, filter)
        }
    }

    private fun unregisterCallRecordReceiver() {
        if (callRecordReceiver == null) return
        unregisterReceiver(callRecordReceiver)
        callRecordReceiver = null
    }

    private fun isServiceRunning(className: String): Boolean {
        val manager = getSystemService(Context.ACTIVITY_SERVICE) as? ActivityManager ?: return false
        @Suppress("DEPRECATION")
        return manager.getRunningServices(Int.MAX_VALUE).any { it.service.className == className }
    }

    override fun onDestroy() {
        try {
            appTts?.stop()
            appTts?.shutdown()
        } catch (_: Exception) {
        }
        appTts = null
        appTtsReady = false
        appTtsInitInProgress = false
        appTtsPendingResult = null
        appTtsUtteranceId = null
        unregisterCallRecordReceiver()
        super.onDestroy()
    }
}

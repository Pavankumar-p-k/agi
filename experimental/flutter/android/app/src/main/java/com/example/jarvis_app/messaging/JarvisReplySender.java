// android/java/JarvisReplySender.java
// Sends replies back via WhatsApp/Instagram/SMS notification actions
// or falls back to ADB tap automation

package com.example.jarvis_app.messaging;

import android.app.PendingIntent;
import android.app.RemoteInput;
import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.provider.Settings;
import android.util.Log;

import androidx.core.app.NotificationCompat;

import io.flutter.plugin.common.MethodCall;
import io.flutter.plugin.common.MethodChannel;

import java.util.HashMap;
import java.util.Map;

public class JarvisReplySender implements MethodChannel.MethodCallHandler {

    private static final String TAG = "JarvisReplySender";

    // Platform package names
    private static final Map<String, String> PACKAGES = new HashMap<String, String>() {{
        put("whatsapp",  "com.whatsapp");
        put("instagram", "com.instagram.android");
        put("telegram",  "org.telegram.messenger");
        put("sms",       "com.google.android.apps.messaging");
    }};

    private final Context _ctx;

    public JarvisReplySender(Context ctx) {
        this._ctx = ctx;
    }

    // ── Called from Flutter via MethodChannel ─────────────────
    @Override
    public void onMethodCall(MethodCall call, MethodChannel.Result result) {
        switch (call.method) {
            case "sendReply":
                String sender   = call.argument("sender");
                String platform = call.argument("platform");
                String cacheKey = call.argument("cache_key");
                String text     = call.argument("text");
                boolean sent = sendReply(sender, platform, cacheKey, text);
                result.success(sent);
                break;
            case "openNotificationAccessSettings":
                openNotificationAccessSettings();
                result.success(true);
                break;
            case "openAccessibilitySettings":
                openAccessibilitySettings();
                result.success(true);
                break;
            case "isNotificationAccessEnabled":
                result.success(isNotificationAccessEnabled());
                break;
            case "isAccessibilityEnabled":
                result.success(isAccessibilityEnabled());
                break;
            default:
                result.notImplemented();
        }
    }

    // ── Main reply method ─────────────────────────────────────

    public boolean sendReply(String sender, String platform, String cacheKey, String text) {
        Log.d(TAG, "Sending reply to " + sender + " on " + platform + " (cache=" + cacheKey + "): " + text);

        // Method 1: Reply via active notification RemoteInput (most reliable)
        boolean sent = _replyViaNotification(cacheKey, text);
        if (sent) return true;

        // Method 2: Broadcast to notification listener (fallback)
        Intent intent = new Intent("com.example.jarvis_app.SEND_REPLY");
        intent.putExtra("sender",   sender);
        intent.putExtra("platform", platform);
        intent.putExtra("cache_key", cacheKey);
        intent.putExtra("text",     text);
        _ctx.sendBroadcast(intent);

        Log.d(TAG, "Reply broadcast sent");
        return true;
    }

    // ── Reply via notification RemoteInput ─────────────────────
    // This is how WhatsApp inline reply works in notification shade

    private boolean _replyViaNotification(String cacheKey, String text) {
        try {
            // Get the stored pending intent + RemoteInput array
            NotificationReplyCache.ReplyAction reply =
                NotificationReplyCache.get(cacheKey);
            if (reply == null) {
                Log.d(TAG, "No cached reply action for " + cacheKey);
                return false;
            }

            PendingIntent replyIntent = reply.pendingIntent;
            RemoteInput[] remoteInputs = reply.remoteInputs;
            if (replyIntent == null || remoteInputs == null || remoteInputs.length == 0) {
                Log.d(TAG, "Reply action missing for cacheKey=" + cacheKey);
                return false;
            }

            // Fill RemoteInput with our text
            Bundle remoteInputData = new Bundle();
            String key = remoteInputs[0].getResultKey();
            remoteInputData.putCharSequence(key, text);

            Intent fillInIntent = new Intent();
            RemoteInput.addResultsToIntent(remoteInputs, fillInIntent, remoteInputData);

            // Send the pending intent
            replyIntent.send(_ctx, 0, fillInIntent);
            Log.d(TAG, "Reply sent via RemoteInput ✓");
            return true;

        } catch (Exception e) {
            Log.e(TAG, "RemoteInput reply failed: " + e.getMessage());
            return false;
        }
    }

    // ── SMS reply via Android SMS API ─────────────────────────

    public boolean sendSMS(String phoneNumber, String text) {
        try {
            android.telephony.SmsManager sms =
                android.telephony.SmsManager.getDefault();
            sms.sendTextMessage(phoneNumber, null, text, null, null);
            Log.d(TAG, "SMS sent to " + phoneNumber);
            return true;
        } catch (Exception e) {
            Log.e(TAG, "SMS failed: " + e.getMessage());
            return false;
        }
    }

    private void openNotificationAccessSettings() {
        Intent intent = new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS);
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        _ctx.startActivity(intent);
    }

    private void openAccessibilitySettings() {
        Intent intent = new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS);
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        _ctx.startActivity(intent);
    }

    private boolean isNotificationAccessEnabled() {
        String enabled = Settings.Secure.getString(
            _ctx.getContentResolver(),
            "enabled_notification_listeners"
        );
        if (enabled == null) return false;
        return enabled.contains(_ctx.getPackageName());
    }

    private boolean isAccessibilityEnabled() {
        String enabled = Settings.Secure.getString(
            _ctx.getContentResolver(),
            Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES
        );
        if (enabled == null) return false;
        return enabled.contains(_ctx.getPackageName());
    }
}


// ── Notification Reply Cache ──────────────────────────────────
// Stores pending intents from incoming notifications
// so we can reply to them later

class NotificationReplyCache {
    private static final long CACHE_TTL_MS = 60_000; // 1 minute

    static class ReplyAction {
        final PendingIntent pendingIntent;
        final RemoteInput[] remoteInputs;
        final long storedAtMs;

        ReplyAction(PendingIntent intent, RemoteInput[] inputs) {
            this.pendingIntent = intent;
            this.remoteInputs = inputs;
            this.storedAtMs = System.currentTimeMillis();
        }

        boolean isExpired() {
            return (System.currentTimeMillis() - storedAtMs) > CACHE_TTL_MS;
        }
    }

    private static final Map<String, ReplyAction> _cache = new HashMap<>();

    public static void store(String cacheKey,
                             PendingIntent replyIntent,
                             RemoteInput[] remoteInputs) {
        _cache.put(cacheKey, new ReplyAction(replyIntent, remoteInputs));
    }

    public static ReplyAction get(String cacheKey) {
        ReplyAction action = _cache.get(cacheKey);
        if (action == null) return null;
        if (action.isExpired()) {
            _cache.remove(cacheKey);
            return null;
        }
        return action;
    }

    public static void clear(String cacheKey) {
        _cache.remove(cacheKey);
    }
}

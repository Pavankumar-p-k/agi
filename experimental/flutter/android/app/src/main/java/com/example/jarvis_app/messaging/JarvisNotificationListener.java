package com.example.jarvis_app.messaging;

import android.app.Notification;
import android.app.PendingIntent;
import android.app.RemoteInput;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.Bundle;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;
import android.text.TextUtils;
import android.util.Log;

import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class JarvisNotificationListener extends NotificationListenerService {

    private static final String TAG = "JarvisNotifListener";
    private static final String ACTION_SEND_REPLY = "com.example.jarvis_app.SEND_REPLY";

    private static final Map<String, String> PLATFORM_BY_PKG =
        new HashMap<String, String>() {{
            put("com.whatsapp", "whatsapp");
            put("com.whatsapp.w4b", "whatsapp");
            put("com.instagram.android", "instagram");
            put("org.telegram.messenger", "telegram");
            put("org.thoughtcrime.securesms", "signal");
            put("com.facebook.orca", "messenger");
            put("com.facebook.mlite", "messenger");
            put("com.google.android.apps.messaging", "sms");
            put("com.android.mms", "sms");
            put("com.viber.voip", "viber");
            put("com.microsoft.teams", "teams");
            put("com.discord", "discord");
        }};

    private BroadcastReceiver _replyReceiver;

    @Override
    public void onCreate() {
        super.onCreate();
        _replyReceiver = new BroadcastReceiver() {
            @Override
            public void onReceive(Context context, Intent intent) {
                if (ACTION_SEND_REPLY.equals(intent.getAction())) {
                    String cacheKey = intent.getStringExtra("cache_key");
                    String text = intent.getStringExtra("text");
                    if (cacheKey != null && text != null) {
                        _replyToCachedAction(cacheKey, text);
                    }
                }
            }
        };
        IntentFilter filter = new IntentFilter(ACTION_SEND_REPLY);
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(_replyReceiver, filter, Context.RECEIVER_NOT_EXPORTED);
        } else {
            registerReceiver(_replyReceiver, filter);
        }
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        try { unregisterReceiver(_replyReceiver); } catch (Exception ignored) {}
    }

    @Override
    public void onNotificationPosted(StatusBarNotification sbn) {
        if (sbn == null) return;

        // Ignore our own notifications to avoid loops
        if (getPackageName().equals(sbn.getPackageName())) return;

        String pkg = sbn.getPackageName();
        String platform = getPlatform(pkg);

        Notification n = sbn.getNotification();
        if (n == null) return;

        String sender = extractSender(n);
        String message = extractMessage(n);
        if (message.trim().isEmpty()) return;

        String cacheKey = sbn.getKey() != null ? sbn.getKey() : sender + "_" + platform;

        // Cache reply action (RemoteInput) if present
        boolean canReply = cacheReplyAction(n, cacheKey);

        // If we already have a cached action from earlier, we can reply too
        if (!canReply && NotificationReplyCache.get(cacheKey) != null) {
            canReply = true;
        }

        JarvisMessageBridge.emit(sender, platform, message, canReply, cacheKey);
        Log.d(TAG, "Msg: " + sender + " [" + platform + "]: " + message + " (canReply=" + canReply + ")");
    }

    private String getPlatform(String pkg) {
        String p = PLATFORM_BY_PKG.get(pkg);
        if (p != null) return p;
        if (pkg.contains("whatsapp")) return "whatsapp";
        if (pkg.contains("instagram")) return "instagram";
        if (pkg.contains("telegram")) return "telegram";
        if (pkg.contains("messenger") || pkg.contains("facebook")) return "messenger";
        if (pkg.contains("signal")) return "signal";
        if (pkg.contains("viber")) return "viber";
        if (pkg.contains("discord")) return "discord";
        if (pkg.contains("sms") || pkg.contains("mms")) return "sms";
        if (pkg.contains("teams")) return "teams";
        // Fallback to package name (sanitized) so we can still track and reply
        return pkg.replace('.', '_');
    }

    private String extractSender(Notification n) {
        Bundle extras = n.extras;
        if (extras == null) return "Unknown";
        CharSequence title = extras.getCharSequence(Notification.EXTRA_TITLE);
        if (title != null && title.length() > 0) return title.toString();
        CharSequence sub = extras.getCharSequence(Notification.EXTRA_SUB_TEXT);
        if (sub != null && sub.length() > 0) return sub.toString();
        return "Unknown";
    }

    private String extractMessage(Notification n) {
        Bundle extras = n.extras;
        if (extras == null) return "";

        List<String> parts = new ArrayList<>();
        addIfNotEmpty(parts, extras.getCharSequence(Notification.EXTRA_TEXT));
        addIfNotEmpty(parts, extras.getCharSequence(Notification.EXTRA_BIG_TEXT));
        addIfNotEmpty(parts, extras.getCharSequence(Notification.EXTRA_SUMMARY_TEXT));
        addIfNotEmpty(parts, extras.getCharSequence(Notification.EXTRA_SUB_TEXT));

        // Sometimes messages are delivered as an array of lines
        Object lines = extras.get(Notification.EXTRA_TEXT_LINES);
        if (lines instanceof CharSequence[]) {
            for (CharSequence cs : (CharSequence[]) lines) {
                addIfNotEmpty(parts, cs);
            }
        } else if (lines instanceof List) {
            for (Object item : (List<?>) lines) {
                addIfNotEmpty(parts, asCharSequence(item));
            }
        }

        // MessagingStyle messages (WhatsApp, Telegram, etc)
        Object msgs = extras.get(Notification.EXTRA_MESSAGES);
        if (msgs instanceof Object[]) {
            for (Object msg : (Object[]) msgs) {
                addIfNotEmpty(parts, extractFromMessagingStyle(msg));
            }
        }

        if (parts.isEmpty()) return "";
        // Return the last non-empty line (most recent), but keep full context separated by newlines
        return TextUtils.join("\n", parts);
    }

    private void addIfNotEmpty(List<String> parts, CharSequence cs) {
        if (cs != null) {
            String s = cs.toString().trim();
            if (!s.isEmpty()) parts.add(s);
        }
    }

    private CharSequence asCharSequence(Object obj) {
        if (obj instanceof CharSequence) return (CharSequence) obj;
        if (obj != null) return obj.toString();
        return null;
    }

    private String extractFromMessagingStyle(Object msg) {
        if (msg == null) return "";
        // Try common accessor methods via reflection
        try {
            Method getText = msg.getClass().getMethod("getText");
            Object text = getText.invoke(msg);
            if (text instanceof CharSequence) return text.toString();
        } catch (Exception ignored) {}
        try {
            Method getMessage = msg.getClass().getMethod("getMessage");
            Object text = getMessage.invoke(msg);
            if (text instanceof CharSequence) return text.toString();
        } catch (Exception ignored) {}
        return msg.toString();
    }

    private boolean cacheReplyAction(Notification n, String cacheKey) {
        if (n.actions == null) return false;
        for (Notification.Action action : n.actions) {
            RemoteInput[] inputs = action.getRemoteInputs();
            PendingIntent intent = action.actionIntent;
            if (inputs != null && inputs.length > 0 && intent != null) {
                NotificationReplyCache.store(cacheKey, intent, inputs);
                return true;
            }
        }
        return false;
    }

    private void _replyToCachedAction(String cacheKey, String text) {
        NotificationReplyCache.ReplyAction reply = NotificationReplyCache.get(cacheKey);
        if (reply == null) return;

        try {
            PendingIntent replyIntent = reply.pendingIntent;
            RemoteInput[] remoteInputs = reply.remoteInputs;
            if (replyIntent == null || remoteInputs == null || remoteInputs.length == 0) return;

            Bundle remoteInputData = new Bundle();
            String key = remoteInputs[0].getResultKey();
            remoteInputData.putCharSequence(key, text);

            Intent fillInIntent = new Intent();
            RemoteInput.addResultsToIntent(remoteInputs, fillInIntent, remoteInputData);
            replyIntent.send(this, 0, fillInIntent);
            Log.d(TAG, "Reply sent via cached action (fallback) ✓");
        } catch (Exception e) {
            Log.e(TAG, "Fallback reply failed: " + e.getMessage());
        }
    }
}

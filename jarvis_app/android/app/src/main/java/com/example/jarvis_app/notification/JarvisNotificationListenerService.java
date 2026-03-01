package com.example.jarvis_app.notification;

import android.app.Notification;
import android.app.Notification.Action;
import android.app.PendingIntent;
import android.app.RemoteInput;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;
import android.util.Log;

import com.example.jarvis_app.accessibility.JarvisAccessibilityService;

import org.json.JSONObject;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class JarvisNotificationListenerService extends NotificationListenerService {
    private static final String TAG = "JarvisNotifListener";
    private static final String PREFS_NAME = "jarvis_prefs";
    private static final String KEY_PC_IP = "call_pc_ip";
    private static final String DEFAULT_PC_IP = "192.168.1.100";
    private static final int BACKEND_PORT = 8000;

    private static final String PLATFORM_WHATSAPP = "whatsapp";
    private static final String PLATFORM_INSTAGRAM = "instagram";
    private static final String PKG_WHATSAPP = "com.whatsapp";
    private static final String PKG_INSTAGRAM = "com.instagram.android";

    private static final long MIN_REPLY_INTERVAL_MS = 15000L;
    private static final int MAX_RECENT_EVENTS = 80;
    private static final Object LOCK = new Object();
    private static final Map<String, Long> LAST_REPLY_BY_SENDER = new HashMap<>();
    private static final Set<String> RECENT_EVENT_SET = new HashSet<>();
    private static final Deque<String> RECENT_EVENT_QUEUE = new ArrayDeque<>();
    private static final ExecutorService EXECUTOR = Executors.newSingleThreadExecutor();

    private static final class IncomingMessage {
        String sender;
        String text;
    }

    @Override
    public void onNotificationPosted(StatusBarNotification sbn) {
        if (sbn == null) return;

        String pkg = sbn.getPackageName();
        String platform = platformFromPackage(pkg);
        if (platform == null) return;

        Notification notification = sbn.getNotification();
        if (notification == null) return;

        IncomingMessage incoming = extractIncomingMessage(notification);
        if (incoming == null) return;

        String sender = safeTrim(incoming.sender);
        String text = safeTrim(incoming.text);
        if (text.isEmpty()) return;
        if (sender.isEmpty()) sender = "Unknown";
        if (looksLikeOutgoing(text)) return;

        String dedupeKey = buildDedupeKey(platform, sender, text);
        if (isDuplicateEvent(dedupeKey)) return;
        if (isRateLimited(platform, sender)) return;

        final String senderFinal = sender;
        final String textFinal = text;
        final Notification notifFinal = notification;
        EXECUTOR.execute(() -> handleIncoming(platform, pkg, senderFinal, textFinal, notifFinal));
    }

    private void handleIncoming(
        String platform,
        String packageName,
        String sender,
        String incomingText,
        Notification sourceNotification
    ) {
        String reply = generateReplyFromBackend(platform, sender, incomingText);
        if (reply.isEmpty()) {
            reply = fallbackReply(sender);
        }
        if (reply.isEmpty()) return;

        boolean sent = tryInlineReply(sourceNotification, reply);
        if (!sent) {
            String recipient = normalizeRecipient(sender);
            boolean queued = JarvisAccessibilityService.enqueueOutgoingMessage(
                platform,
                recipient,
                reply,
                true
            );
            if (queued) {
                sent = launchMessagingApp(packageName);
            }
        }

        if (sent) {
            markReplied(platform, sender);
            Log.d(TAG, "Auto-replied on " + platform + " to " + sender);
        }
    }

    private IncomingMessage extractIncomingMessage(Notification notification) {
        Bundle extras = notification.extras;
        if (extras == null) return null;

        String sender = firstNonEmpty(
            charSeqToString(extras.getCharSequence(Notification.EXTRA_TITLE)),
            charSeqToString(extras.getCharSequence(Notification.EXTRA_SUB_TEXT))
        );
        String text = "";

        CharSequence bigText = extras.getCharSequence(Notification.EXTRA_BIG_TEXT);
        if (bigText != null) text = bigText.toString();

        if (text.isEmpty()) {
            CharSequence body = extras.getCharSequence(Notification.EXTRA_TEXT);
            if (body != null) text = body.toString();
        }

        if (text.isEmpty()) {
            CharSequence[] lines = extras.getCharSequenceArray(Notification.EXTRA_TEXT_LINES);
            if (lines != null && lines.length > 0) {
                CharSequence last = lines[lines.length - 1];
                if (last != null) text = last.toString();
            }
        }

        text = sanitizeMessageText(text);
        sender = sanitizeSender(sender, text);
        text = stripSenderPrefix(text, sender);
        text = safeTrim(text);

        if (text.isEmpty()) return null;
        IncomingMessage out = new IncomingMessage();
        out.sender = sender;
        out.text = text;
        return out;
    }

    private String generateReplyFromBackend(String platform, String sender, String incomingText) {
        HttpURLConnection conn = null;
        try {
            String baseUrl = buildBackendBaseUrl();
            URL url = new URL(baseUrl + "/api/automation/messaging/auto-reply/generate");
            conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("POST");
            conn.setConnectTimeout(3500);
            conn.setReadTimeout(7000);
            conn.setDoOutput(true);
            conn.setRequestProperty("Content-Type", "application/json; charset=UTF-8");

            JSONObject payload = new JSONObject();
            payload.put("platform", platform);
            payload.put("incoming_message", incomingText);
            payload.put("sender", sender);
            payload.put("context", "notification_listener");

            byte[] bytes = payload.toString().getBytes(StandardCharsets.UTF_8);
            try (OutputStream os = conn.getOutputStream()) {
                os.write(bytes);
            }

            int code = conn.getResponseCode();
            if (code < 200 || code >= 300) return "";
            byte[] body = readAllBytes(new BufferedInputStream(conn.getInputStream()));
            if (body.length == 0) return "";

            JSONObject json = new JSONObject(new String(body, StandardCharsets.UTF_8));
            if (!json.optBoolean("success", false)) return "";
            return safeTrim(json.optString("reply", ""));
        } catch (Exception ex) {
            Log.w(TAG, "Auto-reply generation failed: " + ex.getMessage());
            return "";
        } finally {
            if (conn != null) conn.disconnect();
        }
    }

    private boolean tryInlineReply(Notification notification, String replyText) {
        try {
            Action[] actions = notification.actions;
            if (actions == null || actions.length == 0) return false;

            for (Action action : actions) {
                if (action == null || action.actionIntent == null) continue;
                RemoteInput[] remoteInputs = action.getRemoteInputs();
                if (remoteInputs == null || remoteInputs.length == 0) continue;

                Bundle results = new Bundle();
                for (RemoteInput input : remoteInputs) {
                    if (input == null) continue;
                    if (input.getAllowFreeFormInput()) {
                        results.putCharSequence(input.getResultKey(), replyText);
                    }
                }
                if (results.isEmpty()) continue;

                Intent fillInIntent = new Intent();
                RemoteInput.addResultsToIntent(remoteInputs, fillInIntent, results);
                action.actionIntent.send(this, 0, fillInIntent);
                return true;
            }
        } catch (PendingIntent.CanceledException ignored) {
        } catch (Exception ex) {
            Log.w(TAG, "Inline reply failed: " + ex.getMessage());
        }
        return false;
    }

    private boolean launchMessagingApp(String packageName) {
        try {
            Intent launchIntent = getPackageManager().getLaunchIntentForPackage(packageName);
            if (launchIntent == null) return false;
            launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(launchIntent);
            return true;
        } catch (Exception ex) {
            Log.w(TAG, "Failed to launch package " + packageName + ": " + ex.getMessage());
            return false;
        }
    }

    private boolean isDuplicateEvent(String key) {
        synchronized (LOCK) {
            if (RECENT_EVENT_SET.contains(key)) return true;
            RECENT_EVENT_SET.add(key);
            RECENT_EVENT_QUEUE.addLast(key);
            while (RECENT_EVENT_QUEUE.size() > MAX_RECENT_EVENTS) {
                String old = RECENT_EVENT_QUEUE.pollFirst();
                if (old != null) RECENT_EVENT_SET.remove(old);
            }
            return false;
        }
    }

    private boolean isRateLimited(String platform, String sender) {
        String key = (platform + "|" + sender).toLowerCase(Locale.US);
        long now = System.currentTimeMillis();
        synchronized (LOCK) {
            Long last = LAST_REPLY_BY_SENDER.get(key);
            return last != null && (now - last) < MIN_REPLY_INTERVAL_MS;
        }
    }

    private void markReplied(String platform, String sender) {
        String key = (platform + "|" + sender).toLowerCase(Locale.US);
        synchronized (LOCK) {
            LAST_REPLY_BY_SENDER.put(key, System.currentTimeMillis());
            if (LAST_REPLY_BY_SENDER.size() > 200) {
                LAST_REPLY_BY_SENDER.clear();
            }
        }
    }

    private String buildBackendBaseUrl() {
        SharedPreferences prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);
        String ip = safeTrim(prefs.getString(KEY_PC_IP, DEFAULT_PC_IP));
        if (ip.isEmpty()) ip = DEFAULT_PC_IP;
        return "http://" + ip + ":" + BACKEND_PORT;
    }

    private String normalizeRecipient(String sender) {
        String clean = safeTrim(sender);
        if (clean.equalsIgnoreCase("unknown")) return "";
        return clean;
    }

    private String sanitizeSender(String senderRaw, String text) {
        String sender = safeTrim(senderRaw);
        if (sender.contains(":")) {
            sender = safeTrim(sender.substring(0, sender.indexOf(':')));
        }

        if (sender.isEmpty() && text.contains(":")) {
            String maybeSender = safeTrim(text.substring(0, text.indexOf(':')));
            if (maybeSender.length() <= 64 && !maybeSender.contains("http")) {
                sender = maybeSender;
            }
        }
        return sender;
    }

    private String stripSenderPrefix(String textRaw, String senderRaw) {
        String text = safeTrim(textRaw);
        String sender = safeTrim(senderRaw);
        if (text.isEmpty() || sender.isEmpty()) return text;

        String lowerText = text.toLowerCase(Locale.US);
        String lowerSender = sender.toLowerCase(Locale.US);
        String prefix = lowerSender + ":";
        if (lowerText.startsWith(prefix)) {
            return safeTrim(text.substring(prefix.length()));
        }
        return text;
    }

    private String sanitizeMessageText(String textRaw) {
        String text = safeTrim(textRaw);
        if (text.equalsIgnoreCase("new messages")) return "";
        if (text.equalsIgnoreCase("1 new message")) return "";
        return text;
    }

    private boolean looksLikeOutgoing(String textRaw) {
        String text = safeTrim(textRaw).toLowerCase(Locale.US);
        return text.startsWith("you:") || text.startsWith("you ");
    }

    private String fallbackReply(String sender) {
        if (safeTrim(sender).isEmpty()) {
            return "Got your message. I will get back to you shortly.";
        }
        return "Got your message, " + sender + ". I will get back to you shortly.";
    }

    private String buildDedupeKey(String platform, String sender, String text) {
        return (platform + "|" + sender + "|" + text).toLowerCase(Locale.US);
    }

    private static String platformFromPackage(String pkg) {
        if (PKG_WHATSAPP.equals(pkg)) return PLATFORM_WHATSAPP;
        if (PKG_INSTAGRAM.equals(pkg)) return PLATFORM_INSTAGRAM;
        return null;
    }

    private static String charSeqToString(CharSequence value) {
        return value == null ? "" : value.toString();
    }

    private static String firstNonEmpty(String... values) {
        if (values == null) return "";
        for (String value : values) {
            String v = safeTrim(value);
            if (!v.isEmpty()) return v;
        }
        return "";
    }

    private static byte[] readAllBytes(BufferedInputStream input) throws Exception {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buffer = new byte[1024];
        int read;
        while ((read = input.read(buffer)) != -1) {
            out.write(buffer, 0, read);
        }
        return out.toByteArray();
    }

    private static String safeTrim(String value) {
        return value == null ? "" : value.trim();
    }
}

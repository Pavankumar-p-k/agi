package com.example.jarvis_app.accessibility;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.os.Bundle;
import android.content.Intent;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.text.TextUtils;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;

import com.example.jarvis_app.call.CallAssistantService;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.Locale;

public class JarvisAccessibilityService extends AccessibilityService {
    private static final int ANSWER_DELAY_MS = 3500;
    private static final long SEND_RETRY_MIN_INTERVAL_MS = 500L;
    private static final long SEND_MAX_AGE_MS = 120000L;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private boolean pendingAnswer = false;

    private static final String[] WHATSAPP_TEXTS = {"Answer", "Accept", "ANSWER", "ACCEPT", "answer"};
    private static final String[] INSTAGRAM_TEXTS = {"Accept", "Answer", "accept", "answer video call"};

    private static final String PLATFORM_WHATSAPP = "whatsapp";
    private static final String PLATFORM_INSTAGRAM = "instagram";
    private static final String PKG_WHATSAPP = "com.whatsapp";
    private static final String PKG_INSTAGRAM = "com.instagram.android";

    private static final Object OUTBOX_LOCK = new Object();
    private static final Deque<PendingMessage> OUTBOX = new ArrayDeque<>();
    private static long nextMessageId = 1L;
    private static JarvisAccessibilityService instance;

    private static final class PendingMessage {
        long id;
        String platform;
        String recipient;
        String message;
        boolean fromNotification;
        long createdAtMs;
        long lastAttemptAtMs;
        int attempts;
    }

    public static boolean enqueueOutgoingMessage(
        String platformRaw,
        String recipientRaw,
        String messageRaw,
        boolean fromNotification
    ) {
        String platform = normalizePlatform(platformRaw);
        String message = safeTrim(messageRaw);
        if (message.isEmpty()) return false;
        if (!PLATFORM_WHATSAPP.equals(platform) && !PLATFORM_INSTAGRAM.equals(platform)) return false;

        PendingMessage pending = new PendingMessage();
        synchronized (OUTBOX_LOCK) {
            pending.id = nextMessageId++;
        }
        pending.platform = platform;
        pending.recipient = safeTrim(recipientRaw);
        pending.message = message;
        pending.fromNotification = fromNotification;
        pending.createdAtMs = System.currentTimeMillis();

        synchronized (OUTBOX_LOCK) {
            OUTBOX.addLast(pending);
        }

        JarvisAccessibilityService svc = instance;
        if (svc != null) {
            svc.handler.post(svc::processQueuedMessagesNow);
        }
        return true;
    }

    @Override
    protected void onServiceConnected() {
        instance = this;
        AccessibilityServiceInfo info = new AccessibilityServiceInfo();
        info.eventTypes = AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED
            | AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED
            | AccessibilityEvent.TYPE_NOTIFICATION_STATE_CHANGED;
        info.feedbackType = AccessibilityServiceInfo.FEEDBACK_GENERIC;
        info.packageNames = new String[]{PKG_WHATSAPP, PKG_INSTAGRAM};
        info.flags = AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS | AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;
        info.notificationTimeout = 100;
        setServiceInfo(info);
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        if (event == null || event.getPackageName() == null) return;
        String pkg = event.getPackageName().toString();

        if ("com.whatsapp".equals(pkg)) {
            maybeAnswerWhatsApp();
        } else if ("com.instagram.android".equals(pkg)) {
            maybeAnswerInstagram();
        }

        processQueuedMessagesNow();
    }

    private void maybeAnswerWhatsApp() {
        if (pendingAnswer) return;
        pendingAnswer = true;
        handler.postDelayed(() -> {
            pendingAnswer = false;
            AccessibilityNodeInfo root = getRootInActiveWindow();
            if (root == null) return;
            if (clickByText(root, WHATSAPP_TEXTS)) {
                notifyVoipAnswered("WhatsApp", "Unknown");
                return;
            }
            List<AccessibilityNodeInfo> byId = root.findAccessibilityNodeInfosByViewId("com.whatsapp:id/accept_call_btn");
            if (byId != null && !byId.isEmpty()) {
                byId.get(0).performAction(AccessibilityNodeInfo.ACTION_CLICK);
                notifyVoipAnswered("WhatsApp", "Unknown");
            }
        }, ANSWER_DELAY_MS);
    }

    private void maybeAnswerInstagram() {
        if (pendingAnswer) return;
        pendingAnswer = true;
        handler.postDelayed(() -> {
            pendingAnswer = false;
            AccessibilityNodeInfo root = getRootInActiveWindow();
            if (root == null) return;
            if (clickByText(root, INSTAGRAM_TEXTS)) {
                notifyVoipAnswered("Instagram", "Unknown");
            }
        }, ANSWER_DELAY_MS);
    }

    private void processQueuedMessagesNow() {
        AccessibilityNodeInfo root = getRootInActiveWindow();
        if (root == null) return;
        String currentPkg = root.getPackageName() == null ? "" : root.getPackageName().toString();
        if (currentPkg.isEmpty()) return;

        PendingMessage pending = peekOutbox();
        if (pending == null) return;

        long now = System.currentTimeMillis();
        if (now - pending.createdAtMs > SEND_MAX_AGE_MS) {
            popOutbox();
            return;
        }
        if (now - pending.lastAttemptAtMs < SEND_RETRY_MIN_INTERVAL_MS) return;
        pending.lastAttemptAtMs = now;
        pending.attempts += 1;

        boolean pkgOk =
            (PLATFORM_WHATSAPP.equals(pending.platform) && PKG_WHATSAPP.equals(currentPkg))
                || (PLATFORM_INSTAGRAM.equals(pending.platform) && PKG_INSTAGRAM.equals(currentPkg));
        if (!pkgOk) return;

        boolean sent = false;
        if (PLATFORM_WHATSAPP.equals(pending.platform)) {
            sent = trySendWhatsApp(root, pending);
        } else if (PLATFORM_INSTAGRAM.equals(pending.platform)) {
            sent = trySendInstagram(root, pending);
        }

        if (sent) {
            popOutbox();
            return;
        }

        if (pending.attempts > 35) {
            popOutbox();
        }
    }

    private boolean trySendWhatsApp(AccessibilityNodeInfo root, PendingMessage pending) {
        if (tapSendButton(root, new String[]{"com.whatsapp:id/send", "com.whatsapp:id/send_container"})) {
            return true;
        }

        AccessibilityNodeInfo input = findFirstByViewIds(root, new String[]{
            "com.whatsapp:id/entry",
            "com.whatsapp:id/conversation_text_entry",
            "com.whatsapp:id/caption",
        });
        if (input == null) {
            input = findFirstEditable(root);
        }
        if (input != null) {
            setTextIfNeeded(input, pending.message);
            if (tapSendButton(root, new String[]{"com.whatsapp:id/send", "com.whatsapp:id/send_container"})) {
                return true;
            }
        }

        if (!pending.recipient.isEmpty()) {
            if (clickByTextContains(root, pending.recipient)) return false;

            AccessibilityNodeInfo searchBtn = findFirstByViewIds(root, new String[]{"com.whatsapp:id/menuitem_search"});
            if (searchBtn == null) {
                searchBtn = findFirstByContentDescContains(root, "search");
            }
            if (searchBtn != null) {
                clickNodeOrParent(searchBtn);
            }

            AccessibilityNodeInfo searchInput = findFirstEditable(root);
            if (searchInput != null) {
                setTextIfNeeded(searchInput, pending.recipient);
            }
            clickByTextContains(root, pending.recipient);
        }

        return false;
    }

    private boolean trySendInstagram(AccessibilityNodeInfo root, PendingMessage pending) {
        if (tapSendButton(root, new String[]{
            "com.instagram.android:id/row_thread_composer_button_send",
            "com.instagram.android:id/send_button",
        })) {
            return true;
        }

        if (clickByTextContains(root, "Message")) return false;
        if (clickByTextContains(root, "Next")) return false;

        AccessibilityNodeInfo input = findFirstByViewIds(root, new String[]{
            "com.instagram.android:id/row_thread_composer_edittext",
            "com.instagram.android:id/message_input_text",
            "com.instagram.android:id/search_edit_text",
        });
        if (input == null) {
            input = findFirstEditable(root);
        }
        if (input != null) {
            String desired = pending.message;
            if (isRecipientEntryField(input) && !pending.recipient.isEmpty()) {
                desired = pending.recipient;
            }
            setTextIfNeeded(input, desired);
        }

        if (clickByTextContains(root, pending.recipient)) return false;
        if (tapSendButton(root, new String[]{
            "com.instagram.android:id/row_thread_composer_button_send",
            "com.instagram.android:id/send_button",
        })) {
            return true;
        }

        return false;
    }

    private boolean isRecipientEntryField(AccessibilityNodeInfo node) {
        CharSequence hint = node.getHintText();
        String text = hint == null ? "" : hint.toString().toLowerCase(Locale.US);
        return text.contains("search") || text.contains("to");
    }

    private PendingMessage peekOutbox() {
        synchronized (OUTBOX_LOCK) {
            return OUTBOX.peekFirst();
        }
    }

    private void popOutbox() {
        synchronized (OUTBOX_LOCK) {
            OUTBOX.pollFirst();
        }
    }

    private AccessibilityNodeInfo findFirstByViewIds(AccessibilityNodeInfo root, String[] viewIds) {
        if (root == null || viewIds == null) return null;
        for (String viewId : viewIds) {
            try {
                List<AccessibilityNodeInfo> nodes = root.findAccessibilityNodeInfosByViewId(viewId);
                if (nodes != null && !nodes.isEmpty()) return nodes.get(0);
            } catch (Exception ignored) {
            }
        }
        return null;
    }

    private AccessibilityNodeInfo findFirstEditable(AccessibilityNodeInfo root) {
        List<AccessibilityNodeInfo> all = collectAllNodes(root);
        for (AccessibilityNodeInfo node : all) {
            if (node == null) continue;
            if (node.isEditable()) return node;
            CharSequence className = node.getClassName();
            if (className != null && className.toString().toLowerCase(Locale.US).contains("edittext")) {
                return node;
            }
        }
        return null;
    }

    private List<AccessibilityNodeInfo> collectAllNodes(AccessibilityNodeInfo root) {
        List<AccessibilityNodeInfo> out = new ArrayList<>();
        collectNodeTree(root, out);
        return out;
    }

    private void collectNodeTree(AccessibilityNodeInfo node, List<AccessibilityNodeInfo> out) {
        if (node == null) return;
        out.add(node);
        int count = node.getChildCount();
        for (int i = 0; i < count; i++) {
            try {
                collectNodeTree(node.getChild(i), out);
            } catch (Exception ignored) {
            }
        }
    }

    private boolean setTextIfNeeded(AccessibilityNodeInfo node, String textRaw) {
        if (node == null) return false;
        String text = safeTrim(textRaw);
        if (text.isEmpty()) return false;
        CharSequence current = node.getText();
        if (current != null && text.equals(current.toString())) return true;

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            Bundle args = new Bundle();
            args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text);
            return node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args);
        }
        return false;
    }

    private boolean tapSendButton(AccessibilityNodeInfo root, String[] ids) {
        AccessibilityNodeInfo byId = findFirstByViewIds(root, ids);
        if (byId != null && clickNodeOrParent(byId)) return true;
        if (clickByTextContains(root, "Send")) return true;
        AccessibilityNodeInfo byDesc = findFirstByContentDescContains(root, "send");
        return byDesc != null && clickNodeOrParent(byDesc);
    }

    private AccessibilityNodeInfo findFirstByContentDescContains(AccessibilityNodeInfo root, String needleRaw) {
        String needle = safeTrim(needleRaw).toLowerCase(Locale.US);
        if (needle.isEmpty()) return null;
        for (AccessibilityNodeInfo node : collectAllNodes(root)) {
            CharSequence desc = node.getContentDescription();
            if (desc == null) continue;
            String d = desc.toString().toLowerCase(Locale.US);
            if (d.contains(needle)) return node;
        }
        return null;
    }

    private boolean clickByTextContains(AccessibilityNodeInfo root, String raw) {
        String target = safeTrim(raw);
        if (target.isEmpty()) return false;
        List<AccessibilityNodeInfo> nodes = root.findAccessibilityNodeInfosByText(target);
        if (nodes != null) {
            for (AccessibilityNodeInfo node : nodes) {
                if (clickNodeOrParent(node)) return true;
            }
        }

        String lower = target.toLowerCase(Locale.US);
        for (AccessibilityNodeInfo node : collectAllNodes(root)) {
            CharSequence txt = node.getText();
            if (txt == null) continue;
            String current = txt.toString().toLowerCase(Locale.US);
            if (current.contains(lower) && clickNodeOrParent(node)) return true;
        }
        return false;
    }

    private boolean clickNodeOrParent(AccessibilityNodeInfo node) {
        AccessibilityNodeInfo current = node;
        int depth = 0;
        while (current != null && depth < 6) {
            if (current.isClickable()) {
                return current.performAction(AccessibilityNodeInfo.ACTION_CLICK);
            }
            current = current.getParent();
            depth++;
        }
        return false;
    }

    private static String safeTrim(String value) {
        return value == null ? "" : value.trim();
    }

    private static String normalizePlatform(String value) {
        String p = safeTrim(value).toLowerCase(Locale.US);
        if (p.equals("wa")) return PLATFORM_WHATSAPP;
        if (p.equals("ig") || p.equals("insta")) return PLATFORM_INSTAGRAM;
        return p;
    }

    private boolean clickByText(AccessibilityNodeInfo root, String[] values) {
        for (String value : values) {
            List<AccessibilityNodeInfo> nodes = root.findAccessibilityNodeInfosByText(value);
            if (nodes == null) continue;
            for (AccessibilityNodeInfo node : nodes) {
                if (node.isClickable()) {
                    node.performAction(AccessibilityNodeInfo.ACTION_CLICK);
                    return true;
                }
                AccessibilityNodeInfo parent = node.getParent();
                if (parent != null && parent.isClickable()) {
                    parent.performAction(AccessibilityNodeInfo.ACTION_CLICK);
                    return true;
                }
            }
        }
        return false;
    }

    private void notifyVoipAnswered(String platform, String callerName) {
        Intent intent = new Intent(this, CallAssistantService.class);
        intent.setAction(CallAssistantService.ACTION_VOIP_ANSWERED);
        intent.putExtra("platform", platform);
        intent.putExtra("caller_name", callerName);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent);
        } else {
            startService(intent);
        }
    }

    @Override
    public void onInterrupt() {
        // No-op
    }

    @Override
    public void onDestroy() {
        synchronized (OUTBOX_LOCK) {
            if (instance == this) instance = null;
        }
        super.onDestroy();
    }
}

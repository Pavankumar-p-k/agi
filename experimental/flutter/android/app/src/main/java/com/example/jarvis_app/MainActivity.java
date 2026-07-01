// android/app/src/main/java/com/jarvis/app/MainActivity.java
//
// Bridges Flutter ↔ Android native code via MethodChannel
// Handles: start/stop service, receive wake broadcasts, battery opt bypass

package com.example.jarvis_app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.net.Uri;
import android.app.ActivityManager;
import android.app.SearchManager;
import android.os.Build;
import android.os.Bundle;
import android.os.PowerManager;
import android.app.role.RoleManager;
import android.provider.AlarmClock;
import android.provider.MediaStore;
import android.provider.Settings;
import android.util.Log;

import androidx.annotation.NonNull;

import io.flutter.embedding.android.FlutterActivity;
import io.flutter.embedding.engine.FlutterEngine;
import io.flutter.plugin.common.EventChannel;
import io.flutter.plugin.common.MethodChannel;
import io.flutter.plugin.common.MethodCall;

import com.example.jarvis_app.device.DeviceDataProvider;
import com.example.jarvis_app.sync.WindowsSync;
import com.example.jarvis_app.messaging.JarvisReplySender;
import com.example.jarvis_app.messaging.JarvisMessageBridge;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

public class MainActivity extends FlutterActivity {

    private static final String METHOD_CHANNEL = "com.example.jarvis_app/wake_service";
    private static final String EVENT_CHANNEL  = "com.example.jarvis_app/wake_events";
    private static final String DEVICE_CHANNEL = "com.example.jarvis_app/device_data";
    private static final String MSG_CHANNEL    = "com.example.jarvis_app/messages";
    private static final String REPLY_CHANNEL  = "com.example.jarvis_app/reply";
    private static final String AUTOMATION_CHANNEL = "com.example.jarvis_app/automation";
    private static final String TASK_EVENTS_CHANNEL = "com.example.jarvis_app/task_events";
    private static final String PREFS          = "jarvis_prefs";

    private MethodChannel _methodChannel;
    private MethodChannel _deviceChannel;
    private MethodChannel _replyChannel;
    private MethodChannel _automationChannel;
    private EventChannel.EventSink _eventSink;
    private final WindowsSync _sync = new WindowsSync();

    // Receives broadcast from JarvisWakeService when wake word fires
    private final BroadcastReceiver _wakeReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context ctx, Intent intent) {
            if (JarvisWakeService.ACTION_WAKE.equals(intent.getAction())) {
                // Forward to Flutter via EventChannel
                if (_eventSink != null) {
                    runOnUiThread(() -> _eventSink.success("wake_word_detected"));
                }
            }
        }
    };

    @Override
    public void configureFlutterEngine(@NonNull FlutterEngine flutterEngine) {
        super.configureFlutterEngine(flutterEngine);

        // ── MethodChannel: Flutter calls Java ──
        _methodChannel = new MethodChannel(
            flutterEngine.getDartExecutor().getBinaryMessenger(),
            METHOD_CHANNEL
        );

        _methodChannel.setMethodCallHandler((call, result) -> {
            switch (call.method) {

                case "startWakeService":
                    startWakeService();
                    result.success(true);
                    break;

                case "stopWakeService":
                    stopWakeService();
                    result.success(true);
                    break;

                case "isServiceRunning":
                    result.success(isServiceRunning());
                    break;

                case "requestBatteryOptimizationExempt":
                    requestBatteryExemption();
                    result.success(true);
                    break;

                case "isBatteryOptimizationExempt":
                    result.success(isBatteryOptimizationExempt());
                    break;

                case "openBatterySettings":
                    openBatterySettings();
                    result.success(true);
                    break;

                default:
                    result.notImplemented();
            }
        });

        // ── Device Data Channel ──
        _deviceChannel = new MethodChannel(
            flutterEngine.getDartExecutor().getBinaryMessenger(),
            DEVICE_CHANNEL
        );

        _deviceChannel.setMethodCallHandler((call, result) -> {
            switch (call.method) {
                case "getContacts":
                    result.success(DeviceDataProvider.getContacts(this, getIntArg(call, "limit", 500)));
                    break;
                case "getCallLogs":
                    result.success(DeviceDataProvider.getCallLogs(this, getIntArg(call, "limit", 200)));
                    break;
                case "getSmsLogs":
                    result.success(DeviceDataProvider.getSmsLogs(this, getIntArg(call, "limit", 200)));
                    break;
                case "getUsageSummary":
                    result.success(DeviceDataProvider.getUsageSummary(this, getIntArg(call, "days", 1)));
                    break;
                case "getCallStats":
                    result.success(DeviceDataProvider.getCallStats(this, getIntArg(call, "days", 1)));
                    break;
                case "openDialer":
                    openDialer(getStringArg(call, "number", ""));
                    result.success(true);
                    break;
                case "placeCall":
                    placeCall(getStringArg(call, "number", ""));
                    result.success(true);
                    break;
                case "requestDialerRole":
                    result.success(requestDialerRole());
                    break;
                case "openUsageAccessSettings":
                    openUsageAccessSettings();
                    result.success(true);
                    break;
                case "syncAllToPc":
                    syncAllToPc(getIntArg(call, "limit", 200));
                    result.success(true);
                    break;
                case "setPcIp":
                    if (call.arguments instanceof Map) {
                        Object ipObj = ((Map<?, ?>) call.arguments).get("ip");
                        String ip = ipObj != null ? ipObj.toString() : "";
                        if (!ip.trim().isEmpty()) {
                            getPrefs().edit().putString("pc_ip", ip.trim()).apply();
                            _sync.setPcIp(ip.trim());
                        }
                    }
                    result.success(true);
                    break;
                default:
                    result.notImplemented();
            }
        });

        // ── EventChannel: Java pushes events to Flutter ──
        // Message Inbox Channel (Android -> Flutter)
        new EventChannel(
            flutterEngine.getDartExecutor().getBinaryMessenger(),
            MSG_CHANNEL
        ).setStreamHandler(new EventChannel.StreamHandler() {
            @Override
            public void onListen(Object args, EventChannel.EventSink sink) {
                JarvisMessageBridge.setSink(sink);
            }
            @Override
            public void onCancel(Object args) {
                JarvisMessageBridge.setSink(null);
            }
        });

        // Reply Channel (Flutter -> Android)
        _replyChannel = new MethodChannel(
            flutterEngine.getDartExecutor().getBinaryMessenger(),
            REPLY_CHANNEL
        );
        _replyChannel.setMethodCallHandler(new JarvisReplySender(this));

        new EventChannel(
            flutterEngine.getDartExecutor().getBinaryMessenger(),
            EVENT_CHANNEL
        ).setStreamHandler(new EventChannel.StreamHandler() {
            @Override
            public void onListen(Object args, EventChannel.EventSink sink) {
                _eventSink = sink;
            }
            @Override
            public void onCancel(Object args) {
                _eventSink = null;
            }
        });

        // Automation Channel (Flutter -> Android)
        _automationChannel = new MethodChannel(
            flutterEngine.getDartExecutor().getBinaryMessenger(),
            AUTOMATION_CHANNEL
        );
        _automationChannel.setMethodCallHandler((call, result) -> {
            switch (call.method) {
                case "openApp":
                    openApp((String) call.argument("package"));
                    result.success(true);
                    break;
                case "sendMessage":
                    composePlatformMessage(
                        getStringArg(call, "platform", "sms"),
                        getStringArg(call, "target", getStringArg(call, "recipient", "")),
                        getStringArg(call, "text", "")
                    );
                    result.success(true);
                    break;
                case "search":
                    searchWeb(getStringArg(call, "query", ""));
                    result.success(true);
                    break;
                case "screenshot":
                    // Would require accessibility service
                    result.success(false);
                    break;
                case "type":
                    // Would require accessibility service + focus tracking
                    result.success(false);
                    break;
                case "openUrl":
                    openUrl(getStringArg(call, "url", ""));
                    result.success(true);
                    break;
                case "setAlarm":
                    setAlarm(getStringArg(call, "time", ""));
                    result.success(true);
                    break;
                case "playMusic":
                    playMusic(getStringArg(call, "song", ""));
                    result.success(true);
                    break;
                case "callPerson":
                    callPerson(getStringArg(call, "name", getStringArg(call, "number", "")));
                    result.success(true);
                    break;
                case "composeSms":
                case "sendSMS":
                    composeSms(
                        getStringArg(call, "number", getStringArg(call, "target", "")),
                        getStringArg(call, "text", "")
                    );
                    result.success(true);
                    break;
                case "composeEmail":
                    composeEmail(
                        getStringArg(call, "email", getStringArg(call, "target", "")),
                        getStringArg(call, "subject", ""),
                        getStringArg(call, "body", getStringArg(call, "text", ""))
                    );
                    result.success(true);
                    break;
                case "composeWhatsApp":
                    composeWhatsApp(
                        getStringArg(call, "number", getStringArg(call, "target", "")),
                        getStringArg(call, "text", "")
                    );
                    result.success(true);
                    break;
                case "openSettings":
                    openSystemSettings(getStringArg(call, "setting", ""));
                    result.success(true);
                    break;
                case "toggleWifi":
                    openConnectivityPanel("wifi");
                    result.success(true);
                    break;
                case "toggleBluetooth":
                    openConnectivityPanel("bluetooth");
                    result.success(true);
                    break;
                default:
                    result.notImplemented();
            }
        });
    }

    @Override
    protected void onResume() {
        super.onResume();
        // Register broadcast receiver
        IntentFilter filter = new IntentFilter(JarvisWakeService.ACTION_WAKE);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(_wakeReceiver, filter, Context.RECEIVER_NOT_EXPORTED);
        } else {
            registerReceiver(_wakeReceiver, filter);
        }
    }

    @Override
    protected void onPause() {
        super.onPause();
        try { unregisterReceiver(_wakeReceiver); } catch (Exception ignored) {}
    }


    // ── Service Control ──

    private void startWakeService() {
        Intent intent = new Intent(this, JarvisWakeService.class);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent);
        } else {
            startService(intent);
        }
    }

    private void stopWakeService() {
        Intent intent = new Intent(this, JarvisWakeService.class);
        intent.setAction(JarvisWakeService.ACTION_STOP);
        startService(intent);
    }

    private boolean isServiceRunning() {
        return isServiceRunning(JarvisWakeService.class);
    }

    private boolean isServiceRunning(Class<?> serviceClass) {
        ActivityManager am = (ActivityManager) getSystemService(Context.ACTIVITY_SERVICE);
        if (am == null) return false;
        for (ActivityManager.RunningServiceInfo info :
                am.getRunningServices(Integer.MAX_VALUE)) {
            if (serviceClass.getName().equals(info.service.getClassName())) {
                return true;
            }
        }
        return false;
    }

    private SharedPreferences getPrefs() {
        return getSharedPreferences(PREFS, MODE_PRIVATE);
    }

    private int getIntArg(MethodCall call, String key, int fallback) {
        if (call.arguments instanceof Map) {
            Object v = ((Map<?, ?>) call.arguments).get(key);
            if (v instanceof Number) return ((Number) v).intValue();
            try { return Integer.parseInt(String.valueOf(v)); } catch (Exception ignored) {}
        }
        return fallback;
    }

    private String getStringArg(MethodCall call, String key, String fallback) {
        if (call.arguments instanceof Map) {
            Object v = ((Map<?, ?>) call.arguments).get(key);
            if (v != null) return v.toString();
        }
        return fallback;
    }

    private boolean getBoolArg(MethodCall call, String key, boolean fallback) {
        if (call.arguments instanceof Map) {
            Object v = ((Map<?, ?>) call.arguments).get(key);
            if (v instanceof Boolean) return (Boolean) v;
            if (v instanceof Number) return ((Number) v).intValue() != 0;
            if (v != null) {
                String s = v.toString().trim().toLowerCase();
                if ("true".equals(s) || "1".equals(s)) return true;
                if ("false".equals(s) || "0".equals(s)) return false;
            }
        }
        return fallback;
    }


    // ── Battery Optimization ──

    private boolean isBatteryOptimizationExempt() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
            return pm.isIgnoringBatteryOptimizations(getPackageName());
        }
        return true;
    }

    private void requestBatteryExemption() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            if (!isBatteryOptimizationExempt()) {
                Intent intent = new Intent(
                    Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS
                );
                intent.setData(Uri.parse("package:" + getPackageName()));
                startActivity(intent);
            }
        }
    }

    private void openBatterySettings() {
        Intent intent = new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS);
        startActivity(intent);
    }

    // ── Device helpers ──

    private void openDialer(String number) {
        String n = number == null ? "" : number.trim();
        Uri uri = Uri.parse("tel:" + n);
        Intent intent = new Intent(Intent.ACTION_DIAL, uri);
        startActivity(intent);
    }

    private void placeCall(String number) {
        String n = number == null ? "" : number.trim();
        if (n.isEmpty()) return;
        Uri uri = Uri.parse("tel:" + n);
        Intent intent = new Intent(Intent.ACTION_CALL, uri);
        startActivity(intent);
    }

    private void openApp(String packageName) {
        try {
            Intent intent = getPackageManager().getLaunchIntentForPackage(packageName);
            if (intent != null) {
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                startActivity(intent);
            }
        } catch (Exception e) {
            Log.e("MainActivity", "Failed to open app: " + packageName, e);
        }
    }

    private void openUrl(String url) {
        String target = url == null ? "" : url.trim();
        if (target.isEmpty()) return;
        if (!target.startsWith("http://") && !target.startsWith("https://")) {
            target = "https://" + target;
        }
        try {
            Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(target));
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(intent);
        } catch (Exception e) {
            Log.e("MainActivity", "Failed to open url: " + target, e);
        }
    }

    private void searchWeb(String query) {
        String q = query == null ? "" : query.trim();
        if (q.isEmpty()) return;
        try {
            Intent intent = new Intent(Intent.ACTION_WEB_SEARCH);
            intent.putExtra(SearchManager.QUERY, q);
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(intent);
        } catch (Exception ignored) {
            String encoded = URLEncoder.encode(q, StandardCharsets.UTF_8);
            openUrl("https://www.google.com/search?q=" + encoded);
        }
    }

    private void composeSms(String number, String text) {
        String target = number == null ? "" : number.trim();
        try {
            Intent intent = new Intent(Intent.ACTION_SENDTO);
            intent.setData(Uri.parse("smsto:" + target));
            intent.putExtra("sms_body", text == null ? "" : text);
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(intent);
        } catch (Exception e) {
            Log.e("MainActivity", "Failed to compose SMS", e);
        }
    }

    private void composeEmail(String email, String subject, String body) {
        String target = email == null ? "" : email.trim();
        try {
            Intent intent = new Intent(Intent.ACTION_SENDTO);
            intent.setData(Uri.parse("mailto:" + target));
            intent.putExtra(Intent.EXTRA_EMAIL, new String[] { target });
            intent.putExtra(Intent.EXTRA_SUBJECT, subject == null ? "" : subject);
            intent.putExtra(Intent.EXTRA_TEXT, body == null ? "" : body);
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(intent);
        } catch (Exception e) {
            Log.e("MainActivity", "Failed to compose email", e);
        }
    }

    private void composeWhatsApp(String number, String text) {
        String target = number == null ? "" : number.replaceAll("[^0-9+]", "");
        try {
            String encoded = URLEncoder.encode(text == null ? "" : text, StandardCharsets.UTF_8);
            Uri uri = Uri.parse("https://wa.me/" + target + "?text=" + encoded);
            Intent intent = new Intent(Intent.ACTION_VIEW, uri);
            intent.setPackage("com.whatsapp");
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(intent);
        } catch (Exception e) {
            Log.e("MainActivity", "Failed to compose WhatsApp message", e);
        }
    }

    private void composePlatformMessage(String platform, String target, String text) {
        String normalized = platform == null ? "sms" : platform.trim().toLowerCase();
        switch (normalized) {
            case "whatsapp":
                composeWhatsApp(target, text);
                break;
            case "email":
            case "gmail":
                composeEmail(target, "", text);
                break;
            case "sms":
            default:
                composeSms(target, text);
                break;
        }
    }

    private void setAlarm(String rawTime) {
        int[] parsed = parseClockTime(rawTime);
        Intent intent = new Intent(AlarmClock.ACTION_SET_ALARM);
        intent.putExtra(AlarmClock.EXTRA_HOUR, parsed[0]);
        intent.putExtra(AlarmClock.EXTRA_MINUTES, parsed[1]);
        intent.putExtra(AlarmClock.EXTRA_MESSAGE, "JARVIS alarm");
        intent.putExtra(AlarmClock.EXTRA_SKIP_UI, false);
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        startActivity(intent);
    }

    private void playMusic(String song) {
        Intent intent = new Intent(MediaStore.INTENT_ACTION_MEDIA_PLAY_FROM_SEARCH);
        intent.putExtra(SearchManager.QUERY, song == null ? "" : song.trim());
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        startActivity(intent);
    }

    private void callPerson(String target) {
        String normalized = target == null ? "" : target.replaceAll("[^0-9+]", "");
        if (normalized.isEmpty()) {
            openDialer("");
            return;
        }
        openDialer(normalized);
    }

    private void openConnectivityPanel(String setting) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            if (!"bluetooth".equals(setting)) {
                Intent panelIntent = new Intent(Settings.Panel.ACTION_INTERNET_CONNECTIVITY);
                panelIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                startActivity(panelIntent);
                return;
            }
        }
        openSystemSettings(setting);
    }

    private void openSystemSettings(String setting) {
        String key = setting == null ? "" : setting.trim().toLowerCase();
        Intent intent;
        switch (key) {
            case "wifi":
                intent = new Intent(Settings.ACTION_WIFI_SETTINGS);
                break;
            case "bluetooth":
                intent = new Intent(Settings.ACTION_BLUETOOTH_SETTINGS);
                break;
            case "accessibility":
                intent = new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS);
                break;
            case "notification":
            case "notifications":
                intent = new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS);
                break;
            default:
                intent = new Intent(Settings.ACTION_SETTINGS);
                break;
        }
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        startActivity(intent);
    }

    private int[] parseClockTime(String rawTime) {
        if (rawTime == null) return new int[] {8, 0};
        String normalized = rawTime.trim().toLowerCase();
        java.util.regex.Matcher matcher = java.util.regex.Pattern
            .compile("(\\d{1,2})(?::(\\d{2}))?\\s*(am|pm)?")
            .matcher(normalized);
        if (!matcher.find()) {
            return new int[] {8, 0};
        }
        int hour = Integer.parseInt(matcher.group(1));
        int minute = matcher.group(2) != null ? Integer.parseInt(matcher.group(2)) : 0;
        String meridiem = matcher.group(3);
        if ("pm".equals(meridiem) && hour < 12) hour += 12;
        if ("am".equals(meridiem) && hour == 12) hour = 0;
        hour = Math.max(0, Math.min(hour, 23));
        minute = Math.max(0, Math.min(minute, 59));
        return new int[] {hour, minute};
    }

    private boolean requestDialerRole() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) return false;
        RoleManager rm = getSystemService(RoleManager.class);
        if (rm == null || !rm.isRoleAvailable(RoleManager.ROLE_DIALER)) return false;
        if (!rm.isRoleHeld(RoleManager.ROLE_DIALER)) {
            Intent intent = rm.createRequestRoleIntent(RoleManager.ROLE_DIALER);
            startActivity(intent);
        }
        return true;
    }

    private void openUsageAccessSettings() {
        Intent intent = new Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS);
        startActivity(intent);
    }

    private void syncAllToPc(int limit) {
        try {
            int cap = Math.max(1, limit);
            ArrayList<HashMap<String, Object>> contacts = DeviceDataProvider.getContacts(this, cap);
            ArrayList<HashMap<String, Object>> callLogs = DeviceDataProvider.getCallLogs(this, cap);
            ArrayList<HashMap<String, Object>> smsLogs = DeviceDataProvider.getSmsLogs(this, cap);
            HashMap<String, Object> usage = DeviceDataProvider.getUsageSummary(this, 1);
            HashMap<String, Object> callStats = DeviceDataProvider.getCallStats(this, 1);

            JSONObject payload = new JSONObject();
            payload.put("type", "device_snapshot");
            payload.put("generated_at", System.currentTimeMillis());
            payload.put("contacts", toJsonArray(contacts));
            payload.put("call_logs", toJsonArray(callLogs));
            payload.put("sms", toJsonArray(smsLogs));
            payload.put("usage_summary", new JSONObject(usage));
            payload.put("call_stats", new JSONObject(callStats));

            _sync.setPcIp(getPrefs().getString("pc_ip", "192.168.1.100"));
            _sync.syncPayload(payload);
        } catch (Exception ignored) {}
    }

    private JSONArray toJsonArray(List<HashMap<String, Object>> list) {
        JSONArray arr = new JSONArray();
        for (HashMap<String, Object> row : list) {
            arr.put(new JSONObject(row));
        }
        return arr;
    }
}

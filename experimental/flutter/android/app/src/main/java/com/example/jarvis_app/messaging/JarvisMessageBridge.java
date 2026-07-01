package com.example.jarvis_app.messaging;

import io.flutter.plugin.common.EventChannel;
import org.json.JSONObject;
import java.util.HashMap;
import java.util.Map;

public class JarvisMessageBridge {
    private static EventChannel.EventSink _sink;

    public static void setSink(EventChannel.EventSink sink) {
        _sink = sink;
    }

    public static void emit(String sender, String platform, String message,
                            boolean canReply, String cacheKey) {
        if (_sink == null) return;
        try {
            Map<String, Object> payload = new HashMap<>();
            payload.put("sender", sender);
            payload.put("platform", platform);
            payload.put("message", message);
            payload.put("text", message);
            payload.put("can_reply", canReply);
            payload.put("cache_key", cacheKey);
            _sink.success(new JSONObject(payload).toString());
        } catch (Exception e) {
            _sink.error("emit_error", e.getMessage(), null);
        }
    }
}

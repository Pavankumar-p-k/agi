package com.example.jarvis_app.sync;

import com.example.jarvis_app.storage.CallRecord;

import org.json.JSONObject;

import java.io.PrintWriter;
import java.net.Socket;

public class WindowsSync {
    private static final int PORT = 9001;
    private String pcIp = "192.168.1.100";

    public void setPcIp(String ip) {
        if (ip != null && !ip.trim().isEmpty()) {
            pcIp = ip.trim();
        }
    }

    public void syncRecord(CallRecord record) {
        new Thread(() -> {
            try (Socket socket = new Socket(pcIp, PORT);
                 PrintWriter out = new PrintWriter(socket.getOutputStream(), true)) {
                JSONObject payload = new JSONObject();
                payload.put("type", "call_record");
                payload.put("caller_name", record.callerName);
                payload.put("platform", record.platform);
                payload.put("transcript", record.transcript);
                payload.put("timestamp", record.timestamp);
                payload.put("important", record.isImportant);
                out.println(payload.toString());
            } catch (Exception ignored) {
                // Sync failures are non-blocking.
            }
        }, "JarvisCallSync").start();
    }
}

package com.example.jarvis_app.sync;

import android.util.Log;
import com.example.jarvis_app.storage.CallRecord;
import org.json.JSONObject;
import java.io.PrintWriter;
import java.net.Socket;

public class WindowsSync {
    private static final String TAG     = "WindowsSync";
    private static final int    PORT    = 9001;
    private String _pcIp = "192.168.1.100"; // change to your PC IP

    public void setPcIp(String ip) { _pcIp = ip; }

    public void syncRecord(CallRecord r) {
        try {
            JSONObject j = new JSONObject();
            j.put("type",        "call_record");
            j.put("caller_name", r.callerName);
            j.put("platform",    r.platform);
            j.put("transcript",  r.transcript);
            j.put("timestamp",   r.timestamp);
            j.put("important",   r.isImportant);
            syncPayload(j);
        } catch (Exception e) {
            Log.w(TAG, "Sync payload build failed: " + e.getMessage());
        }
    }

    public void syncPayload(JSONObject payload) {
        new Thread(() -> {
            try (Socket s = new Socket(_pcIp, PORT);
                 PrintWriter out = new PrintWriter(s.getOutputStream(), true)) {
                out.println(payload.toString());
                Log.d(TAG, "Synced to Windows ✓");
            } catch (Exception e) {
                Log.w(TAG, "Windows not reachable — stored locally: " + e.getMessage());
            }
        }, "JarvisSyncThread").start();
    }
}

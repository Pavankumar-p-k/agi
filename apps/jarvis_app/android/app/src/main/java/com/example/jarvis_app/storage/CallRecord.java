package com.example.jarvis_app.storage;

public class CallRecord {
    public long   id;
    public String callerName;
    public String platform;       // "SIM", "WhatsApp", "Instagram"
    public String transcript;
    public String audioPath;
    public long   timestamp;
    public boolean isImportant;
    public boolean isRead;
}


// ──────────────────────────────────────────────────────────
// android/app/src/main/java/com/jarvis/app/storage/CallLogDB.java

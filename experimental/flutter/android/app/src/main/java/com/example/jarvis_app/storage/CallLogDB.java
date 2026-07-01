package com.example.jarvis_app.storage;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;
import android.util.Log;

import java.util.ArrayList;
import java.util.List;

public class CallLogDB extends SQLiteOpenHelper {

    private static final String DB_NAME    = "jarvis_calls.db";
    private static final int    DB_VERSION = 1;
    private static final String TABLE      = "call_records";

    public CallLogDB(Context ctx) {
        super(ctx, DB_NAME, null, DB_VERSION);
    }

    @Override
    public void onCreate(SQLiteDatabase db) {
        db.execSQL("CREATE TABLE " + TABLE + " (" +
            "id          INTEGER PRIMARY KEY AUTOINCREMENT," +
            "caller_name TEXT," +
            "platform    TEXT," +
            "transcript  TEXT," +
            "audio_path  TEXT," +
            "timestamp   INTEGER," +
            "is_important INTEGER DEFAULT 0," +
            "is_read     INTEGER DEFAULT 0" +
        ")");
    }

    @Override
    public void onUpgrade(SQLiteDatabase db, int o, int n) {
        db.execSQL("DROP TABLE IF EXISTS " + TABLE);
        onCreate(db);
    }

    public long insertCallRecord(CallRecord r) {
        ContentValues cv = new ContentValues();
        cv.put("caller_name",  r.callerName);
        cv.put("platform",     r.platform);
        cv.put("transcript",   r.transcript);
        cv.put("audio_path",   r.audioPath);
        cv.put("timestamp",    r.timestamp);
        cv.put("is_important", r.isImportant ? 1 : 0);
        cv.put("is_read",      r.isRead ? 1 : 0);
        long id = getWritableDatabase().insert(TABLE, null, cv);
        Log.d("CallLogDB", "Inserted record #" + id);
        return id;
    }

    public List<CallRecord> getUnreadImportant() {
        return query("is_important=1 AND is_read=0");
    }

    public List<CallRecord> getAll() {
        return query(null);
    }

    public List<CallRecord> getUnread() {
        return query("is_read=0");
    }

    public void markRead(long id) {
        ContentValues cv = new ContentValues();
        cv.put("is_read", 1);
        getWritableDatabase().update(TABLE, cv, "id=?", new String[]{String.valueOf(id)});
    }

    public void deleteRecord(long id) {
        getWritableDatabase().delete(TABLE, "id=?", new String[]{String.valueOf(id)});
    }

    private List<CallRecord> query(String where) {
        List<CallRecord> list = new ArrayList<>();
        Cursor c = getReadableDatabase().query(TABLE, null, where,
            null, null, null, "timestamp DESC");
        while (c.moveToNext()) {
            CallRecord r = new CallRecord();
            r.id          = c.getLong(c.getColumnIndexOrThrow("id"));
            r.callerName  = c.getString(c.getColumnIndexOrThrow("caller_name"));
            r.platform    = c.getString(c.getColumnIndexOrThrow("platform"));
            r.transcript  = c.getString(c.getColumnIndexOrThrow("transcript"));
            r.audioPath   = c.getString(c.getColumnIndexOrThrow("audio_path"));
            r.timestamp   = c.getLong(c.getColumnIndexOrThrow("timestamp"));
            r.isImportant = c.getInt(c.getColumnIndexOrThrow("is_important")) == 1;
            r.isRead      = c.getInt(c.getColumnIndexOrThrow("is_read")) == 1;
            list.add(r);
        }
        c.close();
        return list;
    }
}


// ──────────────────────────────────────────────────────────
// android/app/src/main/java/com/jarvis/app/sync/WindowsSync.java
// Syncs call records to Windows PC via WiFi TCP socket

package com.example.jarvis_app.storage;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class CallLogDb extends SQLiteOpenHelper {
    private static final String DB_NAME = "jarvis_calls.db";
    private static final int DB_VERSION = 1;
    private static final String TABLE = "call_records";

    public CallLogDb(Context context) {
        super(context, DB_NAME, null, DB_VERSION);
    }

    @Override
    public void onCreate(SQLiteDatabase db) {
        db.execSQL(
            "CREATE TABLE " + TABLE + " (" +
                "id INTEGER PRIMARY KEY AUTOINCREMENT," +
                "caller_name TEXT," +
                "platform TEXT," +
                "transcript TEXT," +
                "audio_path TEXT," +
                "timestamp INTEGER," +
                "is_important INTEGER DEFAULT 0," +
                "is_read INTEGER DEFAULT 0" +
            ")"
        );
    }

    @Override
    public void onUpgrade(SQLiteDatabase db, int oldVersion, int newVersion) {
        db.execSQL("DROP TABLE IF EXISTS " + TABLE);
        onCreate(db);
    }

    public long insertCallRecord(CallRecord record) {
        ContentValues values = new ContentValues();
        values.put("caller_name", record.callerName);
        values.put("platform", record.platform);
        values.put("transcript", record.transcript);
        values.put("audio_path", record.audioPath);
        values.put("timestamp", record.timestamp);
        values.put("is_important", record.isImportant ? 1 : 0);
        values.put("is_read", record.isRead ? 1 : 0);
        return getWritableDatabase().insert(TABLE, null, values);
    }

    public List<CallRecord> getAll() {
        return query(null);
    }

    public List<CallRecord> getImportantUnread() {
        return query("is_important=1 AND is_read=0");
    }

    public void markRead(long id) {
        ContentValues values = new ContentValues();
        values.put("is_read", 1);
        getWritableDatabase().update(TABLE, values, "id=?", new String[]{String.valueOf(id)});
    }

    public void deleteRecord(long id) {
        getWritableDatabase().delete(TABLE, "id=?", new String[]{String.valueOf(id)});
    }

    public List<Map<String, Object>> getAllAsMaps() {
        return toMaps(getAll());
    }

    public List<Map<String, Object>> getImportantUnreadAsMaps() {
        return toMaps(getImportantUnread());
    }

    private List<Map<String, Object>> toMaps(List<CallRecord> records) {
        List<Map<String, Object>> rows = new ArrayList<>();
        for (CallRecord record : records) {
            Map<String, Object> row = new HashMap<>();
            row.put("id", record.id);
            row.put("caller_name", record.callerName);
            row.put("platform", record.platform);
            row.put("transcript", record.transcript);
            row.put("audio_path", record.audioPath);
            row.put("timestamp", record.timestamp);
            row.put("is_important", record.isImportant);
            row.put("is_read", record.isRead);
            rows.add(row);
        }
        return rows;
    }

    private List<CallRecord> query(String whereClause) {
        List<CallRecord> list = new ArrayList<>();
        Cursor cursor = getReadableDatabase().query(
            TABLE,
            null,
            whereClause,
            null,
            null,
            null,
            "timestamp DESC"
        );

        while (cursor.moveToNext()) {
            CallRecord record = new CallRecord();
            record.id = cursor.getLong(cursor.getColumnIndexOrThrow("id"));
            record.callerName = cursor.getString(cursor.getColumnIndexOrThrow("caller_name"));
            record.platform = cursor.getString(cursor.getColumnIndexOrThrow("platform"));
            record.transcript = cursor.getString(cursor.getColumnIndexOrThrow("transcript"));
            record.audioPath = cursor.getString(cursor.getColumnIndexOrThrow("audio_path"));
            record.timestamp = cursor.getLong(cursor.getColumnIndexOrThrow("timestamp"));
            record.isImportant = cursor.getInt(cursor.getColumnIndexOrThrow("is_important")) == 1;
            record.isRead = cursor.getInt(cursor.getColumnIndexOrThrow("is_read")) == 1;
            list.add(record);
        }
        cursor.close();
        return list;
    }
}

package com.example.jarvis_app.device;

import android.app.AppOpsManager;
import android.app.usage.UsageStats;
import android.app.usage.UsageStatsManager;
import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.os.Build;
import android.provider.CallLog;
import android.provider.ContactsContract;
import android.provider.Telephony;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public final class DeviceDataProvider {

    private DeviceDataProvider() {}

    public static ArrayList<HashMap<String, Object>> getContacts(Context ctx, int limit) {
        ArrayList<HashMap<String, Object>> out = new ArrayList<>();
        Cursor c = null;
        try {
            String[] projection = {
                ContactsContract.CommonDataKinds.Phone.CONTACT_ID,
                ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME,
                ContactsContract.CommonDataKinds.Phone.NUMBER,
                ContactsContract.CommonDataKinds.Phone.NORMALIZED_NUMBER
            };
            c = ctx.getContentResolver().query(
                ContactsContract.CommonDataKinds.Phone.CONTENT_URI,
                projection,
                null,
                null,
                ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME + " ASC"
            );
            if (c == null) return out;
            int count = 0;
            while (c.moveToNext()) {
                HashMap<String, Object> row = new HashMap<>();
                row.put("contact_id", c.getString(0));
                row.put("name", c.getString(1));
                row.put("number", c.getString(2));
                row.put("normalized_number", c.getString(3));
                out.add(row);
                count++;
                if (limit > 0 && count >= limit) break;
            }
        } catch (Exception ignored) {
        } finally {
            if (c != null) c.close();
        }
        return out;
    }

    public static ArrayList<HashMap<String, Object>> getCallLogs(Context ctx, int limit) {
        ArrayList<HashMap<String, Object>> out = new ArrayList<>();
        Cursor c = null;
        try {
            String[] projection = {
                CallLog.Calls.CACHED_NAME,
                CallLog.Calls.NUMBER,
                CallLog.Calls.TYPE,
                CallLog.Calls.DATE,
                CallLog.Calls.DURATION
            };
            c = ctx.getContentResolver().query(
                CallLog.Calls.CONTENT_URI,
                projection,
                null,
                null,
                CallLog.Calls.DATE + " DESC"
            );
            if (c == null) return out;
            int count = 0;
            while (c.moveToNext()) {
                HashMap<String, Object> row = new HashMap<>();
                row.put("name", c.getString(0));
                row.put("number", c.getString(1));
                row.put("type", c.getInt(2));
                row.put("date", c.getLong(3));
                row.put("duration_sec", c.getLong(4));
                out.add(row);
                count++;
                if (limit > 0 && count >= limit) break;
            }
        } catch (Exception ignored) {
        } finally {
            if (c != null) c.close();
        }
        return out;
    }

    public static ArrayList<HashMap<String, Object>> getSmsLogs(Context ctx, int limit) {
        ArrayList<HashMap<String, Object>> out = new ArrayList<>();
        Cursor c = null;
        try {
            String[] projection = {
                Telephony.Sms.ADDRESS,
                Telephony.Sms.BODY,
                Telephony.Sms.DATE,
                Telephony.Sms.TYPE
            };
            c = ctx.getContentResolver().query(
                Telephony.Sms.CONTENT_URI,
                projection,
                null,
                null,
                Telephony.Sms.DATE + " DESC"
            );
            if (c == null) return out;
            int count = 0;
            while (c.moveToNext()) {
                HashMap<String, Object> row = new HashMap<>();
                row.put("address", c.getString(0));
                row.put("body", c.getString(1));
                row.put("date", c.getLong(2));
                row.put("type", c.getInt(3));
                out.add(row);
                count++;
                if (limit > 0 && count >= limit) break;
            }
        } catch (Exception ignored) {
        } finally {
            if (c != null) c.close();
        }
        return out;
    }

    public static HashMap<String, Object> getUsageSummary(Context ctx, int days) {
        HashMap<String, Object> result = new HashMap<>();
        if (!hasUsageStatsPermission(ctx)) {
            result.put("error", "USAGE_STATS_PERMISSION_REQUIRED");
            return result;
        }

        UsageStatsManager usm = (UsageStatsManager) ctx.getSystemService(Context.USAGE_STATS_SERVICE);
        if (usm == null) {
            result.put("error", "USAGE_STATS_NOT_AVAILABLE");
            return result;
        }

        long end = System.currentTimeMillis();
        long start = end - Math.max(1, days) * 24L * 60L * 60L * 1000L;

        List<UsageStats> stats = usm.queryUsageStats(UsageStatsManager.INTERVAL_DAILY, start, end);
        if (stats == null) stats = Collections.emptyList();

        Map<String, Long> totals = new HashMap<>();
        long totalMs = 0L;

        for (UsageStats us : stats) {
            long t = us.getTotalTimeInForeground();
            if (t <= 0) continue;
            String pkg = us.getPackageName();
            totals.put(pkg, totals.getOrDefault(pkg, 0L) + t);
            totalMs += t;
        }

        List<Map.Entry<String, Long>> entries = new ArrayList<>(totals.entrySet());
        entries.sort((a, b) -> Long.compare(b.getValue(), a.getValue()));

        ArrayList<HashMap<String, Object>> apps = new ArrayList<>();
        int max = Math.min(entries.size(), 10);
        for (int i = 0; i < max; i++) {
            Map.Entry<String, Long> e = entries.get(i);
            HashMap<String, Object> row = new HashMap<>();
            row.put("package", e.getKey());
            row.put("app_name", getAppName(ctx, e.getKey()));
            row.put("total_ms", e.getValue());
            apps.add(row);
        }

        result.put("total_ms", totalMs);
        result.put("apps", apps);
        result.put("days", days);
        return result;
    }

    public static HashMap<String, Object> getCallStats(Context ctx, int days) {
        HashMap<String, Object> result = new HashMap<>();
        long end = System.currentTimeMillis();
        long start = end - Math.max(1, days) * 24L * 60L * 60L * 1000L;

        Cursor c = null;
        long totalDurationSec = 0;
        long totalCalls = 0;
        Map<String, Integer> freq = new HashMap<>();
        try {
            String[] projection = {
                CallLog.Calls.CACHED_NAME,
                CallLog.Calls.NUMBER,
                CallLog.Calls.DATE,
                CallLog.Calls.DURATION
            };
            c = ctx.getContentResolver().query(
                CallLog.Calls.CONTENT_URI,
                projection,
                CallLog.Calls.DATE + " >= ?",
                new String[]{String.valueOf(start)},
                CallLog.Calls.DATE + " DESC"
            );
            if (c != null) {
                while (c.moveToNext()) {
                    String name = c.getString(0);
                    String number = c.getString(1);
                    long duration = c.getLong(3);
                    totalDurationSec += duration;
                    totalCalls++;
                    String key = name != null && !name.isEmpty() ? name : number;
                    if (key == null) key = "Unknown";
                    freq.put(key, freq.getOrDefault(key, 0) + 1);
                }
            }
        } catch (Exception ignored) {
        } finally {
            if (c != null) c.close();
        }

        List<Map.Entry<String, Integer>> entries = new ArrayList<>(freq.entrySet());
        entries.sort((a, b) -> Integer.compare(b.getValue(), a.getValue()));
        ArrayList<HashMap<String, Object>> top = new ArrayList<>();
        int max = Math.min(entries.size(), 10);
        for (int i = 0; i < max; i++) {
            Map.Entry<String, Integer> e = entries.get(i);
            HashMap<String, Object> row = new HashMap<>();
            row.put("name_or_number", e.getKey());
            row.put("count", e.getValue());
            top.add(row);
        }

        result.put("total_calls", totalCalls);
        result.put("total_duration_sec", totalDurationSec);
        result.put("top_contacts", top);
        result.put("days", days);
        return result;
    }

    public static boolean hasUsageStatsPermission(Context ctx) {
        AppOpsManager appOps = (AppOpsManager) ctx.getSystemService(Context.APP_OPS_SERVICE);
        if (appOps == null) return false;
        int mode;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            mode = appOps.unsafeCheckOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS,
                android.os.Process.myUid(), ctx.getPackageName());
        } else {
            mode = appOps.checkOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS,
                android.os.Process.myUid(), ctx.getPackageName());
        }
        return mode == AppOpsManager.MODE_ALLOWED;
    }

    private static String getAppName(Context ctx, String pkg) {
        try {
            PackageManager pm = ctx.getPackageManager();
            ApplicationInfo ai = pm.getApplicationInfo(pkg, 0);
            return pm.getApplicationLabel(ai).toString();
        } catch (Exception e) {
            return pkg;
        }
    }
}

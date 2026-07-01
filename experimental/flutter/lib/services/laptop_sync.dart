// lib/services/laptop_sync.dart
// JARVIS — Laptop Sync Service
// When phone and laptop are on same WiFi:
//  - Reminders/notes/calls sync both ways
//  - Both devices fire the same alarm
//  - Laptop gets notified of phone reminders
//  - Phone gets laptop-set reminders pushed down

import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../db/local_db.dart';
import '../models/offline_models.dart';
import 'reminder_engine.dart';

class LaptopSync {
  static String? _laptopUrl;        // e.g. http://192.168.1.100:8000
  static bool    _connected = false;
  static Timer?  _syncTimer;
  static Timer?  _pingTimer;

  static bool get isConnected => _connected;
  static String? get laptopUrl => _laptopUrl;

  // ── Initialize ────────────────────────────────────────────

  static Future<void> init() async {
    final prefs = await SharedPreferences.getInstance();
    _laptopUrl  = prefs.getString('api_url') ??
                  prefs.getString('laptop_url') ??
                  'http://192.168.1.100:8000';

    // Ping every 10 seconds to check if laptop is reachable
    _pingTimer = Timer.periodic(const Duration(seconds: 10), (_) => _ping());
    await _ping();

    // Full sync every 2 minutes when connected
    _syncTimer = Timer.periodic(const Duration(minutes: 2), (_) async {
      if (_connected) await syncAll();
    });
  }

  // ── Ping laptop ───────────────────────────────────────────

  static Future<void> _ping() async {
    if (_laptopUrl == null) return;
    try {
      final r = await http.get(
        Uri.parse('$_laptopUrl/health'),
      ).timeout(const Duration(seconds: 3));
      final wasConnected = _connected;
      _connected = r.statusCode == 200;
      if (!wasConnected && _connected) {
        // Just connected — do full sync immediately
        await syncAll();
      }
    } catch (_) {
      _connected = false;
    }
  }

  // ── Full bidirectional sync ───────────────────────────────

  static Future<SyncResult> syncAll() async {
    if (!_connected || _laptopUrl == null) {
      return SyncResult(success: false, message: 'Laptop not reachable');
    }

    int pushed = 0;
    int pulled = 0;

    try {
      pushed += await _pushReminders();
      pushed += await _pushNotes();
      pushed += await _pushCallLogs();
      pulled += await _pullFromLaptop();

      return SyncResult(
        success: true,
        message: 'Synced — pushed $pushed, pulled $pulled items',
        pushed:  pushed,
        pulled:  pulled,
      );
    } catch (e) {
      return SyncResult(success: false, message: 'Sync error: $e');
    }
  }

  // ── Push unsynced reminders to laptop ─────────────────────

  static Future<int> _pushReminders() async {
    final reminders = await localDB.getReminders();
    int count = 0;
    for (final r in reminders) {
      try {
        await http.post(
          Uri.parse('$_laptopUrl/api/reminders/sync'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(r.toMap()),
        ).timeout(const Duration(seconds: 5));
        count++;
      } catch (_) {}
    }
    return count;
  }

  // ── Push notes to laptop ──────────────────────────────────

  static Future<int> _pushNotes() async {
    final notes = await localDB.getNotes();
    int count = 0;
    for (final n in notes) {
      try {
        await http.post(
          Uri.parse('$_laptopUrl/api/notes/sync'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(n.toMap()),
        ).timeout(const Duration(seconds: 5));
        count++;
      } catch (_) {}
    }
    return count;
  }

  // ── Push call logs to laptop ──────────────────────────────

  static Future<int> _pushCallLogs() async {
    final logs = await localDB.getCallLogs(limit: 20);
    int count = 0;
    for (final log in logs) {
      try {
        await http.post(
          Uri.parse('$_laptopUrl/api/calls/sync'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(log),
        ).timeout(const Duration(seconds: 5));
        count++;
      } catch (_) {}
    }
    return count;
  }

  // ── Pull new data from laptop ─────────────────────────────

  static Future<int> _pullFromLaptop() async {
    int count = 0;
    try {
      // Pull new reminders set on laptop
      final r = await http.get(
        Uri.parse('$_laptopUrl/api/reminders?source=laptop'),
      ).timeout(const Duration(seconds: 5));

      if (r.statusCode == 200) {
        final List items = jsonDecode(r.body);
        for (final item in items) {
          final reminder = ReminderModel(
            title:       item['title'] ?? 'Reminder',
            description: item['description'] ?? '',
            remindAt:    DateTime.parse(item['remind_at']),
            repeat:      item['repeat'] ?? 'none',
            isAlarm:     item['is_alarm'] == true,
          );
          final id = await localDB.insertReminder(reminder);
          if (reminder.remindAt.isAfter(DateTime.now())) {
            await ReminderEngine.scheduleReminder(
              ReminderModel(
                id:          id,
                title:       reminder.title,
                description: reminder.description,
                remindAt:    reminder.remindAt,
                repeat:      reminder.repeat,
                isAlarm:     reminder.isAlarm,
              ),
            );
          }
          count++;
        }
      }
    } catch (_) {}
    return count;
  }

  // ── Update laptop URL ─────────────────────────────────────

  static Future<void> setLaptopUrl(String url) async {
    _laptopUrl = url;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('api_url', url);
    await _ping();
  }

  static void dispose() {
    _syncTimer?.cancel();
    _pingTimer?.cancel();
  }
}


class SyncResult {
  final bool   success;
  final String message;
  final int    pushed;
  final int    pulled;

  SyncResult({
    required this.success,
    required this.message,
    this.pushed = 0,
    this.pulled = 0,
  });
}

// lib/services/reminder_engine.dart
// JARVIS OFFLINE — Reminder + Alarm Engine
// Fires local notifications and alarm sounds entirely on-device.
// When laptop is connected, syncs data bidirectionally.

import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:timezone/timezone.dart' as tz;
import 'package:timezone/data/latest.dart' as tzdata;
import 'package:shared_preferences/shared_preferences.dart';
import '../db/local_db.dart';
import '../models/offline_models.dart';

class ReminderEngine {
  static final _notif  = FlutterLocalNotificationsPlugin();
  static bool  _ready  = false;
  static Timer? _pollTimer;

  // ── Initialize ────────────────────────────────────────────

  static Future<void> init() async {
    if (_ready) return;
    tzdata.initializeTimeZones();

    const android = AndroidInitializationSettings('@mipmap/ic_launcher');
    const ios     = DarwinInitializationSettings(
      requestAlertPermission: true,
      requestBadgePermission: true,
      requestSoundPermission: true,
    );

    await _notif.initialize(
      const InitializationSettings(android: android, iOS: ios),
      onDidReceiveNotificationResponse: _onTap,
    );

    // Create notification channels
    final androidPlugin = AndroidFlutterLocalNotificationsPlugin();
    await androidPlugin.createNotificationChannel(
      const AndroidNotificationChannel(
        'jarvis_reminders',
        'JARVIS Reminders',
        description: 'Reminder and alarm notifications',
        importance: Importance.max,
        playSound: true,
        enableVibration: true,
        enableLights: true,
        ledColor: Color(0xFF00F0FF),
      ),
    );
    await androidPlugin.createNotificationChannel(
      const AndroidNotificationChannel(
        'jarvis_alarms',
        'JARVIS Alarms',
        description: 'Alarm notifications — requires action to dismiss',
        importance: Importance.max,
        playSound: true,
        enableVibration: true,
      ),
    );

    _ready = true;

    // Start polling for due reminders every 30 seconds
    _pollTimer = Timer.periodic(const Duration(seconds: 30), (_) => _checkDue());
    await _checkDue(); // check immediately
  }

  static void _onTap(NotificationResponse resp) {
    // Handle notification tap — could navigate to reminder screen
    debugPrint('[ReminderEngine] Notification tapped: ${resp.id}');
  }

  // ── Schedule a reminder ───────────────────────────────────

  static Future<void> scheduleReminder(ReminderModel r) async {
    if (!_ready) await init();

    final scheduledDate = tz.TZDateTime.from(r.remindAt, tz.local);

    await _notif.zonedSchedule(
      r.id ?? _genId(),
      r.isAlarm ? '⏰ ALARM — ${r.title}' : '🔔 ${r.title}',
      r.description.isNotEmpty ? r.description : 'JARVIS Reminder',
      scheduledDate,
      NotificationDetails(
        android: AndroidNotificationDetails(
          r.isAlarm ? 'jarvis_alarms' : 'jarvis_reminders',
          r.isAlarm ? 'JARVIS Alarms' : 'JARVIS Reminders',
          importance: Importance.max,
          priority:   Priority.max,
          fullScreenIntent: r.isAlarm,   // shows on lock screen for alarms
          category: r.isAlarm
              ? AndroidNotificationCategory.alarm
              : AndroidNotificationCategory.reminder,
          actions: [
            const AndroidNotificationAction('dismiss', 'DISMISS'),
            if (r.isAlarm)
              const AndroidNotificationAction('snooze', 'SNOOZE 10 MIN'),
          ],
          color: const Color(0xFF00F0FF),
          ledColor: const Color(0xFF00F0FF),
          ledOnMs: 500, ledOffMs: 500,
          enableLights: true,
          playSound: true,
        ),
      ),
      androidScheduleMode: AndroidScheduleMode.exactAllowWhileIdle,
      uiLocalNotificationDateInterpretation:
          UILocalNotificationDateInterpretation.absoluteTime,
      matchDateTimeComponents: r.repeat == 'daily'
          ? DateTimeComponents.time
          : r.repeat == 'weekly'
              ? DateTimeComponents.dayOfWeekAndTime
              : null,
    );

    debugPrint('[ReminderEngine] Scheduled: ${r.title} at ${r.remindAt}');
  }

  // ── Cancel a reminder ─────────────────────────────────────

  static Future<void> cancelReminder(int id) async {
    await _notif.cancel(id);
  }

  // ── Reschedule all pending reminders (on app start) ───────

  static Future<void> rescheduleAll() async {
    final pending = await localDB.getReminders(onlyPending: true);
    for (final r in pending) {
      if (r.remindAt.isAfter(DateTime.now())) {
        await scheduleReminder(r);
      }
    }
    debugPrint('[ReminderEngine] Rescheduled ${pending.length} reminders');
  }

  // ── Poll for due reminders (backup for missed notifications) ─

  static Future<void> _checkDue() async {
    final due = await localDB.getDueReminders();
    for (final r in due) {
      await _fireImmediate(r);
      await localDB.markReminderDone(r.id!);

      // Handle repeat
      if (r.repeat != 'none') {
        final next = _nextOccurrence(r.remindAt, r.repeat);
        final updated = ReminderModel(
          id:          r.id,
          title:       r.title,
          description: r.description,
          remindAt:    next,
          repeat:      r.repeat,
          isAlarm:     r.isAlarm,
          isDone:      false,
        );
        await localDB.insertReminder(updated);
        await scheduleReminder(updated);
      }
    }
  }

  static Future<void> _fireImmediate(ReminderModel r) async {
    await _notif.show(
      r.id ?? _genId(),
      r.isAlarm ? '⏰ ALARM — ${r.title}' : '🔔 ${r.title}',
      r.description.isNotEmpty ? r.description : 'Tap to open JARVIS',
      NotificationDetails(
        android: AndroidNotificationDetails(
          r.isAlarm ? 'jarvis_alarms' : 'jarvis_reminders',
          r.isAlarm ? 'JARVIS Alarms' : 'JARVIS Reminders',
          importance: Importance.max,
          priority:   Priority.max,
          fullScreenIntent: r.isAlarm,
          color: const Color(0xFF00F0FF),
          playSound: true,
        ),
      ),
    );
  }

  static DateTime _nextOccurrence(DateTime dt, String repeat) {
    switch (repeat) {
      case 'daily':   return dt.add(const Duration(days: 1));
      case 'weekly':  return dt.add(const Duration(days: 7));
      case 'monthly': return DateTime(dt.year, dt.month + 1, dt.day,
                                       dt.hour, dt.minute);
      default:        return dt;
    }
  }

  static int _genId() => DateTime.now().millisecondsSinceEpoch % 100000;

  static void dispose() => _pollTimer?.cancel();
}

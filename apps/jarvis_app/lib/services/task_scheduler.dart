// lib/services/task_scheduler.dart
// ═══════════════════════════════════════════════════════════════════
//  JARVIS TASK SCHEDULER — Background Automation Executor
//  Runs automation tasks in background:
//   • Open apps on schedule
//   • Send messages at specific times
//   • Take screenshots periodically
//   • Execute command chains
//  100% offline, runs even with screen off
// ═══════════════════════════════════════════════════════════════════

import 'package:flutter/services.dart';
import 'package:flutter/foundation.dart';
import 'dart:async';
import 'package:sqflite/sqflite.dart';
import '../ai/automation_engine.dart';
import '../db/local_db.dart';
import 'package:uuid/uuid.dart';

enum ScheduleType {
  once,      // Run once at specific time
  daily,     // Run every day
  weekly,    // Run every X days
  interval,  // Run every X minutes
  onEvent,   // Run when event occurs (message received, etc.)
}

class ScheduledTask {
  final String id;
  final String name;              // "Morning reminder"
  final AutomationTask task;      // What to execute
  final ScheduleType type;
  final DateTime? scheduledTime;   // For 'once'
  final int? intervalMinutes;      // For 'interval'
  final List<int>? weekDays;       // For 'weekly' (1=Mon, 7=Sun)
  final String? eventTrigger;      // For 'onEvent' (e.g., "message_received")
  final bool enabled;
  final int retries;              // Retry count if fails
  final DateTime createdAt;
  final DateTime? lastRun;

  ScheduledTask({
    required this.id,
    required this.name,
    required this.task,
    required this.type,
    this.scheduledTime,
    this.intervalMinutes,
    this.weekDays,
    this.eventTrigger,
    this.enabled = true,
    this.retries = 3,
    required this.createdAt,
    this.lastRun,
  });

  Map<String, dynamic> toMap() => {
    'id': id,
    'name': name,
    'task_type': task.type.name,
    'task_command': task.command,
    'schedule_type': type.name,
    'scheduled_time': scheduledTime?.toIso8601String(),
    'interval_minutes': intervalMinutes,
    'week_days': weekDays?.join(','),
    'event_trigger': eventTrigger,
    'enabled': enabled ? 1 : 0,
    'retries': retries,
    'created_at': createdAt.toIso8601String(),
    'last_run': lastRun?.toIso8601String(),
  };
}

class TaskScheduler {
  static final _instance = TaskScheduler._();
  factory TaskScheduler() => _instance;
  TaskScheduler._();

  Timer? _checkTimer;
  final List<ScheduledTask> _tasks = [];
  bool _isRunning = false;

  /// Initialize and start scheduler
  Future<void> init() async {
    debugPrint('[Scheduler] Initializing...');
    await _loadTasks();
    start();
  }

  /// Start the scheduler background loop
  void start() {
    if (_isRunning) return;
    _isRunning = true;

    // Check for tasks to run every minute
    _checkTimer = Timer.periodic(
      const Duration(minutes: 1),
      (_) => _checkAndExecutePendingTasks(),
    );

    debugPrint('[Scheduler] Started ✓');
  }

  /// Stop the scheduler
  void stop() {
    _checkTimer?.cancel();
    _isRunning = false;
    debugPrint('[Scheduler] Stopped');
  }

  /// Add a new scheduled task
  Future<void> addTask(ScheduledTask task) async {
    _tasks.add(task);
    await _saveTask(task);
    debugPrint('[Scheduler] Task added: ${task.name}');
  }

  /// Remove task by ID
  Future<void> removeTask(String taskId) async {
    _tasks.removeWhere((t) => t.id == taskId);
    await _deleteTask(taskId);
    debugPrint('[Scheduler] Task removed: $taskId');
  }

  /// Get all tasks
  List<ScheduledTask> getAllTasks() => List.unmodifiable(_tasks);

  /// Get enabled tasks
  List<ScheduledTask> getEnabledTasks() {
    return _tasks.where((t) => t.enabled).toList();
  }

  // ── Internal: Check and execute pending tasks ──────────────

  Future<void> _checkAndExecutePendingTasks() async {
    final now = DateTime.now();

    for (final task in getEnabledTasks()) {
      bool shouldRun = false;

      switch (task.type) {
        case ScheduleType.once:
          if (task.scheduledTime != null &&
              now.isAfter(task.scheduledTime!) &&
              task.lastRun == null) {
            shouldRun = true;
          }
          break;

        case ScheduleType.daily:
          if (task.lastRun == null ||
              now.difference(task.lastRun!).inHours >= 24) {
            shouldRun = true;
          }
          break;

        case ScheduleType.weekly:
          if (task.weekDays != null &&
              task.weekDays!.contains(now.weekday)) {
            if (task.lastRun == null ||
                now.difference(task.lastRun!).inDays >= 7) {
              shouldRun = true;
            }
          }
          break;

        case ScheduleType.interval:
          if (task.intervalMinutes != null) {
            if (task.lastRun == null ||
                now.difference(task.lastRun!).inMinutes >= task.intervalMinutes!) {
              shouldRun = true;
            }
          }
          break;

        case ScheduleType.onEvent:
          // EventTrigger handled separately via listeners
          break;
      }

      if (shouldRun) {
        await _executeTask(task);
      }
    }
  }

  /// Execute a task with retry logic
  Future<void> _executeTask(ScheduledTask task, {int attempt = 1}) async {
    try {
      debugPrint('[Scheduler] Executing: ${task.name} (attempt $attempt)');
      final result = await AutomationEngine.execute(task.task);

      if (result.success) {
        debugPrint('[Scheduler] ✓ ${task.name} succeeded');
        await _updateLastRun(task.id);
      } else {
        debugPrint('[Scheduler] ✗ ${task.name} failed: ${result.message}');

        // Retry if available
        if (attempt < task.retries) {
          await Future.delayed(Duration(seconds: 10 * attempt));
          await _executeTask(task, attempt: attempt + 1);
        }
      }
    } catch (e) {
      debugPrint('[Scheduler] Error executing ${task.name}: $e');
      if (attempt < task.retries) {
        await Future.delayed(Duration(seconds: 10 * attempt));
        await _executeTask(task, attempt: attempt + 1);
      }
    }
  }

  // ── Database operations ────────────────────────────────────

  Future<void> _loadTasks() async {
    try {
      final db = await LocalDB.db;
      final rows = await db.query('scheduled_tasks');
      _tasks.clear();
      for (final row in rows) {
        _tasks.add(_fromRow(row));
      }
      debugPrint('[Scheduler] Loaded ${_tasks.length} tasks');
    } catch (e) {
      debugPrint('[Scheduler] Failed to load tasks: $e');
    }
  }

  Future<void> _saveTask(ScheduledTask task) async {
    try {
      final db = await LocalDB.db;
      await db.insert('scheduled_tasks', task.toMap(),
          conflictAlgorithm: ConflictAlgorithm.replace);
    } catch (e) {
      debugPrint('[Scheduler] Failed to save task: $e');
    }
  }

  ScheduledTask _fromRow(Map<String, Object?> row) {
    final taskType = TaskType.values.firstWhere(
      (value) => value.name == row['task_type'],
      orElse: () => TaskType.custom,
    );
    final scheduleType = ScheduleType.values.firstWhere(
      (value) => value.name == row['schedule_type'],
      orElse: () => ScheduleType.once,
    );
    final rawWeekDays = (row['week_days'] as String?)?.trim();
    final weekDays = rawWeekDays == null || rawWeekDays.isEmpty
        ? null
        : rawWeekDays
            .split(',')
            .map((value) => int.tryParse(value))
            .whereType<int>()
            .toList();

    return ScheduledTask(
      id: row['id'] as String,
      name: (row['name'] as String?) ?? 'Scheduled Task',
      task: AutomationTask(
        type: taskType,
        command: (row['task_command'] as String?) ?? '',
        description: (row['name'] as String?) ?? 'Scheduled Task',
      ),
      type: scheduleType,
      scheduledTime: _parseDateTime(row['scheduled_time']),
      intervalMinutes: row['interval_minutes'] as int?,
      weekDays: weekDays,
      eventTrigger: row['event_trigger'] as String?,
      enabled: (row['enabled'] as int? ?? 1) == 1,
      retries: row['retries'] as int? ?? 3,
      createdAt:
          _parseDateTime(row['created_at']) ?? DateTime.now(),
      lastRun: _parseDateTime(row['last_run']),
    );
  }

  DateTime? _parseDateTime(Object? value) {
    if (value == null) return null;
    return DateTime.tryParse(value.toString());
  }

  Future<void> _deleteTask(String taskId) async {
    try {
      final db = await LocalDB.db;
      await db.delete('scheduled_tasks', where: 'id = ?', whereArgs: [taskId]);
    } catch (e) {
      debugPrint('[Scheduler] Failed to delete task: $e');
    }
  }

  Future<void> _updateLastRun(String taskId) async {
    try {
      final db = await LocalDB.db;
      await db.update(
        'scheduled_tasks',
        {'last_run': DateTime.now().toIso8601String()},
        where: 'id = ?',
        whereArgs: [taskId],
      );

      // Update in-memory task
      final idx = _tasks.indexWhere((t) => t.id == taskId);
      if (idx >= 0) {
        final old = _tasks[idx];
        _tasks[idx] = ScheduledTask(
          id: old.id,
          name: old.name,
          task: old.task,
          type: old.type,
          scheduledTime: old.scheduledTime,
          intervalMinutes: old.intervalMinutes,
          weekDays: old.weekDays,
          eventTrigger: old.eventTrigger,
          enabled: old.enabled,
          retries: old.retries,
          createdAt: old.createdAt,
          lastRun: DateTime.now(),
        );
      }
    } catch (e) {
      debugPrint('[Scheduler] Failed to update lastRun: $e');
    }
  }

  // ── Create common task templates ───────────────────────────

  /// Morning alarm + open WhatsApp
  static ScheduledTask morningRoutine() {
    return ScheduledTask(
      id: const Uuid().v4(),
      name: 'Morning Routine',
      task: AutomationTask(
        type: TaskType.setAlarm,
        command: 'set alarm 8am',
        description: 'Morning alarm',
      ),
      type: ScheduleType.daily,
      enabled: true,
      createdAt: DateTime.now(),
    );
  }

  /// Check notifications every 5 minutes
  static ScheduledTask notificationCheck() {
    return ScheduledTask(
      id: const Uuid().v4(),
      name: 'Check Notifications',
      task: AutomationTask(
        type: TaskType.screenshot,
        command: 'take screenshot',
        description: 'Check screen state',
      ),
      type: ScheduleType.interval,
      intervalMinutes: 5,
      enabled: true,
      createdAt: DateTime.now(),
    );
  }

  /// Send status to Pavan every hour
  static ScheduledTask hourlyStatusReport() {
    return ScheduledTask(
      id: const Uuid().v4(),
      name: 'Hourly Status Report',
      task: AutomationTask(
        type: TaskType.custom,
        command: 'report status to pavan',
        description: 'Send device status',
      ),
      type: ScheduleType.interval,
      intervalMinutes: 60,
      enabled: true,
      createdAt: DateTime.now(),
    );
  }
}

// ── Task execution listener for on-demand tasks ─────────────
// Triggered by events (new message, phone call, etc.)

class EventTaskListener {
  static const _channel = MethodChannel('com.example.jarvis_app/task_events');

  static Future<void> setup() async {
    try {
      _channel.setMethodCallHandler((call) async {
        switch (call.method) {
          case 'onMessageReceived':
            await _onMessageReceived(call.arguments);
            break;
          case 'onCallIncoming':
            await _onCallIncoming(call.arguments);
            break;
          case 'onScreenOn':
            await _onScreenOn();
            break;
          case 'onScreenOff':
            await _onScreenOff();
            break;
        }
      });
      debugPrint('[EventListener] Setup complete ✓');
    } catch (e) {
      debugPrint('[EventListener] Setup failed: $e');
    }
  }

  static Future<void> _onMessageReceived(dynamic args) async {
    final scheduler = TaskScheduler();
    final tasks = scheduler.getEnabledTasks()
        .where((t) => t.eventTrigger == 'message_received')
        .toList();

    for (final task in tasks) {
      await scheduler._executeTask(task);
    }
  }

  static Future<void> _onCallIncoming(dynamic args) async {
    final scheduler = TaskScheduler();
    final tasks = scheduler.getEnabledTasks()
        .where((t) => t.eventTrigger == 'call_incoming')
        .toList();

    for (final task in tasks) {
      await scheduler._executeTask(task);
    }
  }

  static Future<void> _onScreenOn() async {
    debugPrint('[EventListener] Screen turned ON');
  }

  static Future<void> _onScreenOff() async {
    debugPrint('[EventListener] Screen turned OFF — background mode active');
  }
}

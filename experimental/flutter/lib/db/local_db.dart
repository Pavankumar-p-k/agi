// lib/db/local_db.dart
// JARVIS OFFLINE — Complete Local SQLite Database
// Stores: reminders, alarms, notes, chat history, contacts,
//         call logs, sync queue. No server needed ever.

import 'package:sqflite/sqflite.dart';
import 'package:path/path.dart';
import '../models/offline_models.dart';

class LocalDB {
  static Database? _db;
  static const _version = 5;

  static Future<Database> get db async {
    _db ??= await _init();
    return _db!;
  }

  static Future<Database> _init() async {
    final dir  = await getDatabasesPath();
    final path = join(dir, 'jarvis_offline.db');
    return openDatabase(
      path,
      version: _version,
      onCreate: _create,
      onUpgrade: _upgrade,
    );
  }

  static Future<void> _create(Database db, int version) async {
    await db.execute('''
      CREATE TABLE reminders (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        title       TEXT    NOT NULL,
        description TEXT    DEFAULT '',
        remind_at   TEXT    NOT NULL,
        repeat      TEXT    DEFAULT 'none',
        is_done     INTEGER DEFAULT 0,
        is_alarm    INTEGER DEFAULT 0,
        alarm_sound TEXT    DEFAULT 'default',
        synced      INTEGER DEFAULT 0,
        created_at  TEXT    DEFAULT (datetime('now'))
      )
    ''');

    await db.execute('''
      CREATE TABLE notes (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        title      TEXT NOT NULL,
        content    TEXT DEFAULT '',
        tags       TEXT DEFAULT '',
        pinned     INTEGER DEFAULT 0,
        synced     INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
      )
    ''');

    await db.execute('''
      CREATE TABLE chat_history (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        role       TEXT NOT NULL,
        message    TEXT NOT NULL,
        timestamp  TEXT DEFAULT (datetime('now'))
      )
    ''');

    await db.execute('''
      CREATE TABLE call_logs (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        caller       TEXT NOT NULL,
        platform     TEXT DEFAULT 'SIM',
        duration_s   INTEGER DEFAULT 0,
        transcript   TEXT DEFAULT '',
        important    INTEGER DEFAULT 0,
        jarvis_reply TEXT DEFAULT '',
        synced       INTEGER DEFAULT 0,
        timestamp    TEXT DEFAULT (datetime('now'))
      )
    ''');

    await db.execute('''
      CREATE TABLE contacts (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT NOT NULL,
        phone       TEXT,
        relation    TEXT DEFAULT 'friend',
        is_special  INTEGER DEFAULT 0,
        notes       TEXT DEFAULT '',
        last_seen   TEXT
      )
    ''');

    await db.execute('''
      CREATE TABLE sync_queue (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        table_name TEXT NOT NULL,
        record_id  INTEGER NOT NULL,
        action     TEXT NOT NULL,
        payload    TEXT NOT NULL,
        synced     INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now'))
      )
    ''');

    await db.execute('''
      CREATE TABLE scheduled_tasks (
        id               TEXT PRIMARY KEY,
        name             TEXT NOT NULL,
        task_type        TEXT NOT NULL,
        task_command     TEXT NOT NULL,
        schedule_type    TEXT NOT NULL,
        scheduled_time   TEXT,
        interval_minutes INTEGER,
        week_days        TEXT,
        event_trigger    TEXT,
        enabled          INTEGER DEFAULT 1,
        retries          INTEGER DEFAULT 3,
        created_at       TEXT NOT NULL,
        last_run         TEXT
      )
    ''');

    await db.execute('''
      CREATE TABLE inbox_messages (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        sender          TEXT    NOT NULL,
        platform        TEXT    DEFAULT 'unknown',
        cache_key       TEXT    DEFAULT '',
        text            TEXT    NOT NULL,
        language        TEXT    DEFAULT 'english',
        intent          TEXT    DEFAULT 'casual',
        sentiment       TEXT    DEFAULT 'neutral',
        urgency         TEXT    DEFAULT 'low',
        friend_type     TEXT    DEFAULT 'unknown',
        sentiment_score REAL    DEFAULT 0.0,
        suggested_reply TEXT    DEFAULT '',
        reply_sent      INTEGER DEFAULT 0,
        synced          INTEGER DEFAULT 0,
        timestamp       TEXT    DEFAULT (datetime('now'))
      )
    ''');

    await db.execute('''
      CREATE TABLE ai_identity (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
      )
    ''');

    // Default identity config
    await db.insert('ai_identity', {'key': 'owner_name', 'value': 'Pavan'});
    await db.insert('ai_identity', {'key': 'ai_name', 'value': 'JARVIS'});
    await db.insert('ai_identity', {'key': 'reveal_response_en',
      'value': "I'm JARVIS, Pavan's personal AI assistant. Pavan is currently unavailable — I'll let him know you called."});
    await db.insert('ai_identity', {'key': 'reveal_response_te',
      'value': "Nenu JARVIS, Pavan gari personal AI assistant ni. Pavan ippudu available kaadu — meeru chesina call gurinchi cheppistanu."});

    // Learning tables for self-improvement
    await db.execute('''
      CREATE TABLE learning_feedback (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        feedback_id       TEXT NOT NULL UNIQUE,
        user_input        TEXT NOT NULL,
        ai_reply          TEXT NOT NULL,
        user_correction   TEXT,
        feedback_type     TEXT NOT NULL,
        rating            INTEGER DEFAULT 3,
        intent            TEXT DEFAULT 'general',
        friend_type       TEXT,
        response_time     INTEGER DEFAULT 0,
        timestamp         TEXT DEFAULT (datetime('now'))
      )
    ''');

    await db.execute('''
      CREATE TABLE learning_patterns (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        pattern_name      TEXT NOT NULL UNIQUE,
        effectiveness_score REAL DEFAULT 0.5,
        times_used        INTEGER DEFAULT 0,
        positive_count    INTEGER DEFAULT 0,
        total_feedback    INTEGER DEFAULT 0,
        last_used         TEXT DEFAULT (datetime('now')),
        created_at        TEXT DEFAULT (datetime('now'))
      )
    ''');
  }

  static Future<void> _upgrade(Database db, int oldVersion, int newVersion) async {
    if (oldVersion < 2) {
      await db.execute('''
        CREATE TABLE IF NOT EXISTS inbox_messages (
          id              INTEGER PRIMARY KEY AUTOINCREMENT,
          sender          TEXT    NOT NULL,
          platform        TEXT    DEFAULT 'unknown',
          text            TEXT    NOT NULL,
          language        TEXT    DEFAULT 'english',
          intent          TEXT    DEFAULT 'casual',
          sentiment       TEXT    DEFAULT 'neutral',
          urgency         TEXT    DEFAULT 'low',
          friend_type     TEXT    DEFAULT 'unknown',
          sentiment_score REAL    DEFAULT 0.0,
          suggested_reply TEXT    DEFAULT '',
          reply_sent      INTEGER DEFAULT 0,
          synced          INTEGER DEFAULT 0,
          timestamp       TEXT    DEFAULT (datetime('now'))
        )
      ''');
    }
    if (oldVersion < 3) {
      // Add learning tables for self-improvement
      await db.execute('''
        CREATE TABLE IF NOT EXISTS learning_feedback (
          id                INTEGER PRIMARY KEY AUTOINCREMENT,
          feedback_id       TEXT NOT NULL UNIQUE,
          user_input        TEXT NOT NULL,
          ai_reply          TEXT NOT NULL,
          user_correction   TEXT,
          feedback_type     TEXT NOT NULL,
          rating            INTEGER DEFAULT 3,
          intent            TEXT DEFAULT 'general',
          friend_type       TEXT,
          response_time     INTEGER DEFAULT 0,
          timestamp         TEXT DEFAULT (datetime('now'))
        )
      ''');

      await db.execute('''
        CREATE TABLE IF NOT EXISTS learning_patterns (
          id                INTEGER PRIMARY KEY AUTOINCREMENT,
          pattern_name      TEXT NOT NULL UNIQUE,
          effectiveness_score REAL DEFAULT 0.5,
          times_used        INTEGER DEFAULT 0,
          positive_count    INTEGER DEFAULT 0,
          total_feedback    INTEGER DEFAULT 0,
          last_used         TEXT DEFAULT (datetime('now')),
          created_at        TEXT DEFAULT (datetime('now'))
        )
      ''');
    }
    if (oldVersion < 4) {
      // Cache key for reliable auto-reply (notification remote input mapping)
      await db.execute('ALTER TABLE inbox_messages ADD COLUMN cache_key TEXT DEFAULT ""');
    }
    if (oldVersion < 5) {
      // Suggested reply text stored when a response is generated.
      await db.execute('ALTER TABLE inbox_messages ADD COLUMN suggested_reply TEXT');
      await db.execute('''
        CREATE TABLE IF NOT EXISTS scheduled_tasks (
          id               TEXT PRIMARY KEY,
          name             TEXT NOT NULL,
          task_type        TEXT NOT NULL,
          task_command     TEXT NOT NULL,
          schedule_type    TEXT NOT NULL,
          scheduled_time   TEXT,
          interval_minutes INTEGER,
          week_days        TEXT,
          event_trigger    TEXT,
          enabled          INTEGER DEFAULT 1,
          retries          INTEGER DEFAULT 3,
          created_at       TEXT NOT NULL,
          last_run         TEXT
        )
      ''');
    }
  }

  // ── REMINDERS ────────────────────────────────────────────

  Future<int> insertReminder(ReminderModel r) async {
    final d = await db;
    final id = await d.insert('reminders', r.toMap());
    await _queueSync('reminders', id, 'insert', r.toMap());
    return id;
  }

  Future<List<ReminderModel>> getReminders({bool onlyPending = false}) async {
    final d = await db;
    final rows = onlyPending
        ? await d.query('reminders', where: 'is_done=0', orderBy: 'remind_at ASC')
        : await d.query('reminders', orderBy: 'remind_at ASC');
    return rows.map(ReminderModel.fromMap).toList();
  }

  Future<List<ReminderModel>> getDueReminders() async {
    final d    = await db;
    final now  = DateTime.now().toIso8601String();
    final rows = await d.query('reminders',
        where: 'is_done=0 AND remind_at <= ?', whereArgs: [now]);
    return rows.map(ReminderModel.fromMap).toList();
  }

  Future<void> markReminderDone(int id) async {
    final d = await db;
    await d.update('reminders', {'is_done': 1, 'synced': 0},
        where: 'id=?', whereArgs: [id]);
  }

  Future<void> deleteReminder(int id) async {
    final d = await db;
    await d.delete('reminders', where: 'id=?', whereArgs: [id]);
  }

  // ── NOTES ─────────────────────────────────────────────────

  Future<int> insertNote(NoteModel n) async {
    final d  = await db;
    final id = await d.insert('notes', n.toMap());
    await _queueSync('notes', id, 'insert', n.toMap());
    return id;
  }

  Future<List<NoteModel>> getNotes() async {
    final d    = await db;
    final rows = await d.query('notes',
        orderBy: 'pinned DESC, updated_at DESC');
    return rows.map(NoteModel.fromMap).toList();
  }

  Future<void> updateNote(NoteModel n) async {
    final d = await db;
    final map = n.toMap();
    map['updated_at'] = DateTime.now().toIso8601String();
    await d.update('notes', map, where: 'id=?', whereArgs: [n.id]);
    await _queueSync('notes', n.id!, 'update', map);
  }

  Future<void> deleteNote(int id) async {
    final d = await db;
    await d.delete('notes', where: 'id=?', whereArgs: [id]);
  }

  // â”€â”€ INBOX MESSAGES â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

  Future<List<Map<String, dynamic>>> getInboxMessages({
    String? platform,
    int limit = 50,
  }) async {
    final d = await db;
    if (platform != null && platform != 'all') {
      return d.query('inbox_messages',
          where: 'platform=?', whereArgs: [platform],
          orderBy: 'timestamp DESC', limit: limit);
    }
    return d.query('inbox_messages',
        orderBy: 'timestamp DESC', limit: limit);
  }

  static Future<List<Map<String, dynamic>>> getRecentMessages({
    required String sender,
    required String platform,
    int limit = 6,
  }) async {
    final d = await db;
    final rows = await d.rawQuery('''
      SELECT sender, platform, cache_key, text, reply_sent, timestamp
      FROM inbox_messages
      WHERE sender = ? AND platform = ?
      ORDER BY timestamp DESC
      LIMIT ?
    ''', [sender, platform, limit]);
    return rows.reversed.toList();
  }

  static Future<bool> isReplySent({
    required String sender,
    required String platform,
    required String cacheKey,
  }) async {
    final d = await db;
    final rows = await d.query(
      'inbox_messages',
      columns: ['id'],
      where: 'sender=? AND platform=? AND cache_key=? AND reply_sent=1',
      whereArgs: [sender, platform, cacheKey],
      limit: 1,
    );
    return rows.isNotEmpty;
  }

  static Future<void> markReplySent({
    required String sender,
    required String platform,
    required String cacheKey,
    required String text,
    required DateTime timestamp,
    required String suggestedReply,
  }) async {
    final d = await db;
    final rows = await d.query(
      'inbox_messages',
      columns: ['id'],
      where: 'sender=? AND platform=? AND cache_key=?',
      whereArgs: [sender, platform, cacheKey],
      limit: 1,
    );

    final values = {
      'sender': sender,
      'platform': platform,
      'cache_key': cacheKey,
      'text': text,
      'timestamp': timestamp.toIso8601String(),
      'reply_sent': 1,
      'suggested_reply': suggestedReply,
    };

    if (rows.isNotEmpty) {
      await d.update('inbox_messages', values,
          where: 'id=?', whereArgs: [rows.first['id']]);
    } else {
      await d.insert('inbox_messages', values);
    }
  }

  Future<int> getUnreadCount(String? platform) async {
    final d    = await db;
    final where = platform != null && platform != 'all'
        ? 'reply_sent=0 AND platform=?'
        : 'reply_sent=0';
    final args  = platform != null && platform != 'all'
        ? [platform] : null;
    final rows = await d.rawQuery(
        'SELECT COUNT(*) as c FROM inbox_messages WHERE $where',
        args);
    return (rows.first['c'] as int?) ?? 0;
  }

  // ── CHAT HISTORY ──────────────────────────────────────────

  Future<void> saveMessage(String role, String message) async {
    final d = await db;
    await d.insert('chat_history', {
      'role': role,
      'message': message,
      'timestamp': DateTime.now().toIso8601String(),
    });
  }

  Future<List<Map<String, dynamic>>> getHistory({int limit = 30}) async {
    final d = await db;
    return d.query('chat_history',
        orderBy: 'timestamp DESC', limit: limit);
  }

  // ── CALL LOGS ─────────────────────────────────────────────

  Future<int> insertCallLog(Map<String, dynamic> log) async {
    final d  = await db;
    final id = await d.insert('call_logs', log);
    await _queueSync('call_logs', id, 'insert', log);
    return id;
  }

  Future<List<Map<String, dynamic>>> getCallLogs({int limit = 50}) async {
    final d = await db;
    return d.query('call_logs', orderBy: 'timestamp DESC', limit: limit);
  }

  // ── AI IDENTITY ───────────────────────────────────────────

  Future<String> getIdentity(String key) async {
    final d    = await db;
    final rows = await d.query('ai_identity',
        where: 'key=?', whereArgs: [key]);
    return rows.isNotEmpty ? rows.first['value'] as String : '';
  }

  Future<void> setIdentity(String key, String value) async {
    final d = await db;
    await d.insert('ai_identity', {'key': key, 'value': value},
        conflictAlgorithm: ConflictAlgorithm.replace);
  }

  // ── SYNC QUEUE ────────────────────────────────────────────

  Future<void> _queueSync(String table, int id, String action,
      Map<String, dynamic> payload) async {
    final d = await db;
    await d.insert('sync_queue', {
      'table_name': table,
      'record_id':  id,
      'action':     action,
      'payload':    payload.toString(),
      'synced':     0,
    });
  }

  Future<List<Map<String, dynamic>>> getUnsyncedItems() async {
    final d = await db;
    return d.query('sync_queue', where: 'synced=0');
  }

  Future<void> markSynced(int queueId) async {
    final d = await db;
    await d.update('sync_queue', {'synced': 1},
        where: 'id=?', whereArgs: [queueId]);
  }
}

// Global singleton
final localDB = LocalDB();

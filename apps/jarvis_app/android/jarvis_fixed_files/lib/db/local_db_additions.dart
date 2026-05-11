// lib/db/local_db_additions.dart
// ADD these methods to your existing LocalDb class in local_db.dart
// Do NOT replace the whole file — just paste these methods inside the class

/*
  ─────────────────────────────────────────────────────────────
  PASTE INSIDE class LocalDb { ... }
  ─────────────────────────────────────────────────────────────
*/

  /// Returns the last [limit] messages for a sender+platform,
  /// ordered oldest-first so they read as a real conversation.
  static Future<List<Map<String, dynamic>>> getRecentMessages({
    required String sender,
    required String platform,
    int limit = 6,
  }) async {
    final db   = await _database;
    final rows = await db.rawQuery('''
      SELECT text, reply_sent, timestamp
      FROM inbox_messages
      WHERE sender = ? AND platform = ?
      ORDER BY timestamp DESC
      LIMIT ?
    ''', [sender, platform, limit]);
    // Reverse so oldest is first (natural conversation order)
    return rows.reversed.toList();
  }

  /// Returns true if a reply has already been sent for this
  /// sender + platform + cacheKey combination.
  static Future<bool> isReplySent({
    required String sender,
    required String platform,
    required String cacheKey,
  }) async {
    final db   = await _database;
    final rows = await db.rawQuery('''
      SELECT 1 FROM inbox_messages
      WHERE sender = ? AND platform = ? AND cache_key = ?
        AND reply_sent = 1
      LIMIT 1
    ''', [sender, platform, cacheKey]);
    return rows.isNotEmpty;
  }

  /// Marks a message as replied and stores the suggested reply text.
  /// Always call this BEFORE sending — not after.
  static Future<void> markReplySent({
    required String sender,
    required String platform,
    required String cacheKey,
    required String text,
    required DateTime timestamp,
    required String suggestedReply,
  }) async {
    final db = await _database;

    // Upsert — insert if new row, update reply_sent if exists
    await db.rawInsert('''
      INSERT INTO inbox_messages
        (sender, platform, cache_key, text, timestamp, reply_sent, suggested_reply)
      VALUES (?, ?, ?, ?, ?, 1, ?)
      ON CONFLICT(sender, platform, cache_key)
      DO UPDATE SET reply_sent = 1, suggested_reply = excluded.suggested_reply
    ''', [
      sender,
      platform,
      cacheKey,
      text,
      timestamp.toIso8601String(),
      suggestedReply,
    ]);
  }

/*
  ─────────────────────────────────────────────────────────────
  ALSO MAKE SURE your inbox_messages table has these columns.
  Add a migration in your _onCreate / _onUpgrade if missing:
  ─────────────────────────────────────────────────────────────

  CREATE TABLE IF NOT EXISTS inbox_messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sender          TEXT    NOT NULL,
    platform        TEXT    NOT NULL DEFAULT 'unknown',
    cache_key       TEXT    NOT NULL,
    text            TEXT    NOT NULL DEFAULT '',
    timestamp       TEXT    NOT NULL,
    reply_sent      INTEGER NOT NULL DEFAULT 0,
    suggested_reply TEXT,
    UNIQUE(sender, platform, cache_key)
  );

  If the table already exists and is missing suggested_reply:
    ALTER TABLE inbox_messages ADD COLUMN suggested_reply TEXT;

  If missing cache_key:
    ALTER TABLE inbox_messages ADD COLUMN cache_key TEXT NOT NULL DEFAULT '';
  ─────────────────────────────────────────────────────────────
*/

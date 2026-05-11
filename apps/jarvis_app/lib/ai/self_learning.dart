// lib/ai/self_learning.dart
// ═══════════════════════════════════════════════════════════════════
//  JARVIS SELF-LEARNING SYSTEM
//  Tracks which replies work, learns conversational patterns,
//  improves over time based on user feedback + conversation outcomes.
//  100% local — learns on device without server.
// ═══════════════════════════════════════════════════════════════════

import 'package:sqflite/sqflite.dart';
import '../db/local_db.dart';

enum FeedbackType {
  positive,    // User liked the reply
  negative,    // User rejected it
  corrected,   // User corrected the reply (provided better one)
  ignored,     // User didn't respond
  neutral,     // No clear feedback
}

class ConversationFeedback {
  final String id;
  final String userInput;
  final String aiReply;
  final String? userCorrection;  // What user said instead
  final FeedbackType type;
  final int rating;              // 1-5 stars
  final String intent;           // greeting, thank_you, etc.
  final String? friendType;      // close, normal, unknown
  final DateTime timestamp;
  final int responseTime;        // ms to generate reply

  ConversationFeedback({
    required this.id,
    required this.userInput,
    required this.aiReply,
    this.userCorrection,
    required this.type,
    required this.rating,
    required this.intent,
    this.friendType,
    required this.timestamp,
    required this.responseTime,
  });

  Map<String, dynamic> toMap() => {
    'id': id,
    'user_input': userInput,
    'ai_reply': aiReply,
    'user_correction': userCorrection,
    'feedback_type': type.name,
    'rating': rating,
    'intent': intent,
    'friend_type': friendType,
    'timestamp': timestamp.toIso8601String(),
    'response_time': responseTime,
  };
}

class ConversationPattern {
  final String pattern;      // "greeting:english:close_friend"
  final double score;        // 0.0 - 1.0
  final int timesUsed;
  final int positiveCount;
  final int totalFeedback;
  final DateTime lastUsed;

  ConversationPattern({
    required this.pattern,
    required this.score,
    required this.timesUsed,
    required this.positiveCount,
    required this.totalFeedback,
    required this.lastUsed,
  });

  double get successRate => totalFeedback == 0 ? 0 : positiveCount / totalFeedback;
}

class SelfLearningSystem {
  static const String _table = 'learning_feedback';

  // ── Record user feedback ───────────────────────────────────

  static Future<void> recordFeedback(ConversationFeedback feedback) async {
    try {
      final db = await LocalDB.db;
      await db.insert(_table, feedback.toMap(),
          conflictAlgorithm: ConflictAlgorithm.replace);

      // Update pattern scores
      await _updatePatternScore(
        feedback.intent,
        feedback.type,
        feedback.rating,
      );

      print('[Learning] Feedback recorded: ${feedback.intent} → ${feedback.type.name}');
    } catch (e) {
      print('[Learning] Error: $e');
    }
  }

  // ── Update pattern effectiveness ───────────────────────────

  static Future<void> _updatePatternScore(
    String intent,
    FeedbackType type,
    int rating,
  ) async {
    // Scoring logic
    double scoreAdd = 0;
    switch (type) {
      case FeedbackType.positive:
        scoreAdd = 0.3 + (rating / 5.0) * 0.2;  // Max +0.5
        break;
      case FeedbackType.negative:
        scoreAdd = -0.4;
        break;
      case FeedbackType.corrected:
        scoreAdd = -0.2;  // Not ideal, but better than negative
        break;
      case FeedbackType.ignored:
        scoreAdd = -0.1;  // Mild penalty
        break;
      case FeedbackType.neutral:
        scoreAdd = 0;
        break;
    }

    // Store or update in learning_patterns table
    try {
      final db = await LocalDB.db;
      final existing = await db.query(
        'learning_patterns',
        where: 'intent = ?',
        whereArgs: [intent],
      );

      if (existing.isEmpty) {
        await db.insert('learning_patterns', {
          'intent': intent,
          'score': scoreAdd.clamp(0.0, 1.0),
          'times_used': 1,
          'positive_count': type == FeedbackType.positive ? 1 : 0,
          'total_feedback': 1,
          'last_used': DateTime.now().toIso8601String(),
        });
      } else {
        final row = existing.first;
        final newScore = ((row['score'] as double) + scoreAdd).clamp(0.0, 1.0);
        final newUsed = (row['times_used'] as int) + 1;
        final newPositive = (row['positive_count'] as int) +
            (type == FeedbackType.positive ? 1 : 0);
        final newTotal = (row['total_feedback'] as int) + 1;

        await db.update(
          'learning_patterns',
          {
            'score': newScore,
            'times_used': newUsed,
            'positive_count': newPositive,
            'total_feedback': newTotal,
            'last_used': DateTime.now().toIso8601String(),
          },
          where: 'intent = ?',
          whereArgs: [intent],
        );
      }
    } catch (e) {
      print('[Learning] Pattern update failed: $e');
    }
  }

  // ── Get learned pattern score ──────────────────────────────

  static Future<double> getPatternScore(String intent) async {
    try {
      final db = await LocalDB.db;
      final rows = await db.query(
        'learning_patterns',
        where: 'intent = ?',
        whereArgs: [intent],
      );

      if (rows.isEmpty) return 0.5;  // Default neutral
      return (rows.first['score'] as double?) ?? 0.5;
    } catch (e) {
      return 0.5;
    }
  }

  // ── Get all learned patterns ───────────────────────────────

  static Future<List<ConversationPattern>> getLearnedPatterns() async {
    try {
      final db = await LocalDB.db;
      final rows = await db.query('learning_patterns');

      return rows.map((row) => ConversationPattern(
        pattern: row['intent'] as String,
        score: (row['score'] as double?) ?? 0.5,
        timesUsed: (row['times_used'] as int?) ?? 0,
        positiveCount: (row['positive_count'] as int?) ?? 0,
        totalFeedback: (row['total_feedback'] as int?) ?? 0,
        lastUsed: DateTime.tryParse(row['last_used'] as String? ?? '') ?? DateTime.now(),
      )).toList();
    } catch (e) {
      print('[Learning] Fetch patterns failed: $e');
      return [];
    }
  }

  // ── Get feedback history for optimization ──────────────────

  static Future<List<ConversationFeedback>> getFeedbackHistory({
    String? intent,
    int limit = 50,
  }) async {
    try {
      final db = await LocalDB.db;
      final query = intent == null
          ? 'SELECT * FROM $_table ORDER BY timestamp DESC LIMIT $limit'
          : 'SELECT * FROM $_table WHERE intent = ? ORDER BY timestamp DESC LIMIT $limit';

      final rows = intent == null
          ? await db.rawQuery(query)
          : await db.rawQuery(query, [intent]);

      return rows.map((row) => ConversationFeedback(
        id: row['id'] as String,
        userInput: row['user_input'] as String,
        aiReply: row['ai_reply'] as String,
        userCorrection: row['user_correction'] as String?,
        type: FeedbackType.values.byName(row['feedback_type'] as String),
        rating: (row['rating'] as int?) ?? 3,
        intent: row['intent'] as String,
        friendType: row['friend_type'] as String?,
        timestamp: DateTime.parse(row['timestamp'] as String),
        responseTime: (row['response_time'] as int?) ?? 0,
      )).toList();
    } catch (e) {
      print('[Learning] Fetch history failed: $e');
      return [];
    }
  }

  // ── Get success rate for intent ────────────────────────────

  static Future<double> getSuccessRate(String intent) async {
    try {
      final db = await LocalDB.db;
      final rows = await db.query(
        'learning_patterns',
        where: 'intent = ?',
        whereArgs: [intent],
      );

      if (rows.isEmpty) return 0.5;
      final row = rows.first;
      final positive = (row['positive_count'] as int?) ?? 0;
      final total = (row['total_feedback'] as int?) ?? 1;
      return total == 0 ? 0.5 : positive / total;
    } catch (e) {
      return 0.5;
    }
  }

  // ── Get most used intents (for trending) ────────────────────

  static Future<List<String>> getMostUsedIntents({int limit = 10}) async {
    try {
      final db = await LocalDB.db;
      final rows = await db.rawQuery(
        'SELECT intent FROM learning_patterns ORDER BY times_used DESC LIMIT $limit',
      );

      return rows.map((row) => row['intent'] as String).toList();
    } catch (e) {
      return [];
    }
  }

  // ── Get learning statistics ────────────────────────────────

  static Future<Map<String, dynamic>> getLearningStats() async {
    try {
      final db = await LocalDB.db;

      // Total feedback
      final feedback = await db.rawQuery(
        'SELECT COUNT(*) as total FROM $_table',
      );
      final totalFeedback = (feedback.first['total'] as int?) ?? 0;

      // Patterns learned
      final patterns = await db.rawQuery(
        'SELECT COUNT(*) as total FROM learning_patterns',
      );
      final totalPatterns = (patterns.first['total'] as int?) ?? 0;

      // Average success rate
      final rates = await db.rawQuery(
        'SELECT AVG(positive_count * 1.0 / total_feedback) as rate FROM learning_patterns WHERE total_feedback > 0',
      );
      final avgRate = ((rates.first['rate'] as double?) ?? 0.5) * 100;

      // Most positive feedback
      final positive = await db.rawQuery(
        'SELECT COUNT(*) as total FROM $_table WHERE feedback_type = ?',
        ['positive'],
      );
      final positiveCount = (positive.first['total'] as int?) ?? 0;

      return {
        'total_feedback': totalFeedback,
        'patterns_learned': totalPatterns,
        'average_success_rate': avgRate.toStringAsFixed(1),
        'positive_feedback': positiveCount,
        'learning_efficiency': (positiveCount / (totalFeedback.max(1)) * 100).toStringAsFixed(1),
      };
    } catch (e) {
      return {
        'error': '$e',
      };
    }
  }

  // ── Initialize learning database tables ─────────────────────

  static Future<void> initializeLearningTables(Database db) async {
    try {
      // Feedback history table
      await db.execute('''
        CREATE TABLE IF NOT EXISTS $_table (
          id TEXT PRIMARY KEY,
          user_input TEXT NOT NULL,
          ai_reply TEXT NOT NULL,
          user_correction TEXT,
          feedback_type TEXT NOT NULL,
          rating INTEGER NOT NULL,
          intent TEXT NOT NULL,
          friend_type TEXT,
          timestamp TEXT NOT NULL,
          response_time INTEGER NOT NULL
        )
      ''');

      // Pattern scores / effectiveness table
      await db.execute('''
        CREATE TABLE IF NOT EXISTS learning_patterns (
          intent TEXT PRIMARY KEY,
          score REAL NOT NULL,
          times_used INTEGER NOT NULL,
          positive_count INTEGER NOT NULL,
          total_feedback INTEGER NOT NULL,
          last_used TEXT NOT NULL
        )
      ''');

      print('[Learning] Database initialized ✓');
    } catch (e) {
      print('[Learning] Init failed: $e');
    }
  }

  // ── Adaptive reply selection (uses learned scores) ─────────

  /// Select best reply variant based on learning history
  static Future<String?> selectBestReply(
    String intent,
    List<String> replyOptions,
  ) async {
    // If we have learned preferences, use them
    final score = await getPatternScore(intent);

    if (score > 0.7) {
      // High-scoring pattern — use most recent successful reply
      final feedback = await getFeedbackHistory(intent: intent, limit: 5);
      if (feedback.isNotEmpty) {
        final positive = feedback.where((f) => f.type == FeedbackType.positive);
        if (positive.isNotEmpty) {
          return positive.first.aiReply;
        }
      }
    }

    // Otherwise, pick random from options
    return replyOptions.isEmpty ? null : replyOptions[DateTime.now().millisecond % replyOptions.length];
  }
}

extension IntMax on int {
  int max(int other) => this > other ? this : other;
}

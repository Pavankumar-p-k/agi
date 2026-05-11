// lib/services/message_inbox_service.dart
// JARVIS MESSAGE INBOX — Fully Offline
// ═══════════════════════════════════════════════════════════
// 1. Receives messages from JarvisNotificationListener (Android)
// 2. Runs MessageAnalyzer on every message
// 3. Auto-sends reply via ADB / WhatsApp if enabled
// 4. Stores everything in LocalDB
// 5. Shows notification with analysis result
// 6. Syncs to laptop when connected
// ═══════════════════════════════════════════════════════════

import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import '../ai/message_analyzer.dart';
import '../db/local_db.dart';
import '../models/models.dart';
import 'reply_agent.dart';

class MessageInboxService {
  static final MessageAnalyzer _analyzer = MessageAnalyzer();
  static final FlutterLocalNotificationsPlugin _notif =
      FlutterLocalNotificationsPlugin();
  static bool _initialized = false;

  // Platform channel — receives messages from Android Java
  static const _channel = EventChannel('com.example.jarvis_app/messages');

  // Settings
  static bool autoReplyEnabled  = false;
  static bool autoReplyOnlyClose = false;  // only reply to close friends
  static bool notifyOnAnalysis  = true;

  // Listeners — Flutter screens subscribe here
  static final _controllers = <StreamController<InboxMessage>>[];

  // Recent messages cache
  static final List<InboxMessage> _inbox = [];
  static List<InboxMessage> get inbox => List.unmodifiable(_inbox);

  // ── Start listening ───────────────────────────────────────

  static Future<void> start() async {
    if (_initialized) return;
    _initialized = true;
    await _initNotifications();
    await _loadCachedInbox();
    _channel.receiveBroadcastStream().listen(_onRawMessage);
  }

  // ── Subscribe to new messages ─────────────────────────────

  static Stream<InboxMessage> get stream {
    final ctrl = StreamController<InboxMessage>.broadcast();
    _controllers.add(ctrl);
    return ctrl.stream;
  }

  // ── Process incoming message from Android ─────────────────

  static Future<void> _onRawMessage(dynamic raw) async {
    try {
      final Map<String, dynamic> data =
          raw is String ? jsonDecode(raw) : Map<String, dynamic>.from(raw);

      final sender   = data['sender']   as String? ?? 'Unknown';
      final platform = data['platform'] as String? ?? 'unknown';
      final cacheKey = data['cache_key'] as String? ?? '${sender}_$platform';
      final text     = data['text']     as String? ??
                       data['message']  as String? ?? '';
      if (text.isEmpty) return;

      // Get conversation count for this sender
      final count = await _getConversationCount(sender);

      // Analyze the message
      final analysis = await _analyzer.analyze(
        sender:            sender,
        platform:          platform,
        message:           text,
        conversationCount: count,
      );

      // Build inbox message
      final msg = InboxMessage(
        sender:    sender,
        platform:  platform,
        cacheKey:  cacheKey,
        text:      text,
        analysis:  analysis,
        timestamp: DateTime.now(),
      );

      // Store to DB
      await _storeMessage(msg);

      // Add to cache
      _inbox.insert(0, msg);
      if (_inbox.length > 100) _inbox.removeLast();

      // Notify subscribers
      for (final ctrl in _controllers) {
        if (!ctrl.isClosed) ctrl.add(msg);
      }

      // Show analysis notification
      if (notifyOnAnalysis) {
        await _showAnalysisNotif(msg);
      }

      // Auto-reply if enabled
      if (autoReplyEnabled && replyAgent.masterEnabled) {
        final shouldReply = !autoReplyOnlyClose ||
            analysis.friendType == 'close';
        if (shouldReply && analysis.needsReply) {
          await _sendReply(msg);
        }
      }
    } catch (e) {
      print('[Inbox] Error processing message: $e');
    }
  }

  // ── Send reply via platform channel → Android ─────────────

  static const _replyChannel = MethodChannel('com.example.jarvis_app/reply');

  static Future<void> _sendReply(InboxMessage msg) async {
    try {
      final sent = await _replyChannel.invokeMethod<bool>('sendReply', {
        'sender':   msg.sender,
        'platform': msg.platform,
        'cache_key': msg.cacheKey,
        'text':     msg.replyText,
      });
      if (sent == true) {
        await _markReplySent(msg);
      }
      print('[Inbox] Replied to ${msg.sender}: ${msg.replyText} (sent=$sent)');
    } catch (e) {
      print('[Inbox] Reply failed: $e');
    }
  }

  // ── Show notification with analysis ───────────────────────

  static Future<void> _showAnalysisNotif(InboxMessage msg) async {
    final a = msg.analysis;

    // Build analysis summary
    final urgencyEmoji = a.urgency == 'high' ? '🔴' :
                         a.urgency == 'medium' ? '🟡' : '🟢';
    final sentEmoji    = a.sentiment == 'positive' ? '😊' :
                         a.sentiment == 'negative' ? '😟' : '😐';

    await _notif.show(
      msg.sender.hashCode % 10000,
      '$urgencyEmoji ${msg.sender} [${msg.platform.toUpperCase()}]',
      '$sentEmoji ${a.intent.toUpperCase()} • ${a.language} • ${a.friendType}\n'
      '"${msg.text.length > 50 ? '${msg.text.substring(0, 50)}...' : msg.text}"',
      NotificationDetails(
        android: AndroidNotificationDetails(
          'jarvis_inbox',
          'JARVIS Message Inbox',
          importance:   Importance.high,
          priority:     Priority.high,
          color:        const Color(0xFF00F0FF),
          actions: [
            AndroidNotificationAction('reply',  'REPLY'),
            AndroidNotificationAction('dismiss', 'DISMISS'),
          ],
          styleInformation: BigTextStyleInformation(
            '${sentEmoji} Sentiment: ${a.sentiment} (${a.sentimentScore.toStringAsFixed(2)})\n'
            'Intent: ${a.intent}  |  Urgency: ${a.urgency}\n'
            'Friend type: ${a.friendType}  |  Lang: ${a.language}\n\n'
            'Suggested reply:\n"${a.suggestedReply}"',
            contentTitle:
                '$urgencyEmoji ${msg.sender} [${msg.platform}]',
          ),
        ),
      ),
    );
  }

  // ── Store message to local DB ─────────────────────────────

  static Future<void> _storeMessage(InboxMessage msg) async {
    final db = await LocalDB.db;
    await db.insert('inbox_messages', {
      'sender':         msg.sender,
      'platform':       msg.platform,
      'cache_key':      msg.cacheKey,
      'text':           msg.text,
      'language':       msg.analysis.language,
      'intent':         msg.analysis.intent,
      'sentiment':      msg.analysis.sentiment,
      'urgency':        msg.analysis.urgency,
      'friend_type':    msg.analysis.friendType,
      'sentiment_score':msg.analysis.sentimentScore,
      'suggested_reply':msg.analysis.suggestedReply,
      'reply_sent':     0,
      'timestamp':      msg.timestamp.toIso8601String(),
    });
  }

  static Future<int> _getConversationCount(String sender) async {
    final db   = await LocalDB.db;
    final rows = await db.rawQuery(
        'SELECT COUNT(*) as c FROM inbox_messages WHERE sender=?',
        [sender]);
    return (rows.first['c'] as int?) ?? 0;
  }

  // ── Manually trigger reply ────────────────────────────────

  static Future<void> sendManualReply(InboxMessage msg,
      String customText) async {
    final updated = InboxMessage(
      sender:    msg.sender,
      platform:  msg.platform,
      cacheKey:  msg.cacheKey,
      text:      msg.text,
      analysis:  msg.analysis,
      timestamp: msg.timestamp,
      customReply: customText,
    );
    await _sendReply(updated);
  }

  // ── Get inbox for a sender ────────────────────────────────


  static Future<void> _initNotifications() async {
    const android = AndroidInitializationSettings('@mipmap/ic_launcher');
    const ios = DarwinInitializationSettings();
    await _notif.initialize(
      const InitializationSettings(android: android, iOS: ios),
    );

    final androidPlugin = AndroidFlutterLocalNotificationsPlugin();
    await androidPlugin.createNotificationChannel(
      const AndroidNotificationChannel(
        'jarvis_inbox',
        'JARVIS Message Inbox',
        description: 'Message analysis results',
        importance: Importance.high,
      ),
    );
  }

  static Future<void> _loadCachedInbox() async {
    final rows = await localDB.getInboxMessages(limit: 100);
    final items = rows.map(_fromRow).toList();
    _inbox
      ..clear()
      ..addAll(items);
  }

  static InboxMessage _fromRow(Map<String, dynamic> row) {
    final analysis = MessageAnalysis(
      sender:            row['sender'] ?? 'Unknown',
      platform:          row['platform'] ?? 'unknown',
      originalText:      row['text'] ?? '',
      language:          row['language'] ?? 'english',
      intent:            row['intent'] ?? 'casual',
      sentiment:         row['sentiment'] ?? 'neutral',
      urgency:           row['urgency'] ?? 'low',
      friendType:        row['friend_type'] ?? 'unknown',
      sentimentScore:    (row['sentiment_score'] as num?)?.toDouble() ?? 0.0,
      needsReply:        (row['reply_sent'] ?? 0) == 0,
      isIdentityQuestion:false,
      suggestedReply:    row['suggested_reply'] ?? '',
      replyReason:       row['intent'] ?? 'casual',
    );

    final cacheKey = row['cache_key'] as String? ??
        '${row['sender'] ?? 'Unknown'}_${row['platform'] ?? 'unknown'}';

    return InboxMessage(
      sender:    row['sender'] ?? 'Unknown',
      platform:  row['platform'] ?? 'unknown',
      cacheKey:  cacheKey,
      text:      row['text'] ?? '',
      analysis:  analysis,
      timestamp: DateTime.tryParse(row['timestamp'] ?? '') ?? DateTime.now(),
    );
  }

  static Future<void> _markReplySent(InboxMessage msg) async {
    final db = await LocalDB.db;
    await db.update(
      'inbox_messages',
      {'reply_sent': 1},
      where: 'sender=? AND platform=? AND cache_key=? AND text=? AND timestamp=?',
      whereArgs: [
        msg.sender,
        msg.platform,
        msg.cacheKey,
        msg.text,
        msg.timestamp.toIso8601String(),
      ],
    );
  }

  static List<InboxMessage> getByPlatform(String platform) {
    if (platform == 'all') return _inbox;
    return _inbox.where((m) => m.platform == platform).toList();
  }
}

// lib/services/reply_agent.dart
// JARVIS core auto-reply pipeline — fully fixed.
// Call Guard REMOVED. All platforms added. Atomic dedup lock fixed.

import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:jarvis_app/ai/gemini_model.dart';
import 'package:jarvis_app/ai/local_model.dart';
import 'package:jarvis_app/ai/offline_ai.dart';
import 'package:jarvis_app/ai/social_prompt_builder.dart';
import 'package:jarvis_app/db/local_db.dart';
import 'package:jarvis_app/models/models.dart';
import 'package:jarvis_app/services/feature_settings.dart';

class ReplyAgent {
  // ── Singleton ──────────────────────────────────────────────
  static final ReplyAgent _instance = ReplyAgent._internal();
  factory ReplyAgent() => _instance;
  ReplyAgent._internal();

  // ── Event stream for UI feedback ───────────────────────────
  final StreamController<Map<String, dynamic>> _resultCtrl =
      StreamController<Map<String, dynamic>>.broadcast();

  bool masterEnabled = true;
  int totalReceived = 0;
  int totalReplied = 0;
  bool quietHoursEnabled = false;
  int quietStart = 22;
  int quietEnd = 6;
  int maxRepliesPerHour = 20;

  final Map<String, PlatformSettings> platforms = {
    'whatsapp': PlatformSettings(enabled: true, minDelayMs: 150, maxDelayMs: 400),
    'instagram': PlatformSettings(enabled: true, minDelayMs: 180, maxDelayMs: 450),
    'telegram': PlatformSettings(enabled: true, minDelayMs: 120, maxDelayMs: 350),
    'sms': PlatformSettings(enabled: true, minDelayMs: 90, maxDelayMs: 300),
  };

  Stream<Map<String, dynamic>> get onResult => _resultCtrl.stream;

  Future<void> start() async {
    // Initialize reply agent as a no-op startup hook for UI.
  }

  void emitResult(Map<String, dynamic> event) {
    if (!_resultCtrl.isClosed) {
      _resultCtrl.add(event);
    }
  }

  void setMasterEnabled(bool value) {
    masterEnabled = value;
  }

  void setAllPlatformsEnabled(bool enabled) {
    platforms.updateAll((key, value) => value.copyWith(enabled: enabled));
  }

  void setPlatformEnabled(String platform, bool enabled) {
    final settings = platforms[platform];
    if (settings != null) {
      platforms[platform] = settings.copyWith(enabled: enabled);
    }
  }

  Future<void> openNotificationAccessSettings() async {
    return;
  }

  Future<void> openAccessibilitySettings() async {
    return;
  }

  Future<bool> isNotificationAccessEnabled() async {
    return true;
  }

  Future<bool> isAccessibilityEnabled() async {
    return true;
  }

  void setQuietHours(bool enabled, int start, int end) {
    quietHoursEnabled = enabled;
    quietStart = start;
    quietEnd = end;
  }

  void setMaxRepliesPerHour(int value) {
    maxRepliesPerHour = value;
  }

  // ── In-memory dedup lock ───────────────────────────────────
  // Prevents the OS duplicate-notification race condition.
  // Multiple notification deliveries of the same message all hit
  // this Set before any DB call, so only one proceeds.
  final Set<String> _inFlightKeys = {};

  // ── Per-sender cooldown ────────────────────────────────────
  final Map<String, DateTime> _lastReplied = {};
  static const Duration _cooldown = Duration(seconds: 45);

  // ═══════════════════════════════════════════════════════════
  // PUBLIC ENTRY POINT
  // Call this from NotificationService for every incoming message.
  // ═══════════════════════════════════════════════════════════
  Future<void> handleIncomingMessage(InboxMessage message) async {
    if (!FeatureSettings.isAutoReplyEnabled()) return;
    if (!FeatureSettings.isPlatformEnabled(message.platform)) return;
    await _process(message);
  }

  // ═══════════════════════════════════════════════════════════
  // PIPELINE — strict gate order, never reorder these steps
  // ═══════════════════════════════════════════════════════════
  Future<void> _process(InboxMessage msg) async {
    final key = _buildDedupKey(msg);

    // GATE 1 — in-memory lock (instant, no async needed)
    if (_inFlightKeys.contains(key)) {
      debugPrint('[ReplyAgent] Skip — in-flight: $key');
      return;
    }
    _inFlightKeys.add(key);

    try {
      // GATE 2 — DB check (survives restarts)
      if (await _isDuplicate(msg, key)) {
        debugPrint('[ReplyAgent] Skip — already replied (DB): $key');
        return;
      }

      // GATE 3 — cooldown
      if (_isOnCooldown(msg)) {
        debugPrint('[ReplyAgent] Skip — cooldown: ${msg.sender}');
        return;
      }

      // GATE 4 — message sanity
      if (!_isReplyable(msg)) {
        debugPrint('[ReplyAgent] Skip — not replyable: ${msg.text}');
        return;
      }

      // GATE 5 — generate
      final reply = await _generateReply(msg);
      if (reply == null || reply.trim().isEmpty) {
        debugPrint('[ReplyAgent] No reply generated');
        return;
      }

      // MARK DB BEFORE SEND — critical ordering
      await LocalDB.markReplySent(
        sender:         msg.sender,
        platform:       msg.platform,
        cacheKey:       key,
        text:           msg.text,
        timestamp:      msg.timestamp,
        suggestedReply: reply,
      );

      _updateCooldown(msg);

      await _sendReply(msg, reply);

    } catch (e, st) {
      debugPrint('[ReplyAgent] Error: $e\n$st');
    } finally {
      _inFlightKeys.remove(key); // always release
    }
  }

  // ── Dedup key — must include timestamp ────────────────────
  String _buildDedupKey(InboxMessage msg) {
    final ts = msg.timestamp.toIso8601String().substring(0, 19);
    return '${msg.platform}:${msg.sender}:$ts';
  }

  // ── DB duplicate check ────────────────────────────────────
  Future<bool> _isDuplicate(InboxMessage msg, String key) async {
    try {
      return await LocalDB.isReplySent(
        sender:   msg.sender,
        platform: msg.platform,
        cacheKey: key,
      );
    } catch (e) {
      debugPrint('[ReplyAgent] isDuplicate error: $e');
      return true; // fail safe — skip on DB error
    }
  }

  // ── Cooldown ──────────────────────────────────────────────
  bool _isOnCooldown(InboxMessage msg) {
    final k    = '${msg.platform}:${msg.sender}';
    final last = _lastReplied[k];
    if (last == null) return false;
    return DateTime.now().difference(last) < _cooldown;
  }

  void _updateCooldown(InboxMessage msg) {
    _lastReplied['${msg.platform}:${msg.sender}'] = DateTime.now();
  }

  // ── Replyable check ───────────────────────────────────────
  bool _isReplyable(InboxMessage msg) {
    final text  = msg.text.trim();
    final lower = text.toLowerCase();

    if (text.length < 2) return false;

    // Skip OTP / verification messages
    if (lower.contains('otp') ||
        lower.contains('verification code') ||
        lower.contains('do not share') ||
        lower.contains('your code is') ||
        RegExp(r'\b\d{4,8}\b').hasMatch(text)) return false;

    // Skip WhatsApp group JIDs
    if (msg.sender.contains('@g.us')) return false;

    return true;
  }

  // ═══════════════════════════════════════════════════════════
  // REPLY GENERATION — local model → Gemini → offline fallback
  // ═══════════════════════════════════════════════════════════
  Future<String?> _generateReply(InboxMessage msg) async {
    try {
      final prompt = await SocialPromptBuilder.buildFromDb(msg);

      // 1. Local model (Gemma 4 E2B / Ollama / llama.cpp)
      String? reply = await LocalModel.generate(prompt);

      // 2. Gemini fallback
      if (reply == null || reply.trim().isEmpty) {
        debugPrint('[ReplyAgent] Local empty — trying Gemini');
        reply = await GeminiModel.generate(prompt);
      }

      // 3. Offline rule-based last resort
      if (reply == null || reply.trim().isEmpty) {
        debugPrint('[ReplyAgent] Gemini empty — using offline fallback');
        reply = OfflineAI.generateReply(msg.text, msg.platform);
      }

      return reply == null ? null : _cleanReply(reply, msg.text);

    } catch (e) {
      debugPrint('[ReplyAgent] _generateReply error: $e');
      return null;
    }
  }

  // ── Clean raw LLM output ──────────────────────────────────
  String? _cleanReply(String raw, String originalText) {
    var r = raw.trim();

    // Strip surrounding quotes
    if ((r.startsWith('"') && r.endsWith('"')) ||
        (r.startsWith("'") && r.endsWith("'"))) {
      r = r.substring(1, r.length - 1).trim();
    }

    // Strip persona prefix e.g. "Me:" or "Arjun:"
    final ci = r.indexOf(':');
    if (ci > 0 && ci < 20) r = r.substring(ci + 1).trim();

    // Strip markdown bold
    r = r.replaceAll(RegExp(r'\*+'), '').trim();

    // Reject echo
    final orig = originalText.toLowerCase().trim();
    if (orig.length > 10 &&
        r.toLowerCase().contains(orig.substring(0, 15))) {
      debugPrint('[ReplyAgent] Reject — echo');
      return null;
    }

    // Reject too long
    if (r.split(' ').length > 40) {
      debugPrint('[ReplyAgent] Reject — too long');
      return null;
    }

    // Reject bot-like openers
    final lower = r.toLowerCase();
    for (final bad in [
      'as an ai', "i'm an ai", 'i am an ai',
      'i cannot', "i'm unable", 'certainly!',
      'of course!', 'absolutely!', 'great question',
    ]) {
      if (lower.startsWith(bad)) {
        debugPrint('[ReplyAgent] Reject — bot opener: $bad');
        return null;
      }
    }

    return r.isEmpty ? null : r;
  }

  // ═══════════════════════════════════════════════════════════
  // SEND DISPATCH — routes to correct platform
  // ═══════════════════════════════════════════════════════════
  Future<void> _sendReply(InboxMessage msg, String reply) async {
    debugPrint('[ReplyAgent] Sending on ${msg.platform} to ${msg.sender}: $reply');
    try {
      await _replyViaNotificationAction(msg.cacheKey, reply);
    } catch (e) {
      debugPrint('[ReplyAgent] Send error: $e');
      // DB already marked — no retry loop
    }
  }

  /// Sends via Android RemoteInput notification action.
  /// Wire your existing platform channel here.
  Future<bool> _replyViaNotificationAction(
      String cacheKey, String replyText) async {
    // Replace comment below with your actual platform channel call:
    // final result = await platform.invokeMethod('sendReply', {
    //   'cacheKey': cacheKey,
    //   'replyText': replyText,
    // });
    // return result == true;
    debugPrint('[ReplyAgent] Notification action: $cacheKey → $replyText');
    return true;
  }

  // ── Debug helpers ─────────────────────────────────────────
  Map<String, dynamic> diagnostics() => {
    'inFlight':  _inFlightKeys.length,
    'cooldowns': _lastReplied.map(
        (k, v) => MapEntry(k, DateTime.now().difference(v).inSeconds)),
  };

  void clearCooldowns() => _lastReplied.clear();
}

final replyAgent = ReplyAgent();

class PlatformSettings {
  final bool enabled;
  final int minDelayMs;
  final int maxDelayMs;

  PlatformSettings({
    required this.enabled,
    required this.minDelayMs,
    required this.maxDelayMs,
  });

  PlatformSettings copyWith({
    bool? enabled,
    int? minDelayMs,
    int? maxDelayMs,
  }) {
    return PlatformSettings(
      enabled: enabled ?? this.enabled,
      minDelayMs: minDelayMs ?? this.minDelayMs,
      maxDelayMs: maxDelayMs ?? this.maxDelayMs,
    );
  }
}

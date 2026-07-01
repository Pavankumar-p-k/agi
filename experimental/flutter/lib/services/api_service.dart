// lib/services/api_service.dart
// JARVIS — Offline-first API client with local fallback
import 'package:flutter/foundation.dart';
import 'package:dio/dio.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../config/api_config.dart';
import '../models/models.dart';
import '../models/offline_models.dart';
import '../db/local_db.dart';
import '../ai/offline_ai.dart';
import '../services/reminder_engine.dart';

class ApiService {
  late final Dio _dio;
  static bool _online = false;
  static DateTime _lastCheck = DateTime.fromMillisecondsSinceEpoch(0);
  late String _sessionId;

  // Shared OfflineAI instance — loads dataset once for whole app
  static final OfflineAI _localAI = OfflineAI();

  ApiService() {
    _dio = Dio(BaseOptions(
      baseUrl: ApiConfig.baseUrl,
      connectTimeout: const Duration(seconds: 5),
      receiveTimeout: const Duration(seconds: 20),
    ));

    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) async {
        try {
          final prefs = await SharedPreferences.getInstance();
          final saved = prefs.getString('api_url');
          if (saved != null && saved.trim().isNotEmpty) {
            options.baseUrl = saved.trim();
          }
          // Init session ID from prefs or generate new
          _sessionId = prefs.getString('session_id') ?? '';
          if (_sessionId.isEmpty) {
            final now = DateTime.now().millisecondsSinceEpoch;
            final rand = (DateTime.now().microsecondsSinceEpoch % 100000).toString();
            _sessionId = 'flutter_${now}_$rand';
            await prefs.setString('session_id', _sessionId);
          }
        } catch (e) { debugPrint('[ApiService] interceptor error: $e'); }
        handler.next(options);
      },
      onError: (err, handler) => handler.next(err),
    ));
  }

  String get sessionId => _sessionId;

  Future<void> setSessionId(String id) async {
    _sessionId = id;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('session_id', id);
  }

  // —— Connectivity ————————————————————————————————
  Future<bool> isOnline() async {
    if (DateTime.now().difference(_lastCheck).inSeconds < 8) return _online;
    try {
      final r = await _dio.get(ApiConfig.health);
      _online = r.statusCode == 200;
    } catch (e) { debugPrint('[ApiService] isOnline error: $e');
      _online = false;
    }
    _lastCheck = DateTime.now();
    return _online;
  }

  // —— CHAT — server first, local AI fallback —————————
  Future<Map<String, dynamic>> chat(String message) async {
    if (await isOnline()) {
      try {
        final r = await _dio.post(ApiConfig.chat, data: {'message': message, 'session_id': _sessionId});
        final reply = (r.data as Map)['response'] ?? (r.data as Map)['text'] ?? '';
        if (reply.toString().isNotEmpty) {
          await localDB.saveMessage('user', message);
          await localDB.saveMessage('assistant', reply.toString());
          return r.data as Map<String, dynamic>;
        }
      } catch (e) { debugPrint('[ApiService] chat error: $e'); }
    }
    // Local model fallback
    final resp = await _localAI.process(message,
        friendType: 'normal', language: 'mixed');
    await localDB.saveMessage('user', message);
    await localDB.saveMessage('assistant', resp.text);
    return {'response': resp.text, 'source': 'local_model'};
  }

  Future<List<ChatMessage>> getChatHistory() async {
    if (await isOnline()) {
      try {
        final r = await _dio.get(ApiConfig.chatHistory);
        return (r.data as List).map((j) => ChatMessage.fromJson(j)).toList();
      } catch (e) { debugPrint('[ApiService] getChatHistory error: $e'); }
    }
    final rows = await localDB.getHistory(limit: 40);
    return rows.reversed.map((h) => ChatMessage(
      role: h['role'] as String,
      message: h['message'] as String,
      timestamp: DateTime.tryParse(h['timestamp'] as String? ?? '') ?? DateTime.now(),
    )).toList();
  }

  // —— Reminders — local SQLite first, server sync ——————
  Future<List<Reminder>> getReminders() async {
    final local = await localDB.getReminders();
    if (await isOnline()) {
      _pullRemindersFromServer();
    }
    return local.map((r) => Reminder(
      id: r.id ?? 0,
      title: r.title,
      description: r.description,
      remindAt: r.remindAt,
      repeat: r.repeat,
      isDone: r.isDone,
    )).toList();
  }

  Future<Reminder> createReminder({
    required String title,
    required DateTime remindAt,
    String description = '',
    String repeat = 'none',
  }) async {
    final model = ReminderModel(
      title: title,
      description: description,
      remindAt: remindAt,
      repeat: repeat,
    );
    final id = await localDB.insertReminder(model);

    await ReminderEngine.scheduleReminder(ReminderModel(
      id: id,
      title: title,
      description: description,
      remindAt: remindAt,
      repeat: repeat,
    ));

    if (await isOnline()) {
      try {
        await _dio.post(ApiConfig.reminders, data: {
          'title': title,
          'remind_at': remindAt.toIso8601String(),
          'description': description,
          'repeat': repeat,
        });
      } catch (e) { debugPrint('[ApiService] createReminder error: $e'); }
    }
    return Reminder(id: id, title: title, description: description,
        remindAt: remindAt, repeat: repeat);
  }

  Future<void> deleteReminder(int id) async {
    await localDB.deleteReminder(id);
    await ReminderEngine.cancelReminder(id);
    if (await isOnline()) {
      try { await _dio.delete('${ApiConfig.reminders}/$id'); } catch (e) { debugPrint('[ApiService] deleteReminder error: $e'); }
    }
  }

  // —— Notes — local SQLite first ————————————————
  Future<List<Note>> getNotes() async {
    final local = await localDB.getNotes();
    return local.map((n) => Note(
      id: n.id ?? 0,
      title: n.title,
      content: n.content,
      tags: n.tags,
      updatedAt: DateTime.now(),
    )).toList();
  }

  Future<Note> createNote(String title, String content, {String tags = ''}) async {
    final model = NoteModel(title: title, content: content, tags: tags);
    final id = await localDB.insertNote(model);
    if (await isOnline()) {
      try {
        await _dio.post(ApiConfig.notes, data: {
          'title': title,
          'content': content,
          'tags': tags,
        });
      } catch (e) { debugPrint('[ApiService] createNote error: $e'); }
    }
    return Note(id: id, title: title, content: content,
        tags: tags, updatedAt: DateTime.now());
  }

  Future<void> updateNote(int id, {String? title, String? content}) async {
    final all = await localDB.getNotes();
    final note = all.firstWhere(
      (n) => n.id == id,
      orElse: () => NoteModel(title: '', content: ''),
    );
    if (note.id == null) return;
    note.title = title ?? note.title;
    note.content = content ?? note.content;
    await localDB.updateNote(note);

    if (await isOnline()) {
      try {
        await _dio.put('${ApiConfig.notes}/$id', data: {
          if (title != null) 'title': title,
            if (content != null) 'content': content,
          });
        } catch (e) { debugPrint('[ApiService] updateNote error: $e'); }
    }
  }

  Future<void> deleteNote(int id) async {
    await localDB.deleteNote(id);
    if (await isOnline()) {
      try { await _dio.delete('${ApiConfig.notes}/$id'); } catch (e) { debugPrint('[ApiService] deleteNote error: $e'); }
    }
  }

  // —— Server-only features ————————————————————————
  Future<List<Activity>> getTodayActivity() async {
    if (!await isOnline()) return [];
    try {
      final res = await _dio.get(ApiConfig.activity);
      return (res.data as List).map((j) => Activity.fromJson(j)).toList();
    } catch (e) { debugPrint('[ApiService] getTodayActivity error: $e'); return []; }
  }

  Future<DailySummary> getDailySummary() async {
    if (!await isOnline()) return DailySummary(
      date: DateTime.now().toIso8601String(),
      summary: 'Laptop offline',
      productivityScore: 0,
    );
    try {
      final res = await _dio.get(ApiConfig.summary);
      return DailySummary.fromJson(res.data);
    } catch (e) { debugPrint('[ApiService] getDailySummary error: $e');
      return DailySummary(
        date: DateTime.now().toIso8601String(),
        summary: 'Unavailable',
        productivityScore: 0,
      );
    }
  }

  // ── Memory ──────────────────────────────────────────────────────────

  Future<Map<String, dynamic>?> getMemoryStats() async {
    try {
      final r = await _dio.get(ApiConfig.memoryStats);
      return r.data as Map<String, dynamic>;
    } catch (e) { debugPrint('[ApiService] getMemoryStats error: $e');
      return null;
    }
  }

  // ── Activity Graph ───────────────────────────────────────────────────
  
  Future<List<Map<String, dynamic>>> getActivities() async {
    try {
      final r = await _dio.get(ApiConfig.activityGraph);
      final data = r.data as Map<String, dynamic>;
      return List<Map<String, dynamic>>.from(data['activities'] ?? []);
    } catch (e) { debugPrint('[ApiService] getActivities error: $e');
      return [];
    }
  }

  Future<Map<String, dynamic>> getActivityCounts() async {
    try {
      final r = await _dio.get(ApiConfig.activityCounts);
      return r.data as Map<String, dynamic>;
    } catch (e) { debugPrint('[ApiService] getActivityCounts error: $e');
      return {};
    }
  }

  Future<Map<String, dynamic>> getActivityDetail(String id) async {
    try {
      final r = await _dio.get('${ApiConfig.activityGraph}/$id');
      return r.data as Map<String, dynamic>;
    } catch (e) { debugPrint('[ApiService] getActivityDetail error: $e');
      return {};
    }
  }

  Future<Map<String, dynamic>> getActivityTree(String id) async {
    try {
      final r = await _dio.get('${ApiConfig.activityGraph}/$id/tree');
      return r.data as Map<String, dynamic>;
    } catch (e) { debugPrint('[ApiService] getActivityTree error: $e');
      return {};
    }
  }

  Future<Map<String, dynamic>> getActivitySummaryById(String id) async {
    try {
      final r = await _dio.get('${ApiConfig.activityGraph}/$id/summary');
      return r.data as Map<String, dynamic>;
    } catch (e) { debugPrint('[ApiService] getActivitySummaryById error: $e');
      return {};
    }
  }

  Future<Map<String, dynamic>> pauseActivity(String id) async {
    final r = await _dio.post('${ApiConfig.activityGraph}/$id/pause');
    return r.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> resumeActivity(String id) async {
    final r = await _dio.post('${ApiConfig.activityGraph}/$id/resume');
    return r.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> cancelActivity(String id) async {
    final r = await _dio.post(
      '${ApiConfig.activityGraph}/$id/cancel',
      data: {'activity_id': id, 'error': 'cancelled by user'},
    );
    return r.data as Map<String, dynamic>;
  }

  Future<bool> sendMessage(String platform, String recipient, String msg) async {
    if (!await isOnline()) return false;
    try {
      final r = await _dio.post(ApiConfig.messageSend,
          data: {'platform': platform, 'recipient': recipient, 'message': msg});
      return r.statusCode == 200;
    } catch (e) { debugPrint('[ApiService] sendMessage error: $e'); return false; }
  }

  Future<List<KnownFace>> getFaces() async {
    if (!await isOnline()) return [];
    try {
      final r = await _dio.get(ApiConfig.facesList);
      return (r.data as List).map((j) => KnownFace.fromJson(j)).toList();
    } catch (e) { debugPrint('[ApiService] getFaces error: $e'); return []; }
  }

  Future<Map<String, dynamic>> identifyFace(List<int> bytes) async {
    if (!await isOnline()) return {'status': 'offline'};
    try {
      final f = MultipartFile.fromBytes(bytes, filename: 'face.jpg');
      final r = await _dio.post(ApiConfig.facesIdentify,
          data: FormData.fromMap({'image': f}));
      return r.data as Map<String, dynamic>;
    } catch (e) { debugPrint('[ApiService] identifyFace error: $e'); return {'status': 'error'}; }
  }

  Future<Map<String, dynamic>> registerFace({
    required String name,
    required List<List<int>> imageBytesList,
    String relation = 'unknown',
    String info = '',
    String accessLevel = 'visitor',
  }) async {
    if (!await isOnline()) return {'status': 'offline'};
    try {
      final files = imageBytesList.asMap().entries.map((e) =>
        MapEntry('images', MultipartFile.fromBytes(e.value,
            filename: 'img_${e.key}.jpg'))).toList();
      final form = FormData.fromMap({
        'person_name': name,
        'relation': relation,
        'info': info,
        'access_level': accessLevel,
      });
      for (final f in files) form.files.add(f);
      final r = await _dio.post(ApiConfig.facesRegister, data: form);
      return r.data as Map<String, dynamic>;
    } catch (e) { debugPrint('[ApiService] registerFace error: $e'); return {'status': 'error'}; }
  }

  Future<MediaStatus> getMediaStatus() async {
    if (!await isOnline()) {
      return MediaStatus(
        state: 'stopped', position: 0, volume: 80, shuffle: false, repeat: false,
      );
    }
    try {
      final res = await _dio.get(ApiConfig.mediaStatus);
      return MediaStatus.fromJson(res.data as Map<String, dynamic>);
    } catch (e) { debugPrint('[ApiService] getMediaStatus error: $e');
      return MediaStatus(
        state: 'stopped', position: 0, volume: 80, shuffle: false, repeat: false,
      );
    }
  }

  Future<void> mediaPlay({int? trackIndex, String? query}) async {
    if (!await isOnline()) return;
    try {
      await _dio.post(ApiConfig.mediaPlay, queryParameters: {
        if (trackIndex != null) 'track_index': trackIndex,
        if (query != null) 'query': query,
      });
    } catch (e) { debugPrint('[ApiService] mediaPlay error: $e'); }
  }

  Future<void> mediaPause() async {
    if (await isOnline()) {
      try { await _dio.post(ApiConfig.mediaPause); } catch (e) { debugPrint('[ApiService] mediaPause error: $e'); }
    }
  }

  Future<void> mediaNext() async {
    if (await isOnline()) {
      try { await _dio.post(ApiConfig.mediaNext); } catch (e) { debugPrint('[ApiService] mediaNext error: $e'); }
    }
  }

  Future<void> setVolume(int vol) async {
    if (await isOnline()) {
      try { await _dio.post('${ApiConfig.mediaVolume}/$vol'); } catch (e) { debugPrint('[ApiService] setVolume error: $e'); }
    }
  }

  Future<List<Track>> getPlaylist() async {
    if (!await isOnline()) return [];
    try {
      final res = await _dio.get(ApiConfig.mediaPlaylist);
      return (res.data as List).map((j) => Track.fromJson(j)).toList();
    } catch (e) { debugPrint('[ApiService] getPlaylist error: $e'); return []; }
  }

  Future<List<Track>> getSuggestions(String mood) async {
    if (!await isOnline()) return [];
    try {
      final res = await _dio.get('${ApiConfig.musicSuggest}/$mood');
      return (res.data as List).map((j) => Track.fromJson(j)).toList();
    } catch (e) { debugPrint('[ApiService] getSuggestions error: $e'); return []; }
  }

  Future<Map<String, dynamic>> listFiles(String path) async {
    if (!await isOnline()) return {'files': [], 'dirs': []};
    try {
      final res = await _dio.get(ApiConfig.files, queryParameters: {'path': path});
      return res.data as Map<String, dynamic>;
    } catch (e) { debugPrint('[ApiService] listFiles error: $e');
      return {'files': [], 'dirs': []};
    }
  }

  void _pullRemindersFromServer() async {
    try {
      final r = await _dio.get(ApiConfig.reminders);
      for (final j in r.data as List) {
        final m = ReminderModel(
          title: j['title'],
          description: j['description'] ?? '',
          remindAt: DateTime.parse(j['remind_at']),
          repeat: j['repeat'] ?? 'none',
        );
        await localDB.insertReminder(m);
      }
    } catch (e) { debugPrint('[ApiService] _pullRemindersFromServer error: $e'); }
  }

  // —— Voice — STT and TTS —————————————————————
  Future<String> transcribeAudio(String filePath) async {
    try {
      final file = await MultipartFile.fromFile(filePath, filename: 'audio.wav');
      final form = FormData.fromMap({'audio': file});
      final r = await _dio.post(ApiConfig.stt, data: form);
      return (r.data as Map)['text'] as String? ?? '';
    } catch (e) {
      debugPrint('[STT] Error: $e');
      return '';
    }
  }

  Future<String> textToSpeech(String text) async {
    try {
      final r = await _dio.post(ApiConfig.tts, data: {'text': text});
      return (r.data as Map)['audio_url'] as String? ?? '';
    } catch (e) {
      debugPrint('[TTS] Error: $e');
      return '';
    }
  }

  // —— Build System (Phase 4/5) ————————————————————————
  Future<List<BuildProject>> getBuildProjects() async {
    if (!await isOnline()) return [];
    try {
      final r = await _dio.get(ApiConfig.buildProjects);
      final list = (r.data as Map)['projects'] as List? ?? [];
      return list.map((j) => BuildProject.fromJson(j as Map<String, dynamic>)).toList();
    } catch (e) { debugPrint('[ApiService] getBuildProjects error: $e'); return []; }
  }

  Future<BuildDetail?> getBuildDetail(String projectName) async {
    if (!await isOnline()) return null;
    try {
      final r = await _dio.get('${ApiConfig.buildStatus}/$projectName');
      return BuildDetail.fromJson(r.data as Map<String, dynamic>);
    } catch (e) { debugPrint('[ApiService] getBuildDetail error: $e'); return null; }
  }

  Future<List<GovernorDecision>> getGovernorHistory(String projectName) async {
    if (!await isOnline()) return [];
    try {
      final r = await _dio.get('${ApiConfig.buildGovernor}/$projectName');
      final list = (r.data as Map)['decisions'] as List? ?? [];
      return list.map((j) => GovernorDecision.fromJson(j as Map<String, dynamic>)).toList();
    } catch (e) { debugPrint('[ApiService] getGovernorHistory error: $e'); return []; }
  }

  Future<EnvironmentSnapshot?> getEnvironment() async {
    if (!await isOnline()) return null;
    try {
      final r = await _dio.get(ApiConfig.buildEnvironment);
      return EnvironmentSnapshot.fromJson(r.data as Map<String, dynamic>);
    } catch (e) { debugPrint('[ApiService] getEnvironment error: $e'); return null; }
  }

  Future<SystemIdentity?> getSystemIdentity() async {
    if (!await isOnline()) return null;
    try {
      final r = await _dio.get(ApiConfig.buildIdentity);
      return SystemIdentity.fromJson(r.data as Map<String, dynamic>);
    } catch (e) { debugPrint('[ApiService] getSystemIdentity error: $e'); return null; }
  }

  Future<bool> interruptBuild(String projectName) async {
    if (!await isOnline()) return false;
    try {
      final r = await _dio.post('${ApiConfig.buildInterrupt}/$projectName');
      return r.statusCode == 200;
    } catch (e) { debugPrint('[ApiService] interruptBuild error: $e'); return false; }
  }

  Future<List<String>> getCheckpoints(String projectName) async {
    if (!await isOnline()) return [];
    try {
      final r = await _dio.get('${ApiConfig.buildCheckpoints}/$projectName');
      return List<String>.from((r.data as Map)['checkpoints'] ?? []);
    } catch (e) { debugPrint('[ApiService] getCheckpoints error: $e'); return []; }
  }

  // —— Features ——————————————————————————————————
  Future<List<Feature>> getFeatures() async {
    if (!await isOnline()) return [];
    try {
      final r = await _dio.get(ApiConfig.features);
      final list = (r.data as Map)['features'] as List? ?? [];
      return list.map((j) => Feature.fromJson(j as Map<String, dynamic>)).toList();
    } catch (e) { debugPrint('[ApiService] getFeatures error: $e'); return []; }
  }

  Future<bool> toggleFeature(String slug, bool enabled) async {
    if (!await isOnline()) return false;
    try {
      final r = await _dio.post('${ApiConfig.features}/$slug/toggle', data: {'enabled': enabled});
      return r.statusCode == 200;
    } catch (e) { debugPrint('[ApiService] toggleFeature error: $e'); return false; }
  }

  // —— Integrations ——————————————————————————————
  Future<List<Integration>> getIntegrations() async {
    if (!await isOnline()) return [];
    try {
      final r = await _dio.get(ApiConfig.integrations);
      final list = (r.data as Map)['integrations'] as List? ?? [];
      return list.map((j) => Integration.fromJson(j as Map<String, dynamic>)).toList();
    } catch (e) { debugPrint('[ApiService] getIntegrations error: $e'); return []; }
  }

  Future<bool> connectIntegration(String name, Map<String, dynamic> creds) async {
    if (!await isOnline()) return false;
    try {
      final r = await _dio.post('${ApiConfig.integrations}/$name/connect', data: {'credentials': creds});
      return r.statusCode == 200;
    } catch (e) { debugPrint('[ApiService] connectIntegration error: $e'); return false; }
  }

  Future<bool> disconnectIntegration(String name) async {
    if (!await isOnline()) return false;
    try {
      final r = await _dio.post('${ApiConfig.integrations}/$name/disconnect');
      return r.statusCode == 200;
    } catch (e) { debugPrint('[ApiService] disconnectIntegration error: $e'); return false; }
  }

  // —— Diagnostics ———————————————————————————————
  Future<Map<String, dynamic>> getDiagnostics() async {
    if (!await isOnline()) return {};
    try {
      final r = await _dio.get(ApiConfig.diagnostics);
      return r.data as Map<String, dynamic>;
    } catch (e) { debugPrint('[ApiService] getDiagnostics error: $e'); return {}; }
  }

  // —— Models ————————————————————————————————————
  Future<Map<String, dynamic>> getModelInfo() async {
    if (!await isOnline()) return {};
    try {
      final r = await _dio.get(ApiConfig.models);
      return r.data as Map<String, dynamic>;
    } catch (e) { debugPrint('[ApiService] getModelInfo error: $e'); return {}; }
  }

  Future<Map<String, dynamic>> getModelGroups() async {
    if (!await isOnline()) return {};
    try {
      final r = await _dio.get(ApiConfig.modelGroups);
      return r.data as Map<String, dynamic>;
    } catch (e) { debugPrint('[ApiService] getModelGroups error: $e'); return {}; }
  }

  Future<bool> updateSetting(String key, dynamic value) async {
    if (!await isOnline()) return false;
    try {
      final r = await _dio.put('${ApiConfig.settings}/$key', data: {'value': value});
      return r.statusCode == 200;
    } catch (e) { debugPrint('[ApiService] updateSetting error: $e'); return false; }
  }

  // —— Agents ————————————————————————————————————
  Future<List<Agent>> getAgents() async {
    if (!await isOnline()) return [];
    try {
      final r = await _dio.get(ApiConfig.agents);
      final list = (r.data as Map)['agents'] as List? ?? [];
      return list.map((j) => Agent.fromJson(j as Map<String, dynamic>)).toList();
    } catch (e) { debugPrint('[ApiService] getAgents error: $e'); return []; }
  }

  Future<Map<String, dynamic>> runAgent(String name, String task, {String? mode}) async {
    if (!await isOnline()) return {'error': 'Offline'};
    try {
      final r = await _dio.post('${ApiConfig.agents}/$name/run', data: {
        'task': task,
        if (mode != null) 'mode': mode,
      });
      return r.data as Map<String, dynamic>;
    } catch (e) { return {'error': e.toString()}; }
  }
}

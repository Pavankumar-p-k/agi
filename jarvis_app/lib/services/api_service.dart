// lib/services/api_service.dart
import 'package:dio/dio.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart';
import '../config/api_config.dart';
import '../models/models.dart';
import 'mobile_automation_service.dart';

class ApiService {
  late final Dio _dio;

  ApiService() {
    _dio = Dio(BaseOptions(
      baseUrl: ApiConfig.baseUrl,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 30),
    ));

    // Attach Firebase token to every request
    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) async {
        try {
          final token = await FirebaseAuth.instance.currentUser?.getIdToken();
          if (token != null) {
            options.headers['Authorization'] = 'Bearer $token';
          }
        } catch (_) {}
        handler.next(options);
      },
      onError: (err, handler) {
        debugPrint('[API] Error ${err.response?.statusCode}: ${err.message}');
        handler.next(err);
      },
    ));
  }

  // ── Health ──
  Future<bool> isOnline() async {
    try {
      final res = await _dio.get(ApiConfig.health);
      return res.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  // ── Chat ──
  Future<Map<String, dynamic>> chat(String message) async {
    final local = await MobileAutomationService.tryHandleCommand(message);
    if (local != null) {
      final isSendIntent =
          RegExp(r'\b(send|message|msg|text|saying|say)\b', caseSensitive: false)
              .hasMatch(message);
      final localCompleted = local['success'] == true &&
          (!isSendIntent || local['auto_send'] == true);
      if (localCompleted) {
        return <String, dynamic>{
          'response': (local['speech'] ?? 'Done').toString(),
          'intent': 'android_native_automation',
          'automation': local,
        };
      }
    }
    try {
      final res = await _dio.post(ApiConfig.chat, data: {'message': message});
      return res.data;
    } catch (_) {
      if (local != null) {
        return <String, dynamic>{
          'response': (local['speech'] ?? 'Could not complete automation.').toString(),
          'intent': 'android_native_automation_partial',
          'automation': local,
        };
      }
      rethrow;
    }
  }

  Future<List<ChatMessage>> getChatHistory() async {
    final res = await _dio.get(ApiConfig.chatHistory);
    return (res.data as List).map((j) => ChatMessage.fromJson(j)).toList();
  }

  // ── Reminders ──
  Future<List<Reminder>> getReminders() async {
    final res = await _dio.get(ApiConfig.reminders);
    return (res.data as List).map((j) => Reminder.fromJson(j)).toList();
  }

  Future<Reminder> createReminder({
    required String title,
    required DateTime remindAt,
    String description = '',
    String repeat = 'none',
  }) async {
    final res = await _dio.post(ApiConfig.reminders, data: {
      'title': title,
      'remind_at': remindAt.toIso8601String(),
      'description': description,
      'repeat': repeat,
    });
    return Reminder.fromJson(res.data);
  }

  Future<void> deleteReminder(int id) async {
    await _dio.delete('${ApiConfig.reminders}/$id');
  }

  Future<void> completeReminder(int id) async {
    await _dio.post('${ApiConfig.reminders}/$id/complete');
  }

  Future<Map<String, dynamic>> completeTask({
    required int reminderId,
    String? notifyPlatform,
    String? notifyRecipient,
    String? notifyMessage,
  }) async {
    final data = <String, dynamic>{
      'reminder_id': reminderId,
      if (notifyPlatform != null) 'notify_platform': notifyPlatform,
      if (notifyRecipient != null) 'notify_recipient': notifyRecipient,
      if (notifyMessage != null) 'notify_message': notifyMessage,
    };
    final res = await _dio.post(ApiConfig.tasksComplete, data: data);
    return Map<String, dynamic>.from(res.data as Map);
  }

  // ── Notes ──
  Future<List<Note>> getNotes() async {
    final res = await _dio.get(ApiConfig.notes);
    return (res.data as List).map((j) => Note.fromJson(j)).toList();
  }

  Future<Note> createNote(String title, String content,
      {String tags = ''}) async {
    final res = await _dio.post(ApiConfig.notes, data: {
      'title': title,
      'content': content,
      'tags': tags,
    });
    return Note.fromJson(res.data);
  }

  Future<void> updateNote(int id, {String? title, String? content}) async {
    await _dio.put('${ApiConfig.notes}/$id', data: {
      if (title != null) 'title': title,
      if (content != null) 'content': content,
    });
  }

  Future<void> deleteNote(int id) async {
    await _dio.delete('${ApiConfig.notes}/$id');
  }

  // ── Activity & Summary ──
  Future<List<Activity>> getTodayActivity() async {
    final res = await _dio.get(ApiConfig.activity);
    return (res.data as List).map((j) => Activity.fromJson(j)).toList();
  }

  Future<DailySummary> getDailySummary() async {
    final res = await _dio.get(ApiConfig.summary);
    return DailySummary.fromJson(res.data);
  }

  // ── Messaging ──
  Future<bool> sendMessage(
      String platform, String recipient, String message) async {
    final res = await sendMessageDetailed(platform, recipient, message);
    return res['success'] == true;
  }

  Future<Map<String, dynamic>> sendMessageDetailed(
      String platform, String recipient, String message) async {
    final local = await MobileAutomationService.sendMessage(
      platform,
      recipient,
      message,
    );
    if (local['success'] == true && local['auto_send'] == true) {
      return local;
    }

    try {
      final res = await _dio.post(ApiConfig.messageSend, data: {
        'platform': platform,
        'recipient': recipient,
        'message': message,
      });
      return Map<String, dynamic>.from(res.data as Map);
    } catch (_) {
      return local;
    }
  }

  Future<Map<String, dynamic>> loginMessagingPlatform(String platform) async {
    final res = await _dio.post('/api/automation/messaging/login', data: {
      'platform': platform,
    });
    return Map<String, dynamic>.from(res.data as Map);
  }

  Future<Map<String, dynamic>> getAutoReplyProfile() async {
    final res = await _dio.get('/api/automation/messaging/auto-reply/profile');
    return Map<String, dynamic>.from(res.data as Map);
  }

  Future<Map<String, dynamic>> updateAutoReplyProfile({
    required String stylePrompt,
    String personaName = 'Pavan',
    String signature = '',
    int maxChars = 280,
  }) async {
    final res = await _dio.put('/api/automation/messaging/auto-reply/profile',
        data: {
          'persona_name': personaName,
          'style_prompt': stylePrompt,
          'signature': signature,
          'max_chars': maxChars,
        });
    return Map<String, dynamic>.from(res.data as Map);
  }

  Future<Map<String, dynamic>> generateAutoReply({
    required String platform,
    required String incomingMessage,
    required String sender,
    String context = '',
  }) async {
    final res = await _dio.post('/api/automation/messaging/auto-reply/generate',
        data: {
          'platform': platform,
          'incoming_message': incomingMessage,
          'sender': sender,
          'context': context,
        });
    return Map<String, dynamic>.from(res.data as Map);
  }

  Future<Map<String, dynamic>> autoReplyAndSend({
    required String platform,
    required String recipient,
    required String incomingMessage,
    String sender = '',
    String context = '',
  }) async {
    final res = await _dio.post('/api/automation/messaging/auto-reply/respond',
        data: {
          'platform': platform,
          'recipient': recipient,
          'incoming_message': incomingMessage,
          'sender': sender,
          'context': context,
        });
    return Map<String, dynamic>.from(res.data as Map);
  }

  // ── Faces ──
  Future<List<KnownFace>> getFaces() async {
    final res = await _dio.get(ApiConfig.facesList);
    return (res.data as List).map((j) => KnownFace.fromJson(j)).toList();
  }

  Future<Map<String, dynamic>> identifyFace(List<int> imageBytes) async {
    final formData = FormData.fromMap({
      'image': MultipartFile.fromBytes(imageBytes,
          filename: 'face.jpg', contentType: DioMediaType('image', 'jpeg')),
    });
    final res = await _dio.post(ApiConfig.facesIdentify, data: formData);
    return res.data;
  }

  Future<Map<String, dynamic>> registerFace({
    required String name,
    required List<List<int>> imageBytesList,
    String relation = 'unknown',
    String info = '',
    String accessLevel = 'visitor',
  }) async {
    final files = imageBytesList
        .asMap()
        .entries
        .map((e) => MapEntry(
            'images',
            MultipartFile.fromBytes(e.value,
                filename: 'img_${e.key}.jpg',
                contentType: DioMediaType('image', 'jpeg'))))
        .toList();

    final formData = FormData.fromMap({
      'person_name': name,
      'relation': relation,
      'info': info,
      'access_level': accessLevel,
    });
    for (final f in files) {
      formData.files.add(f);
    }

    final res = await _dio.post(ApiConfig.facesRegister, data: formData);
    return res.data;
  }

  // ── Media Player ──
  Future<MediaStatus> getMediaStatus() async {
    final res = await _dio.get(ApiConfig.mediaStatus);
    return MediaStatus.fromJson(res.data);
  }

  Future<void> mediaPlay({int? trackIndex, String? query}) async {
    await _dio.post(ApiConfig.mediaPlay, queryParameters: {
      if (trackIndex != null) 'track_index': trackIndex,
      if (query != null) 'query': query,
    });
  }

  Future<void> mediaPause() => _dio.post(ApiConfig.mediaPause);
  Future<void> mediaNext() => _dio.post(ApiConfig.mediaNext);

  Future<void> setVolume(int vol) async {
    await _dio.post('${ApiConfig.mediaVolume}/$vol');
  }

  Future<List<Track>> getPlaylist() async {
    final res = await _dio.get(ApiConfig.mediaPlaylist);
    return (res.data as List).map((j) => Track.fromJson(j)).toList();
  }

  Future<List<Track>> getSuggestions(String mood) async {
    final res = await _dio.get('${ApiConfig.musicSuggest}/$mood');
    return (res.data as List).map((j) => Track.fromJson(j)).toList();
  }

  // ── File Manager ──
  Future<Map<String, dynamic>> listFiles(String path) async {
    final res =
        await _dio.get(ApiConfig.files, queryParameters: {'path': path});
    return res.data;
  }
}

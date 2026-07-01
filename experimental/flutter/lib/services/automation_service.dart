// lib/services/automation_service.dart
//
// Dart-side service for all automation features:
// contacts, WhatsApp, Instagram, browser, apps, system

import 'package:dio/dio.dart';
import '../config/api_config.dart';

class AutomationService {
  late final Dio _dio;

  AutomationService() {
    _dio = Dio(BaseOptions(
      baseUrl: ApiConfig.baseUrl,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 30),
    ));
  }

  // ── Natural language command (one call does everything) ──
  Future<Map<String, dynamic>> command(String text) async {
    final res = await _dio.post('/api/automation/command',
        data: {'command': text});
    return res.data as Map<String, dynamic>;
  }

  // ── Contacts ──
  Future<List<Map<String, dynamic>>> getContacts() async {
    final res = await _dio.get('/api/automation/contacts');
    return List<Map<String, dynamic>>.from(res.data);
  }

  Future<List<Map<String, dynamic>>> searchContacts(String q) async {
    final res = await _dio.get('/api/automation/contacts/search',
        queryParameters: {'q': q});
    return List<Map<String, dynamic>>.from(res.data);
  }

  Future<Map<String, dynamic>> addContact({
    required String name,
    String phone      = '',
    String whatsapp   = '',
    String instagram  = '',
    String email      = '',
    String notes      = '',
  }) async {
    final res = await _dio.post('/api/automation/contacts', data: {
      'name': name, 'phone': phone, 'whatsapp': whatsapp,
      'instagram': instagram, 'email': email, 'notes': notes,
    });
    return res.data;
  }

  Future<bool> deleteContact(String name) async {
    final res = await _dio.delete('/api/automation/contacts/$name');
    return res.data['success'] == true;
  }

  // ── WhatsApp ──
  Future<Map<String, dynamic>> sendWhatsApp(String contact, String message) async {
    final res = await _dio.post('/api/automation/whatsapp/send',
        data: {'contact': contact, 'message': message});
    return res.data;
  }

  // ── Instagram ──
  Future<Map<String, dynamic>> sendInstagram(String contact, String message) async {
    final res = await _dio.post('/api/automation/instagram/send',
        data: {'contact': contact, 'message': message});
    return res.data;
  }

  // ── Browser ──
  Future<void> openUrl(String url) async {
    await _dio.post('/api/automation/browser/open', data: {'url': url});
  }

  Future<void> googleSearch(String q) async {
    await _dio.post('/api/automation/browser/google', data: {'query': q});
  }

  Future<void> youtubeSearch(String q, {bool autoplay = false}) async {
    await _dio.post('/api/automation/browser/youtube',
        data: {'query': q, 'autoplay': autoplay});
  }

  Future<void> mapsSearch(String place) async {
    await _dio.post('/api/automation/browser/maps', data: {'place': place});
  }

  // ── Apps ──
  Future<Map<String, dynamic>> launchApp(String appName) async {
    final res = await _dio.post('/api/automation/apps/launch',
        data: {'app': appName});
    return res.data;
  }

  // ── System ──
  Future<String> takeScreenshot() async {
    final res = await _dio.post('/api/automation/system/screenshot');
    return res.data['path'] ?? '';
  }

  Future<void> setVolume(String action, {int steps = 2}) async {
    await _dio.post('/api/automation/system/volume',
        data: {'action': action, 'steps': steps});
  }

  Future<void> lockScreen()      => _dio.post('/api/automation/system/lock');
  Future<void> sleep()           => _dio.post('/api/automation/system/sleep');
  Future<void> shutdown({int delay = 60}) =>
      _dio.post('/api/automation/system/shutdown', data: {'delay': delay});
  Future<void> cancelShutdown()  => _dio.post('/api/automation/system/cancel_shutdown');
}

// lib/services/supabase_service.dart
// JARVIS — Supabase Remote Connectivity Service
// Signs in anonymously, sends messages, polls for responses,
// downloads files received from JARVIS server.

import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import '../config/api_config.dart';

class SupabaseResponse {
  final String text;
  final List<SupabaseFile> files;
  final Map<String, dynamic>? plan;
  final Map<String, dynamic>? progress;

  SupabaseResponse({required this.text, this.files = const [], this.plan, this.progress});
}

class SupabaseFile {
  final String name;
  final String url;
  final int size;
  final String type;
  String? localPath;

  SupabaseFile({required this.name, required this.url, required this.size, required this.type, this.localPath});
}

class SupabaseService {
  static final SupabaseService _instance = SupabaseService._();
  factory SupabaseService() => _instance;
  SupabaseService._();

  final http.Client _client = http.Client();
  bool _initialized = false;
  String _jwt = '';
  String _userId = 'default';

  String get _supabaseUrl => ApiConfig.supabaseUrl;
  String get _anonKey => ApiConfig.supabaseAnonKey;

  Map<String, String> get _headers => {
    'apikey': _anonKey,
    'Authorization': 'Bearer $_jwt',
    'Content-Type': 'application/json',
    'Prefer': 'return=minimal',
  };

  Future<void> init() async {
    if (_initialized) return;
    try {
      final resp = await _client.post(
        Uri.parse('$_supabaseUrl/auth/v1/signup'),
        headers: {'apikey': _anonKey, 'Content-Type': 'application/json'},
        body: '{}',
      );
      if (resp.statusCode == 200) {
        final data = jsonDecode(resp.body) as Map<String, dynamic>;
        _jwt = data['access_token'] as String? ?? '';
        final user = data['user'] as Map<String, dynamic>?;
        _userId = user?['id'] as String? ?? 'default';
      }
    } catch (_) {}
    _initialized = true;
  }

  Future<SupabaseResponse> sendAndWait(String text, {String intent = 'chat', Duration pollInterval = const Duration(seconds: 2), Duration timeout = const Duration(seconds: 60)}) async {
    if (_jwt.isEmpty) return SupabaseResponse(text: 'Not connected to JARVIS.');

    final before = DateTime.now().toUtc().toIso8601String();

    await _client.post(
      Uri.parse('$_supabaseUrl/rest/v1/messages'),
      headers: _headers,
      body: jsonEncode({
        'user_id': _userId,
        'role': 'user',
        'content': text,
        'status': 'pending',
        'intent': intent,
      }),
    );

    final deadline = DateTime.now().add(timeout);
    while (DateTime.now().isBefore(deadline)) {
      await Future.delayed(pollInterval);
      try {
        final queryResp = await _client.get(
          Uri.parse('$_supabaseUrl/rest/v1/messages'
              '?role=eq.assistant'
              '&user_id=eq.$_userId'
              '&created_at=gt.$before'
              '&order=created_at.desc'
              '&limit=1'),
          headers: _headers,
        );
        if (queryResp.statusCode == 200 && queryResp.body.isNotEmpty) {
          final rows = jsonDecode(queryResp.body) as List;
          if (rows.isNotEmpty) {
            final content = rows[0]['content'] as String? ?? '';
            final metadataRaw = rows[0]['metadata'];
            List<SupabaseFile> files = [];
            Map<String, dynamic>? plan;
            Map<String, dynamic>? progress;

            if (metadataRaw != null && metadataRaw is String && metadataRaw.isNotEmpty) {
              try {
                final meta = jsonDecode(metadataRaw);
                files = await _processFileMeta(meta);
                if (meta['plan'] is Map) plan = meta['plan'] as Map<String, dynamic>;
                if (meta['progress'] is Map) progress = meta['progress'] as Map<String, dynamic>;
              } catch (_) {}
            } else if (metadataRaw is Map) {
              final meta = metadataRaw as Map<String, dynamic>;
              files = await _processFileMeta(meta);
              if (meta['plan'] is Map) plan = meta['plan'] as Map<String, dynamic>;
              if (meta['progress'] is Map) progress = meta['progress'] as Map<String, dynamic>;
            }

            if (content.isNotEmpty) {
              return SupabaseResponse(text: content, files: files, plan: plan, progress: progress);
            }
          }
        }
      } catch (_) {}
    }
    return SupabaseResponse(text: 'Request timed out. JARVIS may be offline.');
  }

  /// Send a goal for JARVIS to plan and execute
  Future<SupabaseResponse> sendGoal(String goal) {
    return sendAndWait(goal, intent: 'goal', timeout: const Duration(seconds: 120));
  }

  /// Approve or reject a plan
  Future<SupabaseResponse> approvePlan(String planId) {
    return sendAndWait('approve $planId', intent: 'plan_status');
  }

  Future<SupabaseResponse> rejectPlan(String planId) {
    return sendAndWait('reject $planId', intent: 'plan_status');
  }

  /// Check plan/project status
  Future<SupabaseResponse> checkPlanStatus() {
    return sendAndWait('status', intent: 'plan_status');
  }

  /// Get the latest assistant response without sending a message
  Future<SupabaseResponse?> getLatestResponse() async {
    if (_jwt.isEmpty) return null;
    try {
      final queryResp = await _client.get(
        Uri.parse('$_supabaseUrl/rest/v1/messages'
            '?role=eq.assistant'
            '&user_id=eq.$_userId'
            '&order=created_at.desc'
            '&limit=1'),
        headers: _headers,
      );
      if (queryResp.statusCode == 200 && queryResp.body.isNotEmpty) {
        final rows = jsonDecode(queryResp.body) as List;
        if (rows.isNotEmpty) {
          final content = rows[0]['content'] as String? ?? '';
          final metadataRaw = rows[0]['metadata'];
          List<SupabaseFile> files = [];
          Map<String, dynamic>? plan;
          Map<String, dynamic>? progress;

          if (metadataRaw != null && metadataRaw is String && metadataRaw.isNotEmpty) {
            try {
              final meta = jsonDecode(metadataRaw);
              files = await _processFileMeta(meta);
              if (meta['plan'] is Map) plan = meta['plan'] as Map<String, dynamic>;
              if (meta['progress'] is Map) progress = meta['progress'] as Map<String, dynamic>;
            } catch (_) {}
          } else if (metadataRaw is Map) {
            final meta = metadataRaw as Map<String, dynamic>;
            files = await _processFileMeta(meta);
            if (meta['plan'] is Map) plan = meta['plan'] as Map<String, dynamic>;
            if (meta['progress'] is Map) progress = meta['progress'] as Map<String, dynamic>;
          }
          return SupabaseResponse(text: content, files: files, plan: plan, progress: progress);
        }
      }
    } catch (_) {}
    return null;
  }

  Future<List<SupabaseFile>> _processFileMeta(Map<String, dynamic> meta) async {
    final files = <SupabaseFile>[];
    final items = meta.containsKey('name') ? [meta] : (meta['files'] is List ? meta['files'] as List : []);

    for (final item in items) {
      if (item is Map<String, dynamic>) {
        final file = SupabaseFile(
          name: item['name'] as String? ?? 'file',
          url: item['url'] as String? ?? '',
          size: (item['size'] as num?)?.toInt() ?? 0,
          type: item['type'] as String? ?? 'application/octet-stream',
        );
        try {
          final dir = await getApplicationDocumentsDirectory();
          final savePath = '${dir.path}/${file.name}';
          final fileResp = await _client.get(Uri.parse(file.url));
          if (fileResp.statusCode == 200) {
            await File(savePath).writeAsBytes(fileResp.bodyBytes);
            file.localPath = savePath;
          }
        } catch (_) {}
        files.add(file);
      }
    }
    return files;
  }

  void dispose() {
    _client.close();
  }
}

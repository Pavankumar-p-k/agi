// lib/ai/model_detector.dart
// Auto-detects which local AI model server is running on the phone.
// Call ModelDetector.autoDetectAndSave() once in main.dart on startup.

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:jarvis_app/services/feature_settings.dart';

class ModelDetector {
  static const _timeout = Duration(seconds: 3);

  // Priority-ordered list of endpoints to probe
  static const _endpoints = [
    _Endpoint('MLC Chat — Gemma 4 E2B', 'http://127.0.0.1:8080',
        '/v1/models', 'gemma-4-e2b-it', 'openAI'),
    _Endpoint('Ollama', 'http://127.0.0.1:11434',
        '/api/tags', 'gemma4:e2b', 'ollama'),
    _Endpoint('Ollama alt port', 'http://127.0.0.1:11435',
        '/api/tags', 'gemma4:e2b', 'ollama'),
    _Endpoint('LM Studio', 'http://127.0.0.1:1234',
        '/v1/models', 'gemma-4-e2b-it', 'openAI'),
    _Endpoint('llama.cpp Termux', 'http://127.0.0.1:8000',
        '/health', 'gemma-4-e2b-it', 'llamaCpp'),
  ];

  /// Probes all known endpoints, saves the first one that responds.
  /// Non-blocking — call with .then() in main.dart.
  /// Returns the detected model name or null if nothing found.
  static Future<String?> autoDetectAndSave() async {
    debugPrint('[ModelDetector] Starting auto-detection...');
    for (final e in _endpoints) {
      if (await _probe(e)) {
        await FeatureSettings.setOllamaUrl(e.baseUrl);
        await FeatureSettings.setOllamaModel(e.modelName);
        await FeatureSettings.setApiFormat(e.format);
        debugPrint('[ModelDetector] Using: ${e.name} @ ${e.baseUrl}');
        return e.modelName;
      }
    }
    debugPrint('[ModelDetector] No local model found — Gemini fallback active');
    return null;
  }

  /// Probe without saving — used by the settings screen Test button.
  static Future<String?> detectOnly() async {
    for (final e in _endpoints) {
      if (await _probe(e)) return '${e.name} (${e.modelName})';
    }
    return null;
  }

  static Future<bool> _probe(_Endpoint e) async {
    try {
      final res = await http
          .get(Uri.parse('${e.baseUrl}${e.testPath}'))
          .timeout(_timeout);
      if (res.statusCode == 200) {
        debugPrint('[ModelDetector] ✓ ${e.name}');
        return true;
      }
    } catch (_) {}
    return false;
  }
}

class _Endpoint {
  final String name;
  final String baseUrl;
  final String testPath;
  final String modelName;
  final String format;
  const _Endpoint(
      this.name, this.baseUrl, this.testPath, this.modelName, this.format);
}

import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

class ModelDetectionResult {
  final bool connected;
  final String backend;
  final String apiFormat;
  final String baseUrl;
  final String model;
  final String message;

  const ModelDetectionResult({
    required this.connected,
    required this.backend,
    required this.apiFormat,
    required this.baseUrl,
    required this.model,
    required this.message,
  });

  String get statusLabel => connected ? 'Connected' : 'Disconnected';
}

class ModelDetector {
  static const String defaultBaseUrl = 'http://127.0.0.1:11434';
  static const String defaultModel = 'llama3.2';
  static const String defaultApiFormat = 'ollama';

  static Future<ModelDetectionResult> autoDetectAndSave() async {
    final prefs = await SharedPreferences.getInstance();
    final baseUrl = prefs.getString('ollama_url')?.trim() ?? defaultBaseUrl;
    final currentModel = prefs.getString('model') ?? defaultModel;
    final currentFormat = prefs.getString('api_format') ?? defaultApiFormat;

    final result = await detectLocalBackend(baseUrl, currentModel, currentFormat);
    if (result.connected) {
      await prefs.setString('api_format', result.apiFormat);
      await prefs.setString('model', result.model);
      await prefs.setString('ollama_url', result.baseUrl);
    }
    return result;
  }

  static Future<ModelDetectionResult> detectLocalBackend(
    String baseUrl,
    String currentModel,
    String currentFormat,
  ) async {
    final trimmed = baseUrl.trim();
    if (trimmed.isEmpty) {
      return ModelDetectionResult(
        connected: false,
        backend: 'Unknown',
        apiFormat: currentFormat,
        baseUrl: trimmed,
        model: currentModel,
        message: 'Local model URL is empty.',
      );
    }

    final url = trimmed.endsWith('/') ? trimmed.substring(0, trimmed.length - 1) : trimmed;

    final ollamaResult = await _checkOllama(url, currentModel);
    if (ollamaResult.connected) {
      return ollamaResult;
    }

    final openAiResult = await _checkOpenAi(url, currentModel);
    if (openAiResult.connected) {
      return openAiResult;
    }

    return ModelDetectionResult(
      connected: false,
      backend: 'Unknown',
      apiFormat: currentFormat,
      baseUrl: url,
      model: currentModel,
      message: 'No compatible local model endpoint detected.',
    );
  }

  static Future<ModelDetectionResult> _checkOllama(
    String url,
    String currentModel,
  ) async {
    try {
      final uri = Uri.parse('$url/api/models');
      final response = await http.get(uri).timeout(const Duration(seconds: 4));
      if (response.statusCode != 200) {
        return ModelDetectionResult(
          connected: false,
          backend: 'Ollama',
          apiFormat: 'ollama',
          baseUrl: url,
          model: currentModel,
          message: 'Ollama probe returned ${response.statusCode}.',
        );
      }

      final data = jsonDecode(response.body);
      if (data is Map<String, dynamic> && data['models'] is List) {
        final models = (data['models'] as List)
            .whereType<Map<String, dynamic>>()
            .map((item) => item['name']?.toString() ?? '')
            .where((name) => name.isNotEmpty)
            .toList();
        final selectedModel = models.contains(currentModel)
            ? currentModel
            : (models.isNotEmpty ? models.first : currentModel);

        return ModelDetectionResult(
          connected: true,
          backend: 'Ollama',
          apiFormat: 'ollama',
          baseUrl: url,
          model: selectedModel,
          message: 'Ollama server detected.',
        );
      }

      return ModelDetectionResult(
        connected: false,
        backend: 'Ollama',
        apiFormat: 'ollama',
        baseUrl: url,
        model: currentModel,
        message: 'Ollama endpoint did not return a models list.',
      );
    } catch (e) {
      return ModelDetectionResult(
        connected: false,
        backend: 'Ollama',
        apiFormat: 'ollama',
        baseUrl: url,
        model: currentModel,
        message: 'Ollama probe failed: $e',
      );
    }
  }

  static Future<ModelDetectionResult> _checkOpenAi(
    String url,
    String currentModel,
  ) async {
    const paths = ['/v1/models', '/openai/models'];
    for (final path in paths) {
      try {
        final uri = Uri.parse('$url$path');
        final response = await http.get(uri).timeout(const Duration(seconds: 4));
        if (response.statusCode != 200) {
          continue;
        }

        final data = jsonDecode(response.body);
        if (data is Map<String, dynamic>) {
          final objectType = data['object']?.toString().toLowerCase();
          final hasData = data['data'] is List;
          if (hasData || objectType == 'list') {
            return ModelDetectionResult(
              connected: true,
              backend: 'OpenAI-compatible',
              apiFormat: 'openai',
              baseUrl: url,
              model: currentModel,
              message: 'OpenAI-compatible local model endpoint detected.',
            );
          }
        }
      } catch (_) {
        continue;
      }
    }

    return ModelDetectionResult(
      connected: false,
      backend: 'OpenAI-compatible',
      apiFormat: 'openai',
      baseUrl: url,
      model: currentModel,
      message: 'OpenAI-compatible probe did not find a working endpoint.',
    );
  }
}

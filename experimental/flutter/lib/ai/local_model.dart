// lib/ai/local_model.dart
// Routes LLM calls to Ollama, MLC Chat (OpenAI format), or llama.cpp.
// Format is set automatically by ModelDetector on startup.

import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:jarvis_app/services/feature_settings.dart';

class LocalModel {
  static const _stopSequences = ['\n\n', 'Them:', 'Me:', '---'];
  static const _maxTokens     = 80;
  static const _temperature   = 0.75;
  static const _timeout       = Duration(seconds: 15);

  /// Main entry point. Reads api_format from FeatureSettings
  /// and routes to the correct backend automatically.
  static Future<String?> generate(String prompt) async {
    final url    = FeatureSettings.getOllamaUrl();
    final model  = FeatureSettings.getOllamaModel();
    final format = FeatureSettings.getApiFormat();

    debugPrint('[LocalModel] format=$format url=$url model=$model');

    switch (format) {
      case 'openAI':
        return _callOpenAi(url, model, prompt);
      case 'llamaCpp':
        return _callLlamaCpp(url, prompt);
      case 'ollama':
      default:
        return _callOllama(url, model, prompt);
    }
  }

  // ── Ollama (/api/generate) ────────────────────────────────
  static Future<String?> _callOllama(
      String url, String model, String prompt) async {
    try {
      final res = await http
          .post(
            Uri.parse('$url/api/generate'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'model': model,
              'prompt': prompt,
              'stream': false,
              'options': {
                'temperature': _temperature,
                'top_p': 0.9,
                'num_predict': _maxTokens,
                'stop': _stopSequences,
              },
            }),
          )
          .timeout(_timeout);
      if (res.statusCode == 200) {
        return (jsonDecode(res.body)['response'] as String?)?.trim();
      }
      debugPrint('[LocalModel] Ollama HTTP ${res.statusCode}');
    } on TimeoutException {
      debugPrint('[LocalModel] Ollama timeout');
    } catch (e) {
      debugPrint('[LocalModel] Ollama error: $e');
    }
    return null;
  }

  // ── OpenAI-compatible (/v1/chat/completions) ──────────────
  // Used by: MLC Chat, LM Studio
  static Future<String?> _callOpenAi(
      String url, String model, String prompt) async {
    try {
      final res = await http
          .post(
            Uri.parse('$url/v1/chat/completions'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'model': model,
              'messages': [
                {'role': 'user', 'content': prompt}
              ],
              'max_tokens': _maxTokens,
              'temperature': _temperature,
              'stop': _stopSequences,
            }),
          )
          .timeout(_timeout);
      if (res.statusCode == 200) {
        final data = jsonDecode(res.body);
        return (data['choices']?[0]?['message']?['content'] as String?)
            ?.trim();
      }
      debugPrint('[LocalModel] OpenAI-format HTTP ${res.statusCode}');
    } on TimeoutException {
      debugPrint('[LocalModel] OpenAI-format timeout');
    } catch (e) {
      debugPrint('[LocalModel] OpenAI-format error: $e');
    }
    return null;
  }

  // ── llama.cpp server (/completion) ───────────────────────
  static Future<String?> _callLlamaCpp(
      String url, String prompt) async {
    try {
      final res = await http
          .post(
            Uri.parse('$url/completion'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'prompt': prompt,
              'n_predict': _maxTokens,
              'temperature': _temperature,
              'stop': _stopSequences,
            }),
          )
          .timeout(_timeout);
      if (res.statusCode == 200) {
        return (jsonDecode(res.body)['content'] as String?)?.trim();
      }
      debugPrint('[LocalModel] llama.cpp HTTP ${res.statusCode}');
    } on TimeoutException {
      debugPrint('[LocalModel] llama.cpp timeout');
    } catch (e) {
      debugPrint('[LocalModel] llama.cpp error: $e');
    }
    return null;
  }
}

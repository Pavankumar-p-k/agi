// lib/ai/gemini_model.dart
// Gemini 1.5 Flash fallback — only called if local model returns null.

import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:jarvis_app/services/feature_settings.dart';

class GeminiModel {
  static const _model   = 'gemini-1.5-flash-latest';
  static const _baseUrl = 'https://generativelanguage.googleapis.com/v1beta/models';
  static const _timeout = Duration(seconds: 20);
  static const _maxTokens  = 80;
  static const _temperature = 0.75;

  /// Call Gemini API. Returns null silently if key not set.
  static Future<String?> generate(String prompt) async {
    final key = FeatureSettings.getGeminiApiKey();
    if (key.isEmpty) {
      debugPrint('[GeminiModel] No API key set — skipping');
      return null;
    }

    try {
      final res = await http
          .post(
            Uri.parse('$_baseUrl/$_model:generateContent?key=$key'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'contents': [
                {
                  'parts': [
                    {'text': prompt}
                  ]
                }
              ],
              'generationConfig': {
                'temperature': _temperature,
                'maxOutputTokens': _maxTokens,
                'stopSequences': ['\n\n', 'Them:', 'Me:'],
              },
              'safetySettings': [
                {'category': 'HARM_CATEGORY_HARASSMENT',        'threshold': 'BLOCK_NONE'},
                {'category': 'HARM_CATEGORY_HATE_SPEECH',       'threshold': 'BLOCK_NONE'},
                {'category': 'HARM_CATEGORY_SEXUALLY_EXPLICIT', 'threshold': 'BLOCK_NONE'},
                {'category': 'HARM_CATEGORY_DANGEROUS_CONTENT', 'threshold': 'BLOCK_NONE'},
              ],
            }),
          )
          .timeout(_timeout);

      if (res.statusCode == 200) {
        final data = jsonDecode(res.body);
        final text =
            data['candidates']?[0]?['content']?['parts']?[0]?['text'];
        return (text as String?)?.trim();
      }
      debugPrint('[GeminiModel] HTTP ${res.statusCode}: ${res.body}');
    } on TimeoutException {
      debugPrint('[GeminiModel] Timeout');
    } catch (e) {
      debugPrint('[GeminiModel] Error: $e');
    }
    return null;
  }
}

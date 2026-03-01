import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

class MobileAutomationService {
  static const MethodChannel _method =
      MethodChannel('com.jarvis.app/call_service');

  static Future<Map<String, dynamic>?> tryHandleCommand(String text) async {
    if (kIsWeb || defaultTargetPlatform != TargetPlatform.android) {
      return null;
    }

    final query = text.trim();
    if (query.isEmpty) return null;

    final normalized = _normalize(query);
    final hasWhatsApp = _mentionsWhatsApp(normalized);
    final hasInstagram = _mentionsInstagram(normalized);

    if (!hasWhatsApp && !hasInstagram) {
      return null;
    }

    final wantsSend = _containsSendIntent(normalized);

    if (hasWhatsApp) {
      return await _handlePlatform(
        platform: 'whatsapp',
        query: query,
        wantsSend: wantsSend,
      );
    }

    return await _handlePlatform(
      platform: 'instagram',
      query: query,
      wantsSend: wantsSend,
    );
  }

  static Future<Map<String, dynamic>> sendMessage(
    String platform,
    String recipient,
    String message,
  ) async {
    if (kIsWeb || defaultTargetPlatform != TargetPlatform.android) {
      return <String, dynamic>{'success': false, 'error': 'not_android'};
    }

    final p = platform.toLowerCase().trim();
    final method =
        p == 'whatsapp' ? 'sendWhatsAppNative' : 'sendInstagramNative';
    final openMethod =
        p == 'whatsapp' ? 'openWhatsAppNative' : 'openInstagramNative';

    try {
      final raw = await _method.invokeMethod<dynamic>(method, {
        'recipient': recipient,
        'message': message,
      });
      final response = _ensureSpeech(_asMap(raw), platform: p);
      final autoSend = response['auto_send'] == true;
      if (response['success'] == true && autoSend) {
        return response;
      }

      final opened = response['success'] == true
          ? true
          : await _safeOpen(openMethod);
      if (!opened) {
        return response;
      }
      return <String, dynamic>{
        ...response,
        'success': false,
        'auto_send': false,
        'opened': true,
        'native': true,
        'speech':
            'Opened $p on your phone. Auto-send failed, so review and send manually.',
      };
    } on PlatformException catch (e) {
      final opened = await _safeOpen(openMethod);
      return <String, dynamic>{
        'success': opened,
        'platform': p,
        'error': e.message ?? e.code,
        'opened': opened,
        'speech': opened
            ? 'Opened $p on your phone. Please send manually.'
            : 'Could not complete $p automation on this phone.',
      };
    }
  }

  static Future<Map<String, dynamic>> _handlePlatform({
    required String platform,
    required String query,
    required bool wantsSend,
  }) async {
    final openMethod =
        platform == 'whatsapp' ? 'openWhatsAppNative' : 'openInstagramNative';
    final sendMethod =
        platform == 'whatsapp' ? 'sendWhatsAppNative' : 'sendInstagramNative';

    if (wantsSend) {
      final parsed = _extractRecipientAndMessage(query);
      if (parsed != null) {
        try {
          final raw = await _method.invokeMethod<dynamic>(sendMethod, {
            'recipient': _stripPlatformWords(parsed.$1),
            'message': parsed.$2,
          });
          final response = _ensureSpeech(
            _asMap(raw),
            platform: platform,
          );

          if (response['success'] == true && response['auto_send'] == true) {
            return response;
          }

          final opened = response['success'] == true
              ? true
              : await _safeOpen(openMethod);
          return <String, dynamic>{
            ...response,
            'success': false,
            'auto_send': false,
            'opened': opened,
            'speech': opened
                ? 'Opening $platform. Please send the message manually.'
                : (response['speech'] ?? 'Could not open $platform.'),
          };
        } on PlatformException catch (e) {
          final opened = await _safeOpen(openMethod);
          return <String, dynamic>{
            'success': false,
            'platform': platform,
            'opened': opened,
            'error': e.message ?? e.code,
            'speech': opened
                ? 'Opening $platform. Please send the message manually.'
                : 'Could not open $platform on your phone.',
            'native': true,
          };
        }
      }
    }

    final opened = await _safeOpen(openMethod);
    return <String, dynamic>{
      'success': opened,
      'platform': platform,
      'action': 'open_${platform}_android',
      'speech': opened
          ? 'Opening $platform on your phone.'
          : 'Could not open $platform on your phone.',
      'native': true,
    };
  }

  static Future<bool> _safeOpen(String method) async {
    try {
      final ok = await _method.invokeMethod<bool>(method);
      return ok == true;
    } catch (_) {
      return false;
    }
  }

  static String _normalize(String value) {
    return value
        .toLowerCase()
        .replaceAll(RegExp(r'[^a-z0-9@:+\s]'), ' ')
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
  }

  static bool _containsSendIntent(String query) {
    return RegExp(r'\b(send|message|msg|text|saying|say)\b').hasMatch(query);
  }

  static bool _mentionsWhatsApp(String query) {
    return RegExp(
      r'\b(whatsapp|whatsap|watsapp|whtas|whts|whats|wa|whatsup)\b',
    ).hasMatch(query);
  }

  static bool _mentionsInstagram(String query) {
    return RegExp(r'\b(instagram|insta|ig)\b').hasMatch(query);
  }

  static (String, String)? _extractRecipientAndMessage(String query) {
    final patterns = <RegExp>[
      RegExp(
        r'\bto\s+(.+?)\s+(?:saying|say|message|msg|text|:)\s*(.+)$',
        caseSensitive: false,
      ),
      RegExp(
        r'^(?:send|message|text|msg)\s+(.+?)\s+(?:saying|say|message|msg|text|:)\s*(.+)$',
        caseSensitive: false,
      ),
      RegExp(
        r'\bto\s+(.+?)\s+(.+)$',
        caseSensitive: false,
      ),
    ];

    for (final pattern in patterns) {
      final match = pattern.firstMatch(query);
      if (match == null) continue;

      final recipient = (match.group(1) ?? '').trim();
      final message = (match.group(2) ?? '').trim();
      if (recipient.isNotEmpty && message.isNotEmpty) {
        return (recipient, message);
      }
    }

    return null;
  }

  static String _stripPlatformWords(String recipient) {
    return recipient
        .replaceAll(RegExp(r'\b(on|via)\b', caseSensitive: false), ' ')
        .replaceAll(
          RegExp(
            r'\b(whatsapp|whatsap|watsapp|whtas|whts|whats|wa|whatsup|instagram|insta|ig)\b',
            caseSensitive: false,
          ),
          ' ',
        )
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
  }

  static Map<String, dynamic> _asMap(dynamic raw) {
    if (raw is Map) {
      return Map<String, dynamic>.from(raw);
    }
    return <String, dynamic>{
      'success': false,
      'error': 'invalid_native_response',
    };
  }

  static Map<String, dynamic> _ensureSpeech(
    Map<String, dynamic> value, {
    required String platform,
  }) {
    if ((value['speech'] ?? '').toString().trim().isNotEmpty) {
      return value;
    }

    if (value['success'] == true) {
      return <String, dynamic>{
        ...value,
        'speech': 'Done. Opened $platform on your phone.',
      };
    }

    final err = (value['error'] ?? 'automation_failed').toString();
    return <String, dynamic>{
      ...value,
      'speech': 'Could not complete $platform automation: $err',
    };
  }
}

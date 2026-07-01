import 'package:flutter/services.dart';

class DeviceAutomationService {
  static const MethodChannel _channel =
      MethodChannel('com.example.jarvis_app/automation');

  Future<void> openApp(String packageName) async {
    await _channel.invokeMethod('openApp', {'package': packageName});
  }

  Future<void> searchWeb(String query) async {
    await _channel.invokeMethod('search', {'query': query});
  }

  Future<void> openUrl(String url) async {
    await _channel.invokeMethod('openUrl', {'url': url});
  }

  Future<void> composeSms(String number, String text) async {
    await _channel.invokeMethod('composeSms', {
      'number': number,
      'text': text,
    });
  }

  Future<void> composeEmail({
    required String email,
    String subject = '',
    String body = '',
  }) async {
    await _channel.invokeMethod('composeEmail', {
      'email': email,
      'subject': subject,
      'body': body,
    });
  }

  Future<void> composeWhatsApp({
    required String number,
    required String text,
  }) async {
    await _channel.invokeMethod('composeWhatsApp', {
      'number': number,
      'text': text,
    });
  }
}

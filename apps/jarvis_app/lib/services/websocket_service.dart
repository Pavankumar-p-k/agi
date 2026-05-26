// lib/services/websocket_service.dart
import 'package:flutter/foundation.dart';
import 'dart:convert';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../config/api_config.dart';

class WebSocketService extends ChangeNotifier {
  WebSocketChannel? _channel;
  bool _isConnected = false;
  final List<Map<String, dynamic>> _messageQueue = [];

  // Callbacks
  Function(Map)? onChatResponse;
  Function(Map)? onFaceResult;
  Function(String)? onScreenFrame;   // base64 JPEG
  Function(Map)? onCommandResponse;
  Function(Map)? onNotification;

  bool get isConnected => _isConnected;

  Future<void> connect() async {
    final platform = defaultTargetPlatform;
    final platformTag = switch (platform) {
      TargetPlatform.android => 'android',
      TargetPlatform.iOS => 'ios',
      TargetPlatform.macOS => 'macos',
      TargetPlatform.windows => 'windows',
      TargetPlatform.linux => 'linux',
      TargetPlatform.fuchsia => 'fuchsia',
    };
    final deviceId = '${platformTag}_guest';
    const userId = 1;

    try {
      final prefs = await SharedPreferences.getInstance();
      final savedApi = prefs.getString('api_url');
      final savedWs  = prefs.getString('ws_url');
      final wsBase = (savedWs != null && savedWs.trim().isNotEmpty)
          ? savedWs.trim()
          : (savedApi != null && savedApi.trim().isNotEmpty)
              ? savedApi.trim()
                  .replaceFirst('https://', 'wss://')
                  .replaceFirst('http://', 'ws://')
              : ApiConfig.wsUrl;
      final wsUrl = wsBase.contains('/ws') ? wsBase : '$wsBase/ws';

      _channel = WebSocketChannel.connect(
        Uri.parse('$wsUrl/$deviceId/$userId'),
      );

      _channel!.stream.listen(
        _onMessage,
        onError: _onError,
        onDone: _onDone,
      );

      _isConnected = true;
      notifyListeners();

      // Flush queued messages
      for (final msg in _messageQueue) {
        _send(msg);
      }
      _messageQueue.clear();

      debugPrint('[WS] Connected ✓');
    } catch (e) {
      debugPrint('[WS] Connection failed: $e');
    }
  }

  void _onMessage(dynamic raw) {
    try {
      final msg = jsonDecode(raw as String) as Map<String, dynamic>;
      final type = msg['type'] as String?;
      final payload = msg['payload'] as Map<String, dynamic>? ?? {};

      switch (type) {
        case 'chat_response':   onChatResponse?.call(payload);
        case 'face_result':     onFaceResult?.call(payload);
        case 'screen_frame':    onScreenFrame?.call(payload['frame_base64'] as String? ?? '');
        case 'command_response': onCommandResponse?.call(payload);
        case 'notification':    onNotification?.call(payload);
        case 'pong':            debugPrint('[WS] Pong received');
      }
    } catch (e) {
      debugPrint('[WS] Parse error: $e');
    }
  }

  void _onError(error) {
    debugPrint('[WS] Error: $error');
    _isConnected = false;
    notifyListeners();
  }

  void _onDone() {
    debugPrint('[WS] Disconnected');
    _isConnected = false;
    notifyListeners();
  }

  void _send(Map<String, dynamic> data) {
    try {
      _channel?.sink.add(jsonEncode(data));
    } catch (e) {
      debugPrint('[WS] Send error: $e');
    }
  }

  void send(String type, Map<String, dynamic> payload) {
    final msg = {'type': type, 'payload': payload};
    if (_isConnected) {
      _send(msg);
    } else {
      _messageQueue.add(msg);
    }
  }

  void sendChat(String text)        => send('chat', {'text': text});
  void ping()                       => send('ping', {});
  void requestScreenShare({int fps = 10}) => send('screen_request', {'fps': fps});
  void sendCameraFrame(String b64)  => send('camera_frame', {'frame_base64': b64});

  void sendCommand(String cmd, Map<String, dynamic> params) =>
      send('command', {'cmd': cmd, ...params});

  void disconnect() {
    _channel?.sink.close();
    _isConnected = false;
    notifyListeners();
  }
}

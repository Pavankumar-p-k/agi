// lib/services/websocket_service.dart
import 'package:flutter/foundation.dart';
import 'dart:convert';
import 'dart:async';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../config/api_config.dart';

class WebSocketService extends ChangeNotifier {
  WebSocketChannel? _channel;
  bool _isConnected = false;
  final List<Map<String, dynamic>> _messageQueue = [];

  // Reconnect state
  Timer? _reconnectTimer;
  int _reconnectAttempts = 0;
  static const int _maxReconnectDelay = 30; // seconds
  static const Duration _initialDelay = Duration(seconds: 3);

  // Heartbeat state
  Timer? _heartbeatTimer;
  Timer? _pongTimeout;
  static const Duration _heartbeatInterval = Duration(seconds: 30);
  static const Duration _pongTimeoutDuration = Duration(seconds: 10);

  // Callbacks
  Function(Map)? onChatResponse;
  Function(Map)? onFaceResult;
  Function(String)? onScreenFrame;   // base64 JPEG
  Function(Map)? onCommandResponse;
  Function(Map)? onNotification;

  bool get isConnected => _isConnected;

  Future<void> connect() async {
    _reconnectAttempts = 0;
    await _doConnect();
  }

  Future<void> _doConnect({bool isReconnect = false}) async {
    try {
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
      _reconnectAttempts = 0;
      _startHeartbeat();
      notifyListeners();

      // Flush queued messages
      for (final msg in _messageQueue) {
        _send(msg);
      }
      _messageQueue.clear();

      debugPrint('[WS] Connected${isReconnect ? " (reconnected)" : ""} ✓');
    } catch (e) {
      debugPrint('[WS] Connection failed: $e');
      _scheduleReconnect();
    }
  }

  void _scheduleReconnect() {
    _reconnectTimer?.cancel();
    final delay = _initialDelay * (_reconnectAttempts + 1);
    final capped = delay.inSeconds > _maxReconnectDelay
        ? Duration(seconds: _maxReconnectDelay)
        : delay;
    _reconnectAttempts++;
    debugPrint('[WS] Reconnecting in ${capped.inSeconds}s (attempt $_reconnectAttempts)');
    _reconnectTimer = Timer(capped, () => _doConnect(isReconnect: true));
  }

  void _startHeartbeat() {
    _heartbeatTimer?.cancel();
    _heartbeatTimer = Timer.periodic(_heartbeatInterval, (_) {
      ping();
      _pongTimeout?.cancel();
      _pongTimeout = Timer(_pongTimeoutDuration, () {
        debugPrint('[WS] Pong timeout — reconnecting');
        _isConnected = false;
        _channel?.sink.close();
        _scheduleReconnect();
      });
    });
  }

  void _onMessage(dynamic raw) {
    try {
      final msg = jsonDecode(raw as String) as Map<String, dynamic>;
      final type = msg['type'] as String?;
      final payload = msg['payload'] as Map<String, dynamic>? ?? {};

      // Reset pong timeout on any message
      _pongTimeout?.cancel();

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
    _heartbeatTimer?.cancel();
    _pongTimeout?.cancel();
    notifyListeners();
    _scheduleReconnect();
  }

  void _onDone() {
    debugPrint('[WS] Disconnected');
    _isConnected = false;
    _heartbeatTimer?.cancel();
    _pongTimeout?.cancel();
    notifyListeners();
    _scheduleReconnect();
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
    _reconnectTimer?.cancel();
    _heartbeatTimer?.cancel();
    _pongTimeout?.cancel();
    _channel?.sink.close();
    _isConnected = false;
    notifyListeners();
  }

  @override
  void dispose() {
    disconnect();
    super.dispose();
  }
}

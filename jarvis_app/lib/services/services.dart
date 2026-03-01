import 'dart:convert';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../config/api_config.dart';

class AuthService extends ChangeNotifier {
  final FirebaseAuth _auth = FirebaseAuth.instance;
  User? _user;
  bool _localLoggedIn = false;
  String _localEmail = '';
  String _localDisplayName = 'User';

  AuthService() {
    _auth.authStateChanges().listen((user) {
      _user = user;
      if (user != null) {
        _localLoggedIn = false;
        _localEmail = '';
        _localDisplayName = user.displayName ?? user.email?.split('@').first ?? 'User';
      }
      notifyListeners();
    });
  }

  User? get user => _user;
  bool get isLoggedIn => _user != null || _localLoggedIn;
  String get displayName =>
      _user?.displayName ?? _user?.email?.split('@').first ?? _localDisplayName;
  String get email => _user?.email ?? _localEmail;

  Future<UserCredential?> signInWithEmail(String email, String password) async {
    try {
      return await _auth.signInWithEmailAndPassword(
        email: email,
        password: password,
      );
    } on FirebaseAuthException catch (e) {
      if (_canUseLocalFallback(e.code, e.message)) {
        signInOffline(email: email);
        return null;
      }
      throw _mapError(e.code, e.message);
    }
  }

  Future<UserCredential?> signUpWithEmail(
    String email,
    String password,
    String name,
  ) async {
    try {
      final cred = await _auth.createUserWithEmailAndPassword(
        email: email,
        password: password,
      );
      await cred.user?.updateDisplayName(name);
      return cred;
    } on FirebaseAuthException catch (e) {
      if (_canUseLocalFallback(e.code, e.message)) {
        signInOffline(email: email, name: name);
        return null;
      }
      throw _mapError(e.code, e.message);
    }
  }

  void signInOffline({required String email, String name = ''}) {
    _localLoggedIn = true;
    _localEmail = email.trim().isEmpty ? 'offline@local' : email.trim();
    _localDisplayName = name.trim().isNotEmpty
        ? name.trim()
        : _localEmail.split('@').first;
    notifyListeners();
  }

  Future<void> signOut() async {
    _localLoggedIn = false;
    _localEmail = '';
    _localDisplayName = 'User';
    await _auth.signOut();
    notifyListeners();
  }

  bool _canUseLocalFallback(String code, String? message) {
    final msg = (message ?? '').toLowerCase();
    if (msg.contains('configuration_not_found')) return true;
    return code == 'network-request-failed' ||
        code == 'invalid-api-key' ||
        code == 'internal-error' ||
        code == 'operation-not-allowed';
  }

  String _mapError(String code, [String? message]) {
    if ((message ?? '').contains('CONFIGURATION_NOT_FOUND')) {
      return 'Firebase Authentication is not initialized in console. Open Firebase -> Authentication -> Get started.';
    }
    switch (code) {
      case 'user-not-found':
        return 'No account found with this email.';
      case 'wrong-password':
        return 'Incorrect password.';
      case 'email-already-in-use':
        return 'Email already registered.';
      case 'weak-password':
        return 'Password must be at least 6 characters.';
      case 'invalid-email':
        return 'Invalid email format.';
      case 'invalid-credential':
        return 'Invalid email or password.';
      case 'operation-not-allowed':
        return 'Email/Password sign-in is not enabled in Firebase.';
      case 'network-request-failed':
        return 'Network error. Check your internet connection. You can also use offline mode.';
      case 'too-many-requests':
        return 'Too many attempts. Try again later.';
      case 'invalid-api-key':
        return 'Firebase API key is invalid or missing.';
      case 'internal-error':
        return 'Firebase auth setup is incomplete. Open Firebase -> Authentication -> Get started, then enable Email/Password. You can use offline mode now.';
      default:
        return 'Authentication failed ($code).';
    }
  }
}

class WebSocketService extends ChangeNotifier {
  WebSocketChannel? _channel;
  bool _isConnected = false;
  String? _activeUserUid;
  Future<void>? _connectFuture;
  final List<Map<String, dynamic>> _messageQueue = [];

  Function(Map)? onChatResponse;
  Function(Map)? onFaceResult;
  Function(String)? onScreenFrame;
  Function(Map)? onCommandResponse;
  Function(Map)? onNotification;

  bool get isConnected => _isConnected;

  Future<void> connect() async {
    final user = FirebaseAuth.instance.currentUser;
    if (user == null) {
      disconnect(clearQueue: true);
      return;
    }

    if (_isConnected && _activeUserUid == user.uid) {
      return;
    }

    if (_connectFuture != null) {
      await _connectFuture;
      return;
    }

    _connectFuture = _connectForUser(user.uid);
    await _connectFuture;
    _connectFuture = null;
  }

  Future<void> _connectForUser(String uid) async {
    if (_activeUserUid != null && _activeUserUid != uid) {
      disconnect(clearQueue: true);
    }

    final user = FirebaseAuth.instance.currentUser;
    if (user == null || user.uid != uid) {
      return;
    }

    final deviceId = 'android_${user.uid.substring(0, 8)}';
    final userId = user.uid.hashCode.abs();

    try {
      await _channel?.sink.close();
      _channel = WebSocketChannel.connect(
        Uri.parse('${ApiConfig.wsUrl}/$deviceId/$userId'),
      );

      _channel!.stream.listen(
        _onMessage,
        onError: _onError,
        onDone: _onDone,
      );

      _isConnected = true;
      _activeUserUid = user.uid;
      notifyListeners();

      for (final msg in _messageQueue) {
        _send(msg);
      }
      _messageQueue.clear();

      print('[WS] Connected');
    } catch (e) {
      print('[WS] Connection failed: $e');
    }
  }

  void _onMessage(dynamic raw) {
    try {
      final msg = jsonDecode(raw as String) as Map<String, dynamic>;
      final type = msg['type'] as String?;
      final payload = msg['payload'] as Map<String, dynamic>? ?? {};

      switch (type) {
        case 'chat_response':
          onChatResponse?.call(payload);
          break;
        case 'face_result':
          onFaceResult?.call(payload);
          break;
        case 'screen_frame':
          onScreenFrame?.call(payload['frame_base64'] as String? ?? '');
          break;
        case 'command_response':
          onCommandResponse?.call(payload);
          break;
        case 'notification':
          onNotification?.call(payload);
          break;
        case 'pong':
          print('[WS] Pong received');
          break;
        default:
          break;
      }
    } catch (e) {
      print('[WS] Parse error: $e');
    }
  }

  void _onError(Object error) {
    print('[WS] Error: $error');
    _isConnected = false;
    _activeUserUid = null;
    notifyListeners();
  }

  void _onDone() {
    print('[WS] Disconnected');
    _isConnected = false;
    _activeUserUid = null;
    notifyListeners();
  }

  void _send(Map<String, dynamic> data) {
    try {
      _channel?.sink.add(jsonEncode(data));
    } catch (e) {
      print('[WS] Send error: $e');
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

  void sendChat(String text) => send('chat', {'text': text});
  void ping() => send('ping', {});
  void requestScreenShare({int fps = 10}) => send('screen_request', {'fps': fps});
  void sendCameraFrame(String b64) => send('camera_frame', {'frame_base64': b64});

  void sendCommand(String cmd, Map<String, dynamic> params) {
    send('command', {'cmd': cmd, ...params});
  }

  void disconnect({bool clearQueue = false}) {
    final hadState = _channel != null || _isConnected || _activeUserUid != null;
    _channel?.sink.close();
    _channel = null;
    _isConnected = false;
    _activeUserUid = null;
    if (clearQueue) {
      _messageQueue.clear();
    }
    if (hadState || clearQueue) {
      notifyListeners();
    }
  }
}

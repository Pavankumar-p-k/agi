// lib/services/auth_service.dart
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'device_data_service.dart';

class AuthService extends ChangeNotifier {
  static const _sessionKey = 'local_session_active';
  static const _emailKey = 'local_profile_email';
  static const _nameKey = 'local_profile_name';
  static const _passwordKey = 'local_profile_password';

  final FlutterSecureStorage _secureStorage = const FlutterSecureStorage();

  String? _email;
  String? _displayName;
  bool _isLoggedIn = false;
  bool _syncedOnLogin = false;
  bool _ready = false;

  AuthService() {
    _restoreSession();
  }

  bool get isLoggedIn => _isLoggedIn;
  bool get ready => _ready;
  String get displayName => _displayName ?? _email?.split('@').first ?? 'User';
  String get email => _email ?? '';

  Future<void> signInWithEmail(String email, String password) async {
    final prefs = await SharedPreferences.getInstance();
    final savedEmail = prefs.getString(_emailKey);
    final savedPassword = await _secureStorage.read(key: _passwordKey);
    if (savedEmail == null || savedPassword == null) {
      throw StateError('Create a local profile first.');
    }
    if (savedEmail.trim().toLowerCase() != email.trim().toLowerCase()) {
      throw StateError('This email does not match the saved local profile.');
    }
    if (savedPassword != password) {
      throw StateError('Incorrect local profile password.');
    }
    _email = savedEmail;
    _displayName = prefs.getString(_nameKey) ?? savedEmail.split('@').first;
    _isLoggedIn = true;
    await prefs.setBool(_sessionKey, true);
    await _syncIfNeeded();
    notifyListeners();
  }

  Future<void> signUpWithEmail(String email, String password, String name) async {
    final normalizedEmail = email.trim().toLowerCase();
    if (normalizedEmail.isEmpty || !normalizedEmail.contains('@')) {
      throw StateError('Enter a valid email.');
    }
    if (password.length < 6) {
      throw StateError('Password must be at least 6 characters.');
    }

    final prefs = await SharedPreferences.getInstance();
    _email = normalizedEmail;
    _displayName = name.isNotEmpty ? name.trim() : normalizedEmail.split('@').first;
    _isLoggedIn = true;
    await prefs.setString(_emailKey, _email!);
    await prefs.setString(_nameKey, _displayName!);
    await _secureStorage.write(key: _passwordKey, value: password);
    await prefs.setBool(_sessionKey, true);
    await _syncIfNeeded();
    notifyListeners();
  }

  Future<void> signOut() async {
    final prefs = await SharedPreferences.getInstance();
    _isLoggedIn = false;
    _syncedOnLogin = false;
    await prefs.setBool(_sessionKey, false);
    notifyListeners();
  }

  Future<void> _syncIfNeeded() async {
    if (_syncedOnLogin) return;
    _syncedOnLogin = true;
    await DeviceDataService().syncAllToPcOnLogin();
  }

  Future<void> _restoreSession() async {
    final prefs = await SharedPreferences.getInstance();
    final active = prefs.getBool(_sessionKey) ?? false;
    if (active) {
      _email = prefs.getString(_emailKey);
      _displayName = prefs.getString(_nameKey);
      _isLoggedIn = _email != null && _email!.isNotEmpty;
    }
    _ready = true;
    notifyListeners();
  }
}

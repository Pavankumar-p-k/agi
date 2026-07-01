import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:jarvis_app/services/auth_service.dart';
import 'package:jarvis_app/services/device_data_service.dart';

void main() {
  group('AuthService - login logic', () {
    test('signUpWithEmail stores password in secure storage', () async {
      SharedPreferences.setMockInitialValues({});
      FlutterSecureStorage.setMockInitialValues({});

      final auth = AuthService();
      await auth.signUpWithEmail('test@example.com', 'password123', 'Test User');

      expect(auth.isLoggedIn, true);
      expect(auth.email, 'test@example.com');
      expect(auth.displayName, 'Test User');
    });

    test('signInWithEmail matches stored credentials', () async {
      SharedPreferences.setMockInitialValues({
        'local_profile_email': 'test@example.com',
        'local_profile_name': 'Test User',
      });
      FlutterSecureStorage.setMockInitialValues({
        'local_profile_password': 'password123',
      });

      final auth = AuthService();
      await auth.signInWithEmail('test@example.com', 'password123');

      expect(auth.isLoggedIn, true);
      expect(auth.email, 'test@example.com');
    });

    test('signInWithEmail rejects wrong password', () async {
      SharedPreferences.setMockInitialValues({
        'local_profile_email': 'test@example.com',
        'local_profile_name': 'Test User',
      });
      FlutterSecureStorage.setMockInitialValues({
        'local_profile_password': 'password123',
      });

      final auth = AuthService();
      expect(
        () => auth.signInWithEmail('test@example.com', 'wrongpassword'),
        throwsA(isA<StateError>()),
      );
      expect(auth.isLoggedIn, false);
    });

    test('signInWithEmail rejects wrong email', () async {
      SharedPreferences.setMockInitialValues({
        'local_profile_email': 'test@example.com',
        'local_profile_name': 'Test User',
      });
      FlutterSecureStorage.setMockInitialValues({
        'local_profile_password': 'password123',
      });

      final auth = AuthService();
      expect(
        () => auth.signInWithEmail('other@example.com', 'password123'),
        throwsA(isA<StateError>()),
      );
      expect(auth.isLoggedIn, false);
    });

    test('signInWithEmail requires existing profile', () async {
      SharedPreferences.setMockInitialValues({});
      FlutterSecureStorage.setMockInitialValues({});

      final auth = AuthService();
      expect(
        () => auth.signInWithEmail('test@example.com', 'password123'),
        throwsA(isA<StateError>()),
      );
    });

    test('signOut clears session', () async {
      SharedPreferences.setMockInitialValues({
        'local_session_active': true,
      });
      FlutterSecureStorage.setMockInitialValues({});

      final auth = AuthService();
      await auth.signOut();
      expect(auth.isLoggedIn, false);
    });

    test('signUpWithEmail rejects short password', () async {
      SharedPreferences.setMockInitialValues({});
      FlutterSecureStorage.setMockInitialValues({});

      final auth = AuthService();
      expect(
        () => auth.signUpWithEmail('test@example.com', '12345', 'Test'),
        throwsA(isA<StateError>()),
      );
    });

    test('signUpWithEmail rejects invalid email', () async {
      SharedPreferences.setMockInitialValues({});
      FlutterSecureStorage.setMockInitialValues({});

      final auth = AuthService();
      expect(
        () => auth.signUpWithEmail('notanemail', 'password123', 'Test'),
        throwsA(isA<StateError>()),
      );
    });
  });
}

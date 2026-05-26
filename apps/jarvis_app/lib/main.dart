// lib/main.dart
// COMPLETE REPLACEMENT — ModelDetector on startup, Call Guard REMOVED

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:jarvis_app/ai/model_detector.dart';
import 'package:jarvis_app/services/feature_settings.dart';
import 'package:jarvis_app/services/services.dart';
import 'package:jarvis_app/theme/app_theme.dart';
import 'package:jarvis_app/screens/home_screen.dart';
import 'package:jarvis_app/screens/login_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Init settings first — everything else reads from it
  await FeatureSettings.init();

  // Auto-detect local model in background — non-blocking
  ModelDetector.autoDetectAndSave().then((model) {
    if (model != null) {
      debugPrint('[JARVIS] Auto-detected model: $model');
    } else {
      debugPrint('[JARVIS] No local model found — Gemini fallback active');
    }
  });

  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => AuthService()),
        ChangeNotifierProvider(create: (_) => WebSocketService()),
        Provider(create: (_) => DeviceDataService()),
      ],
      child: const JarvisApp(),
    ),
  );
}

class JarvisApp extends StatelessWidget {
  const JarvisApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'JARVIS',
      debugShowCheckedModeBanner: false,
      theme:     AppTheme.light,
      darkTheme: AppTheme.dark,
      themeMode: ThemeMode.system,
      home: const _AuthGate(),
    );
  }
}

class _AuthGate extends StatelessWidget {
  const _AuthGate();

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthService>();

    if (!auth.ready) {
      return const Scaffold(
        body: Center(
          child: CircularProgressIndicator(color: JarvisColors.cyan),
        ),
      );
    }

    return auth.isLoggedIn ? const HomeScreen() : const LoginScreen();
  }
}

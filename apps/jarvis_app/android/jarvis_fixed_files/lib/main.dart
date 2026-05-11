// lib/main.dart
// COMPLETE REPLACEMENT — ModelDetector on startup, Call Guard REMOVED

import 'package:flutter/material.dart';
import 'package:jarvis_app/ai/model_detector.dart';
import 'package:jarvis_app/services/feature_settings.dart';
import 'package:jarvis_app/theme/app_theme.dart';
import 'package:jarvis_app/screens/home_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Init settings first — everything else reads from it
  await FeatureSettings.init();

  // Auto-detect local model in background — non-blocking
  // Finds Gemma 4 E2B on MLC Chat, Ollama, LM Studio, or llama.cpp
  ModelDetector.autoDetectAndSave().then((model) {
    if (model != null) {
      debugPrint('[JARVIS] Auto-detected model: $model');
    } else {
      debugPrint('[JARVIS] No local model found — Gemini fallback active');
    }
  });

  runApp(const JarvisApp());
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
      home: const HomeScreen(),
    );
  }
}

// lib/services/talkback_service.dart
//
// JARVIS TalkBack Service
// ─────────────────────────────────────────────────────────────────
// • Speech-to-Text  : speech_to_text package (on-device, offline-capable)
// • Text-to-Speech  : flutter_tts package (on-device, no internet needed)
// • Wake word       : listens for "jarvis" to auto-activate
// • Continuous mode : keeps listening after each response
// ─────────────────────────────────────────────────────────────────
//
// pubspec.yaml additions needed:
//   speech_to_text: ^6.6.0
//   flutter_tts: ^4.0.2
//   permission_handler: ^11.3.1   (already in your pubspec)

import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:speech_to_text/speech_to_text.dart';
import 'package:speech_to_text/speech_recognition_result.dart';
import 'package:speech_to_text/speech_recognition_error.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:shared_preferences/shared_preferences.dart';

// ── TalkBack State ──
enum TalkBackState {
  idle,        // Mic off, silent
  listening,   // Actively recording speech
  processing,  // Sending to AI, waiting for answer
  speaking,    // JARVIS is reading the response aloud
  error,       // Something went wrong
}

class TalkBackService extends ChangeNotifier {
  // ── Core engines ──
  final SpeechToText _stt  = SpeechToText();
  final FlutterTts   _tts  = FlutterTts();

  // ── State ──
  TalkBackState _state     = TalkBackState.idle;
  String        _transcript = '';      // live partial transcript
  String        _lastSpoken = '';      // last thing JARVIS said
  bool          _initialized = false;
  bool          _continuousMode = false;
  double        _volume    = 1.0;      // 0.0 – 1.0
  double        _speechRate = 0.5;     // 0.0 – 1.0
  double        _pitch     = 1.0;      // 0.5 – 2.0
  String        _language  = 'en-US';
  DateTime?     _listenStart;

  // ── Wake word ──
  bool   _wakeWordEnabled = false;
  static const List<String> _wakeWords = ['jarvis', 'hey jarvis', 'ok jarvis', 'hello jarvis'];

  // ── Callbacks ──
  /// Called when the user finishes speaking — pass text to your AI
  Function(String text)? onUserSpeech;
  /// Called when JARVIS starts/stops speaking
  Function(TalkBackState state)? onStateChange;

  // ── Getters ──
  TalkBackState get state        => _state;
  String        get transcript   => _transcript;
  String        get lastSpoken   => _lastSpoken;
  bool          get isListening  => _state == TalkBackState.listening;
  bool          get isSpeaking   => _state == TalkBackState.speaking;
  bool          get isIdle       => _state == TalkBackState.idle;
  bool          get continuousMode => _continuousMode;
  bool          get wakeWordEnabled => _wakeWordEnabled;
  bool          get initialized  => _initialized;
  double        get volume       => _volume;
  double        get speechRate   => _speechRate;
  double        get pitch        => _pitch;


  // ══════════════════════════════════════════
  //  INITIALIZATION
  // ══════════════════════════════════════════

  Future<bool> initialize() async {
    if (_initialized) return true;

    // ── Request microphone permission ──
    final micStatus = await Permission.microphone.request();
    if (!micStatus.isGranted) {
      _setState(TalkBackState.error);
      return false;
    }

    // ── Init STT ──
    final sttAvailable = await _stt.initialize(
      onError:  _onSttError,
      onStatus: _onSttStatus,
      debugLogging: false,
    );

    if (!sttAvailable) {
      debugPrint('[TalkBack] STT not available on this device');
      return false;
    }

    // ── Init TTS ──
    await _tts.setLanguage(_language);
    await _tts.setVolume(_volume);
    await _tts.setSpeechRate(_speechRate);
    await _tts.setPitch(_pitch);
    await _tts.awaitSpeakCompletion(true);

    // TTS completion callback
    _tts.setCompletionHandler(() {
      if (_continuousMode) {
        // Auto-start listening again after speaking
        Future.delayed(const Duration(milliseconds: 400), () {
          if (_continuousMode) startListening();
        });
      } else {
        _setState(TalkBackState.idle);
      }
    });

    _tts.setErrorHandler((msg) {
      debugPrint('[TalkBack] TTS Error: $msg');
      _setState(TalkBackState.idle);
    });

    _initialized = true;
    debugPrint('[TalkBack] Initialized ✓');
    return true;
  }


  // ══════════════════════════════════════════
  //  SPEECH-TO-TEXT
  // ══════════════════════════════════════════

  Future<void> startListening() async {
    if (!_initialized) {
      final ok = await initialize();
      if (!ok) return;
    }

    // Don't start if already listening or TTS is speaking
    if (_state == TalkBackState.listening || _state == TalkBackState.speaking) return;

    _transcript = '';
    _listenStart = DateTime.now();
    _setState(TalkBackState.listening);

    await _stt.listen(
      onResult: _onSttResult,
      listenFor: const Duration(seconds: 30),
      pauseFor: const Duration(seconds: 3),
      partialResults: true,
      localeId: _language,
      cancelOnError: false,
      listenMode: ListenMode.confirmation,
    );
  }

  Future<void> stopListening() async {
    if (_state != TalkBackState.listening) return;
    await _stt.stop();
    _recordVoiceUsage();
    // onSttResult will be called with the final result
  }

  Future<void> cancelListening() async {
    await _stt.cancel();
    _transcript = '';
    _recordVoiceUsage();
    _setState(TalkBackState.idle);
  }

  void _onSttResult(SpeechRecognitionResult result) {
    _transcript = result.recognizedWords;
    notifyListeners();

    if (result.finalResult && _transcript.trim().isNotEmpty) {
      final text = _transcript.trim();
      _transcript = '';
      _recordVoiceUsage();

      // Check for wake word in continuous mode
      if (_wakeWordEnabled) {
        final lower = text.toLowerCase();
        final hasWakeWord = _wakeWords.any((w) => lower.contains(w));
        if (!hasWakeWord) {
          // Not a command, keep listening
          if (_continuousMode) startListening();
          return;
        }
        // Strip the wake word before sending
        final cleaned = _stripWakeWord(text);
        if (cleaned.trim().isEmpty) {
          speak("Yes? How can I help?");
          return;
        }
        _setState(TalkBackState.processing);
        onUserSpeech?.call(cleaned.trim());
      } else {
        _setState(TalkBackState.processing);
        onUserSpeech?.call(text);
      }
    }
  }

  void _onSttError(SpeechRecognitionError error) {
    debugPrint('[TalkBack] STT Error: ${error.errorMsg}');
    _recordVoiceUsage();
    if (error.errorMsg == 'error_no_match' || error.errorMsg == 'error_speech_timeout') {
      if (_continuousMode) {
        Future.delayed(const Duration(milliseconds: 500), startListening);
      } else {
        _setState(TalkBackState.idle);
      }
    } else {
      _setState(TalkBackState.error);
    }
  }

  void _onSttStatus(String status) {
    debugPrint('[TalkBack] STT Status: $status');
    if (status == 'done' && _state == TalkBackState.listening) {
      if (_transcript.isEmpty && _continuousMode) {
        Future.delayed(const Duration(milliseconds: 300), startListening);
      }
    }
  }

  String _stripWakeWord(String text) {
    String result = text.toLowerCase();
    for (final w in _wakeWords) {
      result = result.replaceFirst(w, '');
    }
    return result.trim();
  }


  // ══════════════════════════════════════════
  //  TEXT-TO-SPEECH
  // ══════════════════════════════════════════

  Future<void> speak(String text) async {
    if (!_initialized) await initialize();
    if (text.trim().isEmpty) return;

    // Stop any ongoing listening
    if (_state == TalkBackState.listening) {
      await _stt.stop();
    }

    _lastSpoken = text;
    _setState(TalkBackState.speaking);

    await _tts.speak(text);
    // Completion is handled by _tts.setCompletionHandler above
  }

  Future<void> stopSpeaking() async {
    await _tts.stop();
    _setState(TalkBackState.idle);
  }

  /// Call this when the AI returns a response
  Future<void> respondWithSpeech(String text) async {
    _setState(TalkBackState.processing);
    await Future.delayed(const Duration(milliseconds: 100));
    await speak(text);
  }

  Future<Map<String, dynamic>> getVoiceUsage() async {
    final prefs = await SharedPreferences.getInstance();
    final sessions = prefs.getInt('voice_usage_sessions') ?? 0;
    final ms = prefs.getInt('voice_usage_ms') ?? 0;
    return {'sessions': sessions, 'total_ms': ms};
  }


  // ══════════════════════════════════════════
  //  CONTINUOUS / WAKE WORD MODE
  // ══════════════════════════════════════════

  Future<void> startContinuousMode() async {
    _continuousMode = true;
    notifyListeners();
    await speak("Continuous mode activated. I'm always listening.");
  }

  Future<void> stopContinuousMode() async {
    _continuousMode = false;
    await cancelListening();
    await stopSpeaking();
    notifyListeners();
  }

  void setWakeWordEnabled(bool enabled) {
    _wakeWordEnabled = enabled;
    notifyListeners();
  }


  // ══════════════════════════════════════════
  //  SETTINGS
  // ══════════════════════════════════════════

  Future<void> setVolume(double v) async {
    _volume = v.clamp(0.0, 1.0);
    await _tts.setVolume(_volume);
    notifyListeners();
  }

  Future<void> setSpeechRate(double r) async {
    _speechRate = r.clamp(0.1, 1.0);
    await _tts.setSpeechRate(_speechRate);
    notifyListeners();
  }

  Future<void> setPitch(double p) async {
    _pitch = p.clamp(0.5, 2.0);
    await _tts.setPitch(_pitch);
    notifyListeners();
  }

  Future<List<dynamic>> getAvailableVoices() async {
    return await _tts.getVoices ?? [];
  }

  Future<void> setVoice(Map<String, String> voice) async {
    await _tts.setVoice(voice);
  }

  Future<List<dynamic>> getAvailableLanguages() async {
    return await _tts.getLanguages ?? [];
  }

  Future<void> setLanguage(String lang) async {
    _language = lang;
    await _tts.setLanguage(lang);
    notifyListeners();
  }


  // ══════════════════════════════════════════
  //  HELPERS
  // ══════════════════════════════════════════

  void _setState(TalkBackState newState) {
    _state = newState;
    onStateChange?.call(newState);
    notifyListeners();
  }

  void _recordVoiceUsage() {
    final start = _listenStart;
    if (start == null) return;
    _listenStart = null;
    final elapsed = DateTime.now().difference(start).inMilliseconds;
    SharedPreferences.getInstance().then((prefs) {
      final sessions = prefs.getInt('voice_usage_sessions') ?? 0;
      final ms = prefs.getInt('voice_usage_ms') ?? 0;
      prefs.setInt('voice_usage_sessions', sessions + 1);
      prefs.setInt('voice_usage_ms', ms + elapsed);
    });
  }

  /// Quick test
  Future<void> testVoice() async {
    await speak("Hello! I am JARVIS, your personal AI assistant. TalkBack is working correctly.");
  }

  @override
  void dispose() {
    _stt.cancel();
    _tts.stop();
    super.dispose();
  }
}

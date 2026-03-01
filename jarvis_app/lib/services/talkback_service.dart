import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:speech_to_text/speech_recognition_error.dart';
import 'package:speech_to_text/speech_recognition_result.dart';
import 'package:speech_to_text/speech_to_text.dart';

enum TalkBackState {
  idle,
  listening,
  processing,
  speaking,
  error,
}

class TalkBackService extends ChangeNotifier {
  final SpeechToText _stt = SpeechToText();
  final FlutterTts _tts = FlutterTts();
  static const MethodChannel _native =
      MethodChannel('com.jarvis.app/call_service');

  static const List<String> _wakeWords = <String>[
    'jarvis',
    'hey jarvis',
    'ok jarvis',
    'hello jarvis',
  ];

  static const List<String> _maleVoiceHints = <String>[
    'male',
    'man',
    'm1',
    'm2',
    'iob',
    'ioc',
    'iod',
    'iol',
    'iom',
    'en-us-x-iob',
    'en-us-x-ioc',
    'en-us-x-iod',
  ];

  static const List<String> _femaleVoiceHints = <String>[
    'female',
    'woman',
    'f1',
    'f2',
    'ioa',
    'iof',
    'iog',
    'ioh',
    'ioj',
    'iok',
  ];

  TalkBackState _state = TalkBackState.idle;
  String _transcript = '';
  String _lastSpoken = '';
  bool _initialized = false;
  bool _wakeWordEnabled = false;

  double _volume = 1.0;
  double _speechRate = 0.45;
  double _pitch = 0.68;
  String _language = 'en-US';
  Map<String, String>? _lockedMaleVoice;

  Function(String text)? onUserSpeech;
  Function(TalkBackState state)? onStateChange;

  TalkBackState get state => _state;
  String get transcript => _transcript;
  String get lastSpoken => _lastSpoken;
  bool get isListening => _state == TalkBackState.listening;
  bool get isSpeaking => _state == TalkBackState.speaking;
  bool get isIdle => _state == TalkBackState.idle;
  bool get continuousMode => false;
  bool get wakeWordEnabled => _wakeWordEnabled;
  bool get initialized => _initialized;
  double get volume => _volume;
  double get speechRate => _speechRate;
  double get pitch => _pitch;

  Future<bool> initialize() async {
    if (_initialized) return true;

    final micStatus = await Permission.microphone.request();
    if (!micStatus.isGranted) {
      _setState(TalkBackState.error);
      return false;
    }

    final sttAvailable = await _stt.initialize(
      onError: _onSttError,
      onStatus: _onSttStatus,
      debugLogging: false,
    );

    if (!sttAvailable) {
      debugPrint('[TalkBack] STT not available on this device');
      return false;
    }

    await _tts.setLanguage(_language);
    await _tts.setVolume(_volume);
    await _tts.setSpeechRate(_speechRate);
    await _tts.setPitch(_pitch);
    await _tts.awaitSpeakCompletion(true);
    await _applyMaleVoiceLock();

    _tts.setCompletionHandler(() {
      _setState(TalkBackState.idle);
    });

    _tts.setErrorHandler((msg) {
      debugPrint('[TalkBack] TTS Error: $msg');
      _setState(TalkBackState.idle);
    });

    _initialized = true;
    return true;
  }

  Future<void> startListening() async {
    if (!_initialized) {
      final ok = await initialize();
      if (!ok) return;
    }

    if (_state == TalkBackState.listening || _state == TalkBackState.speaking) {
      return;
    }

    _transcript = '';
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
  }

  Future<void> cancelListening() async {
    await _stt.cancel();
    _transcript = '';
    _setState(TalkBackState.idle);
  }

  void _onSttResult(SpeechRecognitionResult result) {
    _transcript = result.recognizedWords;
    notifyListeners();

    if (!result.finalResult || _transcript.trim().isEmpty) {
      return;
    }

    final text = _transcript.trim();
    _transcript = '';

    if (_wakeWordEnabled) {
      final lower = text.toLowerCase();
      final hasWakeWord = _wakeWords.any(lower.contains);
      if (!hasWakeWord) {
        return;
      }

      final cleaned = _stripWakeWord(text);
      if (cleaned.trim().isEmpty) {
        speak('Yes? How can I help?');
        return;
      }

      _setState(TalkBackState.processing);
      onUserSpeech?.call(cleaned.trim());
      return;
    }

    _setState(TalkBackState.processing);
    onUserSpeech?.call(text);
  }

  void _onSttError(SpeechRecognitionError error) {
    debugPrint('[TalkBack] STT Error: ${error.errorMsg}');
    if (error.errorMsg == 'error_no_match' ||
        error.errorMsg == 'error_speech_timeout') {
      _setState(TalkBackState.idle);
      return;
    }
    _setState(TalkBackState.error);
  }

  void _onSttStatus(String status) {
    if (status == 'done' && _state == TalkBackState.listening && _transcript.isEmpty) {
      _setState(TalkBackState.idle);
    }
  }

  String _stripWakeWord(String text) {
    var result = text.toLowerCase();
    for (final wakeWord in _wakeWords) {
      result = result.replaceFirst(wakeWord, '');
    }
    return result.trim();
  }

  Future<void> speak(String text) async {
    if (!_initialized) {
      final ok = await initialize();
      if (!ok) return;
    }

    if (text.trim().isEmpty) return;

    if (_state == TalkBackState.listening) {
      await _stt.stop();
    }

    _lastSpoken = text;
    _setState(TalkBackState.speaking);

    final usedNative = await _speakNativeMale(text);
    if (usedNative) {
      _setState(TalkBackState.idle);
      return;
    }

    await _applyMaleVoiceLock();
    await _tts.speak(text);
  }

  Future<void> stopSpeaking() async {
    await _stopNativeMale();
    await _tts.stop();
    _setState(TalkBackState.idle);
  }

  Future<void> respondWithSpeech(String text) async {
    _setState(TalkBackState.processing);
    await Future.delayed(const Duration(milliseconds: 100));
    await speak(text);
  }

  Future<void> startContinuousMode() async {
    await speak('Always-on listening is disabled. Tap the microphone to speak.');
  }

  Future<void> stopContinuousMode() async {
    await cancelListening();
    await stopSpeaking();
    notifyListeners();
  }

  void setWakeWordEnabled(bool enabled) {
    _wakeWordEnabled = enabled;
    notifyListeners();
  }

  Future<void> setVolume(double v) async {
    _volume = v.clamp(0.0, 1.0);
    await _tts.setVolume(_volume);
    notifyListeners();
  }

  Future<void> setSpeechRate(double r) async {
    _speechRate = r.clamp(0.25, 0.8);
    await _tts.setSpeechRate(_speechRate);
    notifyListeners();
  }

  Future<void> setPitch(double p) async {
    _pitch = 0.68;
    await _tts.setPitch(_pitch);
    notifyListeners();
  }

  Future<List<dynamic>> getAvailableVoices() async {
    return await _tts.getVoices ?? <dynamic>[];
  }

  Future<void> setVoice(Map<String, String> voice) async {
    await _applyMaleVoiceLock();
  }

  Future<List<dynamic>> getAvailableLanguages() async {
    return await _tts.getLanguages ?? <dynamic>[];
  }

  Future<void> setLanguage(String lang) async {
    _language = lang;
    await _tts.setLanguage(lang);
    await _applyMaleVoiceLock();
    notifyListeners();
  }

  Future<void> testVoice() async {
    await speak(
      'Hello! I am JARVIS, your personal AI assistant. TalkBack is working correctly.',
    );
  }

  Future<void> _applyMaleVoiceLock() async {
    try {
      final voices = await _tts.getVoices;
      final bestMale = _pickBestMaleVoice(voices);
      if (bestMale != null) {
        _lockedMaleVoice = bestMale;
      }
      if (_lockedMaleVoice != null) {
        await _tts.setVoice(_lockedMaleVoice!);
      }
    } catch (_) {
      // Device may not expose voice list.
    }

    await _tts.setPitch(_pitch);
    await _tts.setSpeechRate(_speechRate);
  }

  Future<bool> _speakNativeMale(String text) async {
    if (kIsWeb || defaultTargetPlatform != TargetPlatform.android) {
      return false;
    }
    try {
      final ok = await _native
          .invokeMethod<bool>('speakMaleNative', {
            'text': text,
          })
          .timeout(const Duration(seconds: 20));
      return ok == true;
    } catch (_) {
      return false;
    }
  }

  Future<void> _stopNativeMale() async {
    if (kIsWeb || defaultTargetPlatform != TargetPlatform.android) {
      return;
    }
    try {
      await _native.invokeMethod('stopMaleNative');
    } catch (_) {}
  }

  Map<String, String>? _pickBestMaleVoice(dynamic voices) {
    if (voices is! List || voices.isEmpty) {
      return null;
    }

    Map<String, String>? best;
    var bestScore = -1 << 30;

    for (final item in voices) {
      if (item is! Map) continue;
      final voice = Map<String, dynamic>.from(item);
      final name = (voice['name'] ?? '').toString();
      final locale = (voice['locale'] ?? '').toString();
      if (name.isEmpty || locale.isEmpty) continue;

      final lowerName = name.toLowerCase();
      final lowerLocale = locale.toLowerCase();
      if (!lowerLocale.startsWith('en')) continue;

      var score = 0;
      if (lowerLocale.contains('en-us')) score += 20;
      final networkRequired = voice['network_required'];
      if (networkRequired == false || networkRequired.toString() == 'false') {
        score += 10;
      }

      for (final hint in _maleVoiceHints) {
        if (lowerName.contains(hint)) {
          score += 30;
          break;
        }
      }

      for (final hint in _femaleVoiceHints) {
        if (lowerName.contains(hint)) {
          score -= 30;
          break;
        }
      }

      if (score > bestScore) {
        bestScore = score;
        best = <String, String>{'name': name, 'locale': locale};
      }
    }

    return best;
  }

  void _setState(TalkBackState newState) {
    _state = newState;
    onStateChange?.call(newState);
    notifyListeners();
  }

  @override
  void dispose() {
    _stt.cancel();
    _tts.stop();
    super.dispose();
  }
}

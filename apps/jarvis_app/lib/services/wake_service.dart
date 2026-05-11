// lib/services/wake_service.dart
//
// Flutter-side bridge to the Android foreground service.
// Talks to JarvisWakeService.java via MethodChannel + EventChannel.

import 'dart:async';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:permission_handler/permission_handler.dart';

class WakeService extends ChangeNotifier {
  static const _method = MethodChannel('com.example.jarvis_app/wake_service');
  static const _events = EventChannel('com.example.jarvis_app/wake_events');

  bool   _serviceRunning = false;
  bool   _batteryExempt  = false;
  int    _wakeCount      = 0;
  DateTime? _lastWakeTime;

  StreamSubscription? _eventSub;

  // Callbacks
  VoidCallback? onWakeDetected;

  // ── Getters ──
  bool     get serviceRunning => _serviceRunning;
  bool     get batteryExempt  => _batteryExempt;
  int      get wakeCount      => _wakeCount;
  DateTime? get lastWakeTime  => _lastWakeTime;


  // ══════════════════════════════════════════
  //  INITIALIZE
  // ══════════════════════════════════════════

  Future<void> initialize() async {
    // Listen for wake word events from native side
    _eventSub = _events.receiveBroadcastStream().listen(_onNativeEvent);

    // Check current state
    _serviceRunning = await isRunning();
    _batteryExempt  = await isBatteryExempt();
    notifyListeners();
  }

  void _onNativeEvent(dynamic event) {
    if (event == 'wake_word_detected') {
      _wakeCount++;
      _lastWakeTime = DateTime.now();
      notifyListeners();
      onWakeDetected?.call();
      debugPrint('[WakeService] Wake word detected! Count: $_wakeCount');
    }
  }


  // ══════════════════════════════════════════
  //  SERVICE CONTROL
  // ══════════════════════════════════════════

  Future<void> start() async {
    if (!Platform.isAndroid) return;

    // Ensure microphone permission is granted before starting the wake service.
    final micStatus = await Permission.microphone.status;
    if (!micStatus.isGranted) {
      final requested = await Permission.microphone.request();
      if (!requested.isGranted) {
        debugPrint('[WakeService] Microphone permission denied; cannot start wake service.');
        return;
      }
    }

    try {
      await _method.invokeMethod('startWakeService');
      _serviceRunning = true;
      notifyListeners();
      debugPrint('[WakeService] Service started ✓');
    } on PlatformException catch (e) {
      debugPrint('[WakeService] Start failed: ${e.message}');
    }
  }

  Future<void> stop() async {
    try {
      await _method.invokeMethod('stopWakeService');
      _serviceRunning = false;
      notifyListeners();
      debugPrint('[WakeService] Service stopped');
    } on PlatformException catch (e) {
      debugPrint('[WakeService] Stop failed: ${e.message}');
    }
  }

  Future<bool> isRunning() async {
    try {
      return await _method.invokeMethod<bool>('isServiceRunning') ?? false;
    } catch (_) {
      return false;
    }
  }


  // ══════════════════════════════════════════
  //  BATTERY OPTIMIZATION
  // ══════════════════════════════════════════

  Future<bool> isBatteryExempt() async {
    try {
      return await _method.invokeMethod<bool>('isBatteryOptimizationExempt') ?? false;
    } catch (_) {
      return false;
    }
  }

  Future<void> requestBatteryExemption() async {
    try {
      await _method.invokeMethod('requestBatteryOptimizationExempt');
      _batteryExempt = await isBatteryExempt();
      notifyListeners();
    } catch (e) {
      debugPrint('[WakeService] Battery exemption request failed: $e');
    }
  }

  Future<void> openBatterySettings() async {
    try {
      await _method.invokeMethod('openBatterySettings');
    } catch (e) {
      debugPrint('[WakeService] Open battery settings failed: $e');
    }
  }

  @override
  void dispose() {
    _eventSub?.cancel();
    super.dispose();
  }
}

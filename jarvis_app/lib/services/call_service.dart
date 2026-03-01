import 'dart:async';

import 'package:flutter/services.dart';

class CallRecord {
  final int id;
  final String callerName;
  final String platform;
  final String transcript;
  final String audioPath;
  final int timestamp;
  final bool isImportant;
  final bool isRead;

  const CallRecord({
    required this.id,
    required this.callerName,
    required this.platform,
    required this.transcript,
    required this.audioPath,
    required this.timestamp,
    required this.isImportant,
    required this.isRead,
  });

  factory CallRecord.fromMap(Map<dynamic, dynamic> map) {
    return CallRecord(
      id: (map['id'] as num?)?.toInt() ?? 0,
      callerName: (map['caller_name'] ?? 'Unknown').toString(),
      platform: (map['platform'] ?? 'SIM').toString(),
      transcript: (map['transcript'] ?? '').toString(),
      audioPath: (map['audio_path'] ?? '').toString(),
      timestamp: (map['timestamp'] as num?)?.toInt() ?? 0,
      isImportant: map['is_important'] == true || map['is_important'] == 1,
      isRead: map['is_read'] == true || map['is_read'] == 1,
    );
  }

  DateTime get time => DateTime.fromMillisecondsSinceEpoch(timestamp);
}

class CallService {
  static const MethodChannel _method =
      MethodChannel('com.jarvis.app/call_service');
  static const EventChannel _events =
      EventChannel('com.jarvis.app/call_events');

  Stream<Map<dynamic, dynamic>> recordsStream() {
    return _events.receiveBroadcastStream().map((event) {
      if (event is Map<dynamic, dynamic>) {
        return event;
      }
      return <dynamic, dynamic>{};
    });
  }

  Future<void> startService() async {
    await _method.invokeMethod('startCallService');
  }

  Future<void> stopService() async {
    await _method.invokeMethod('stopCallService');
  }

  Future<bool> isRunning() async {
    final value = await _method.invokeMethod<bool>('isCallServiceRunning');
    return value ?? false;
  }

  Future<List<CallRecord>> getAllRecords() async {
    final raw = await _method.invokeMethod<List<dynamic>>('getAllCallRecords');
    return (raw ?? const <dynamic>[])
        .map(
            (row) => CallRecord.fromMap(Map<dynamic, dynamic>.from(row as Map)))
        .toList();
  }

  Future<List<CallRecord>> getImportantRecords() async {
    final raw =
        await _method.invokeMethod<List<dynamic>>('getImportantCallRecords');
    return (raw ?? const <dynamic>[])
        .map(
            (row) => CallRecord.fromMap(Map<dynamic, dynamic>.from(row as Map)))
        .toList();
  }

  Future<void> markRead(int id) async {
    await _method.invokeMethod('markCallRead', {'id': id});
  }

  Future<void> deleteRecord(int id) async {
    await _method.invokeMethod('deleteCallRecord', {'id': id});
  }

  Future<void> setCustomMessage(String message) async {
    await _method.invokeMethod('setCustomMessage', {'message': message});
  }

  Future<void> setAnswerDelayMs(int delayMs) async {
    await _method.invokeMethod('setAnswerDelay', {'delay_ms': delayMs});
  }

  Future<void> setPcIp(String ip) async {
    await _method.invokeMethod('setPcIp', {'ip': ip});
  }

  Future<void> setVoiceGender(String gender) async {
    await _method.invokeMethod('setCallVoiceGender', {'gender': 'male'});
  }

  Future<void> setAutoStart(bool enabled) async {
    await _method.invokeMethod('setCallAutostart', {'enabled': enabled});
  }

  Future<String> getVoiceGender() async {
    return 'male';
  }

  Future<bool> getAutoStart() async {
    final value = await _method.invokeMethod<bool>('getCallAutostart');
    return value ?? false;
  }

  Future<String> getCustomMessage() async {
    final value = await _method.invokeMethod<String>('getCustomMessage');
    return value ?? '';
  }

  Future<int> getAnswerDelayMs() async {
    final value = await _method.invokeMethod<int>('getAnswerDelay');
    return value ?? 4000;
  }

  Future<String> getPcIp() async {
    final value = await _method.invokeMethod<String>('getPcIp');
    return value ?? '192.168.1.100';
  }

  Future<void> openAccessibilitySettings() async {
    await _method.invokeMethod('openAccessibilitySettings');
  }

  Future<void> openNotificationAccessSettings() async {
    await _method.invokeMethod('openNotificationAccessSettings');
  }

  Future<void> openAppPermissionSettings() async {
    await _method.invokeMethod('openAppPermissionSettings');
  }

  Future<bool> isAccessibilityServiceEnabled() async {
    final value =
        await _method.invokeMethod<bool>('isAccessibilityServiceEnabled');
    return value ?? false;
  }

  Future<bool> isNotificationAccessEnabled() async {
    final value =
        await _method.invokeMethod<bool>('isNotificationAccessEnabled');
    return value ?? false;
  }
}

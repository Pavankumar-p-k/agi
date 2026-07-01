// lib/services/device_data_service.dart
//
// Android device data bridge (contacts, call logs, SMS, usage stats, dialer)

import 'dart:io';
import 'package:flutter/services.dart';
import 'package:permission_handler/permission_handler.dart';

class DeviceDataService {
  static const MethodChannel _ch =
      MethodChannel('com.example.jarvis_app/device_data');

  Future<List<Map<String, dynamic>>> getContacts({int limit = 500}) async {
    final List<dynamic>? res =
        await _ch.invokeMethod('getContacts', {'limit': limit});
    return res?.map((e) => Map<String, dynamic>.from(e)).toList() ?? [];
  }

  Future<List<Map<String, dynamic>>> getCallLogs({int limit = 200}) async {
    final List<dynamic>? res =
        await _ch.invokeMethod('getCallLogs', {'limit': limit});
    return res?.map((e) => Map<String, dynamic>.from(e)).toList() ?? [];
  }

  Future<List<Map<String, dynamic>>> getSmsLogs({int limit = 200}) async {
    final List<dynamic>? res =
        await _ch.invokeMethod('getSmsLogs', {'limit': limit});
    return res?.map((e) => Map<String, dynamic>.from(e)).toList() ?? [];
  }

  Future<Map<String, dynamic>> getUsageSummary({int days = 1}) async {
    final Map<dynamic, dynamic>? res =
        await _ch.invokeMethod('getUsageSummary', {'days': days});
    return res != null ? Map<String, dynamic>.from(res) : {};
  }

  Future<Map<String, dynamic>> getCallStats({int days = 1}) async {
    final Map<dynamic, dynamic>? res =
        await _ch.invokeMethod('getCallStats', {'days': days});
    return res != null ? Map<String, dynamic>.from(res) : {};
  }

  Future<void> openDialer(String number) async {
    await _ch.invokeMethod('openDialer', {'number': number});
  }

  Future<void> placeCall(String number) async {
    await _ch.invokeMethod('placeCall', {'number': number});
  }

  Future<void> requestDialerRole() async {
    await _ch.invokeMethod('requestDialerRole');
  }

  Future<void> openUsageAccessSettings() async {
    await _ch.invokeMethod('openUsageAccessSettings');
  }

  Future<void> syncAllToPc({int limit = 200}) async {
    await _ch.invokeMethod('syncAllToPc', {'limit': limit});
  }

  Future<void> setPcIp(String ip) async {
    await _ch.invokeMethod('setPcIp', {'ip': ip});
  }

  Future<void> syncAllToPcOnLogin({int limit = 200}) async {
    if (!Platform.isAndroid) return;
    await _requestCorePermissions();
    await syncAllToPc(limit: limit);
  }

  Future<void> _requestCorePermissions() async {
    await [
      Permission.contacts,
      Permission.phone,
      Permission.sms,
    ].request();
  }
}

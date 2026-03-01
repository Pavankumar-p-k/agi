import 'package:flutter/foundation.dart';

class ApiConfig {
  // Replace with your PC IP when running from a physical phone/tablet.
  static const String pcIp = '10.122.223.124';
  static const int port = 8000;

  static String get _host {
    if (kIsWeb) {
      return '127.0.0.1';
    }

    switch (defaultTargetPlatform) {
      case TargetPlatform.android:
      case TargetPlatform.iOS:
        return pcIp;
      case TargetPlatform.windows:
      case TargetPlatform.linux:
      case TargetPlatform.macOS:
      case TargetPlatform.fuchsia:
        return '127.0.0.1';
    }
  }

  static String get baseUrl => 'http://$_host:$port';
  static String get wsUrl => 'ws://$_host:$port/ws';

  static const String health = '/health';

  static const String chat = '/api/chat';
  static const String chatHistory = '/api/chat/history';

  static const String reminders = '/api/reminders';
  static const String tasksComplete = '/api/tasks/complete';
  static const String notes = '/api/notes';

  static const String activity = '/api/activity/today';
  static const String summary = '/api/activity/summary';

  static const String messageSend = '/api/message/send';

  static const String facesList = '/api/faces';
  static const String facesIdentify = '/api/faces/identify';
  static const String facesRegister = '/api/faces/register';

  static const String mediaStatus = '/api/media/status';
  static const String mediaPlay = '/api/media/play';
  static const String mediaPause = '/api/media/pause';
  static const String mediaNext = '/api/media/next';
  static const String mediaVolume = '/api/media/volume';
  static const String mediaPlaylist = '/api/media/playlist';
  static const String musicSuggest = '/api/media/suggest';

  static const String files = '/api/files';
}

// lib/config/api_config.dart
class ApiConfig {
  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://127.0.0.1:8000',
  );

  static const String wsUrl = String.fromEnvironment(
    'WS_URL',
    defaultValue: 'ws://127.0.0.1:8000/ws',
  );

  static const String health = '/health';
  static const String chat = '/api/chat';
  static const String chatHistory = '/api/chat/history';

  static const String reminders = '/api/reminders';
  static const String notes = '/api/notes';
  static const String activity = '/api/activity/today';
  static const String summary = '/api/activity/summary';

  static const String messageSend = '/api/message/send';

  static const String facesIdentify = '/api/faces/identify';
  static const String facesRegister = '/api/faces/register';
  static const String facesList = '/api/faces';

  static const String mediaStatus = '/api/media/status';
  static const String mediaPlay = '/api/media/play';
  static const String mediaPause = '/api/media/pause';
  static const String mediaNext = '/api/media/next';
  static const String mediaVolume = '/api/media/volume';
  static const String mediaPlaylist = '/api/media/playlist';
  static const String musicSuggest = '/api/media/suggest';

  static const String files = '/api/files';

// Automation
  static const String automationCommand = '/api/automation/command';

  // Voice
  static const String stt = '/stt';
  static const String tts = '/tts';
}

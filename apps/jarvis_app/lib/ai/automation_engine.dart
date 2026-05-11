// lib/ai/automation_engine.dart
// ═══════════════════════════════════════════════════════════════════
//  JARVIS AUTOMATION ENGINE — Local Task Execution
//  Executes commands WITHOUT server:
//   • Open apps (WhatsApp, Instagram, Telegram, etc.)
//   • Type messages
//   • Search web
//   • Send messages via accessibility/ADB
//   • Take screenshots
//   • Read clipboard
//   • Control device
//  Works 100% offline on device. No PC needed.
// ═══════════════════════════════════════════════════════════════════

import 'package:flutter/services.dart';

enum TaskType {
  openApp,      // "open whatsapp" / "launch instagram"
  sendMessage,  // "send msg to john"
  search,       // "search playstore for game"
  type,         // "type hello world"
  click,        // "click button"
  screenshot,   // "take screenshot"
  readClipboard,
  writeClipboard,
  openUrl,      // "open youtube.com"
  setAlarm,     // "alarm 8am"
  playMusic,    // "play song"
  callPerson,   // "call mom"
  sms,          // "sms dad hi"
  openSettings, // "open wifi settings"
  toggleWifi,
  toggleBluetooth,
  custom,       // Fallback
}

class AutomationTask {
  final TaskType type;
  final String command;      // original user input
  final String description;  // parsed description
  final Map<String, dynamic> params;  // extracted params
  final int priority;        // 1-10
  final bool requiredConfirm; // needs user approval?

  AutomationTask({
    required this.type,
    required this.command,
    required this.description,
    this.params = const {},
    this.priority = 5,
    this.requiredConfirm = false,
  });
}

class AutomationResult {
  final bool success;
  final String message;
  final dynamic output;
  final Duration executionTime;

  AutomationResult({
    required this.success,
    required this.message,
    this.output,
    this.executionTime = const Duration(milliseconds: 0),
  });
}

class AutomationEngine {
  static const _platform = MethodChannel('com.example.jarvis_app/automation');
  static const _accessibilityChannel = MethodChannel('com.example.jarvis_app/accessibility');

  // App package mappings
  static const Map<String, String> APP_PACKAGES = {
    'whatsapp': 'com.whatsapp',
    'instagram': 'com.instagram.android',
    'telegram': 'org.telegram.messenger',
    'messenger': 'com.facebook.orca',
    'sms': 'com.google.android.apps.messaging',
    'twitter': 'com.twitter.android',
    'linkedin': 'com.linkedin.android',
    'snapchat': 'com.snapchat.android',
    'viber': 'com.viber.voip',
    'signal': 'org.thoughtcrime.securesms',
    'discord': 'com.discord',
    'slack': 'com.Slack',
    'email': 'com.google.android.gm',
    'gmail': 'com.google.android.gm',
    'youtube': 'com.google.android.youtube',
    'maps': 'com.google.android.apps.maps',
    'chrome': 'com.android.chrome',
    'firefox': 'org.mozilla.firefox',
    'playstore': 'com.android.vending',
    'settings': 'com.android.settings',
    'contacts': 'com.android.contacts',
    'gallery': 'com.google.android.apps.photos',
    'camera': 'com.android.camera2',
    'spotify': 'com.spotify.music',
    'vlc': 'org.videolan.vlc',
    'netflix': 'com.netflix.mediaclient',
    'amazon': 'com.amazon.venezia',
    'ebay': 'com.ebay.mobile',
    'uber': 'com.ubercab',
    'ola': 'com.olacabs.customer',
    'swiggy': 'com.swiggy.android',
    'zomato': 'com.application.zomatoapp',
    'medium': 'com.medium.reader',
    'reddit': 'com.reddit.frontpage',
  };

  // ── Parse user command into task ───────────────────────────

  static TaskType parseCommand(String input) {
    final text = input.toLowerCase().trim();

    // Open app
    if (_contains(text, ['open', 'launch', 'start', 'run']) &&
        _contains(text, ['app', 'whatsapp', 'instagram', 'telegram', 'slack', 'discord'])) {
      return TaskType.openApp;
    }

    // Send message
    if (_contains(text, ['send', 'msg', 'message', 'reply', 'text'])) {
      return TaskType.sendMessage;
    }

    // Search
    if (_contains(text, ['search', 'find', 'look for'])) {
      return TaskType.search;
    }

    // Type
    if (_contains(text, ['type', 'write', 'enter'])) {
      return TaskType.type;
    }

    // Screenshot
    if (_contains(text, ['screenshot', 'screen shot', 'snap', 'capture screen'])) {
      return TaskType.screenshot;
    }

    // Call
    if (_contains(text, ['call', 'ring', 'phone'])) {
      return TaskType.callPerson;
    }

    // SMS
    if (_contains(text, ['sms', 'text message', 'send sms'])) {
      return TaskType.sms;
    }

    // Alarm
    if (_contains(text, ['alarm', 'remind', 'set timer'])) {
      return TaskType.setAlarm;
    }

    // Play music
    if (_contains(text, ['play', 'music', 'song'])) {
      return TaskType.playMusic;
    }

    // Open URL
    if (text.contains('http') || text.contains('.com') || text.contains('.net')) {
      return TaskType.openUrl;
    }

    // Toggle
    if (_contains(text, ['toggle', 'turn on', 'turn off', 'enable', 'disable'])) {
      if (_contains(text, ['wifi', 'bluetooth', 'airplane'])) {
        return text.contains('wifi') ? TaskType.toggleWifi : TaskType.toggleBluetooth;
      }
    }

    return TaskType.custom;
  }

  // ── Execute task ──────────────────────────────────────────

  static Future<AutomationResult> execute(AutomationTask task) async {
    try {
      final sw = Stopwatch()..start();

      switch (task.type) {
        case TaskType.openApp:
          return await _openApp(task);
        case TaskType.sendMessage:
          return await _sendMessage(task);
        case TaskType.search:
          return await _search(task);
        case TaskType.type:
          return await _type(task);
        case TaskType.screenshot:
          return await _screenshot(task);
        case TaskType.readClipboard:
          return await _readClipboard(task, sw);
        case TaskType.writeClipboard:
          return await _writeClipboard(task, sw);
        case TaskType.openUrl:
          return await _openUrl(task);
        case TaskType.setAlarm:
          return await _setAlarm(task);
        case TaskType.playMusic:
          return await _playMusic(task);
        case TaskType.callPerson:
          return await _callPerson(task);
        case TaskType.sms:
          return await _sendSMS(task);
        case TaskType.click:
          return AutomationResult(
            success: false,
            message: 'Click action not implemented yet',
          );
        case TaskType.openSettings:
          return await _openSettings(task);
        case TaskType.toggleWifi:
          return await _toggleWifi(task);
        case TaskType.toggleBluetooth:
          return await _toggleBluetooth(task);
        case TaskType.custom:
          return AutomationResult(
            success: false,
            message: 'Unknown command type',
          );
      }
    } catch (e) {
      return AutomationResult(
        success: false,
        message: 'Execution error: $e',
      );
    }
  }

  // ── Task implementations ───────────────────────────────────

  static Future<AutomationResult> _openApp(AutomationTask task) async {
    try {
      final appName = _extractAppName(task.command);
      final pkg = APP_PACKAGES[appName];
      if (pkg == null) {
        return AutomationResult(
          success: false,
          message: 'App "$appName" not found',
        );
      }

      await _platform.invokeMethod('openApp', {'package': pkg});
      return AutomationResult(
        success: true,
        message: 'Opened ${appName}',
      );
    } catch (e) {
      return AutomationResult(success: false, message: e.toString());
    }
  }

  static Future<AutomationResult> _sendMessage(AutomationTask task) async {
    try {
      // Extract: "send msg to john: hello"
      // Parse: recipient, message text
      final parts = task.command.split(':');
      if (parts.length < 2) {
        return AutomationResult(
          success: false,
          message: 'Format: send message to [name]: [text]',
        );
      }

      await _accessibilityChannel.invokeMethod('sendMessage', {
        'recipient': parts[0].trim(),
        'text': parts.sublist(1).join(':').trim(),
      });

      return AutomationResult(
        success: true,
        message: 'Message sent',
      );
    } catch (e) {
      return AutomationResult(success: false, message: e.toString());
    }
  }

  static Future<AutomationResult> _search(AutomationTask task) async {
    try {
      // Extract query: "search playstore for game xyz"
      final query = task.command
          .replaceFirst(RegExp(r'search\s+'), '')
          .replaceFirst(RegExp(r'(playstore|google|web)\s+for\s+'), '')
          .trim();

      await _platform.invokeMethod('search', {'query': query});
      return AutomationResult(
        success: true,
        message: 'Searching for "$query"',
      );
    } catch (e) {
      return AutomationResult(success: false, message: e.toString());
    }
  }

  static Future<AutomationResult> _type(AutomationTask task) async {
    try {
      final text = task.command
          .replaceFirst(RegExp(r'(type|write)\s+'), '')
          .trim();

      await _accessibilityChannel.invokeMethod('typeText', {'text': text});
      return AutomationResult(
        success: true,
        message: 'Typed "$text"',
      );
    } catch (e) {
      return AutomationResult(success: false, message: e.toString());
    }
  }

  static Future<AutomationResult> _screenshot(AutomationTask task) async {
    try {
      final path = await _platform.invokeMethod<String>('screenshot');
      return AutomationResult(
        success: true,
        message: 'Screenshot saved',
        output: path,
      );
    } catch (e) {
      return AutomationResult(success: false, message: e.toString());
    }
  }

  static Future<AutomationResult> _readClipboard(
      AutomationTask task, Stopwatch sw) async {
    try {
      final data = await Clipboard.getData('text/plain');
      sw.stop();
      return AutomationResult(
        success: true,
        message: 'Clipboard: ${data?.text ?? "empty"}',
        output: data?.text,
        executionTime: sw.elapsed,
      );
    } catch (e) {
      return AutomationResult(success: false, message: e.toString());
    }
  }

  static Future<AutomationResult> _writeClipboard(
      AutomationTask task, Stopwatch sw) async {
    try {
      final text = task.command.replaceFirst(RegExp(r'copy\s+'), '').trim();
      await Clipboard.setData(ClipboardData(text: text));
      sw.stop();
      return AutomationResult(
        success: true,
        message: 'Copied to clipboard',
        executionTime: sw.elapsed,
      );
    } catch (e) {
      return AutomationResult(success: false, message: e.toString());
    }
  }

  static Future<AutomationResult> _openUrl(AutomationTask task) async {
    try {
      final url = _extractUrl(task.command);
      if (url == null) {
        return AutomationResult(
          success: false,
          message: 'Could not extract URL',
        );
      }

      await _platform.invokeMethod('openUrl', {'url': url});
      return AutomationResult(
        success: true,
        message: 'Opening $url',
      );
    } catch (e) {
      return AutomationResult(success: false, message: e.toString());
    }
  }

  static Future<AutomationResult> _setAlarm(AutomationTask task) async {
    try {
      // Extract time: "set alarm 8am" or "remindme 3pm"
      final time = _extractTime(task.command);
      if (time == null) {
        return AutomationResult(
          success: false,
          message: 'Could not parse time (try: 8am, 3:30pm)',
        );
      }

      await _platform.invokeMethod('setAlarm', {'time': time});
      return AutomationResult(
        success: true,
        message: 'Alarm set for $time',
      );
    } catch (e) {
      return AutomationResult(success: false, message: e.toString());
    }
  }

  static Future<AutomationResult> _playMusic(AutomationTask task) async {
    try {
      final song = task.command
          .replaceFirst(RegExp(r'play\s+'), '')
          .replaceFirst(RegExp(r'music|song'), '')
          .trim();

      await _platform.invokeMethod('playMusic', {'song': song});
      return AutomationResult(
        success: true,
        message: 'Playing "$song"',
      );
    } catch (e) {
      return AutomationResult(success: false, message: e.toString());
    }
  }

  static Future<AutomationResult> _callPerson(AutomationTask task) async {
    try {
      final name = task.command
          .replaceFirst(RegExp(r'call\s+'), '')
          .trim();

      await _platform.invokeMethod('callPerson', {'name': name});
      return AutomationResult(
        success: true,
        message: 'Opened dialer for $name',
      );
    } catch (e) {
      return AutomationResult(success: false, message: e.toString());
    }
  }

  static Future<AutomationResult> _sendSMS(AutomationTask task) async {
    try {
      final parts = task.command.split(':');
      if (parts.length < 2) {
        return AutomationResult(
          success: false,
          message: 'Format: sms [number]: [message]',
        );
      }

      await _platform.invokeMethod('sendSMS', {
        'number': parts[0].replaceFirst(RegExp(r'sms\s+'), '').trim(),
        'text': parts.sublist(1).join(':').trim(),
      });

      return AutomationResult(
        success: true,
        message: 'SMS sent',
      );
    } catch (e) {
      return AutomationResult(success: false, message: e.toString());
    }
  }

  static Future<AutomationResult> _openSettings(AutomationTask task) async {
    try {
      final setting = task.command
          .replaceFirst(RegExp(r'open\s+'), '')
          .replaceFirst(RegExp(r'settings'), '')
          .trim();

      await _platform.invokeMethod('openSettings', {'setting': setting});
      return AutomationResult(
        success: true,
        message: 'Opened settings',
      );
    } catch (e) {
      return AutomationResult(success: false, message: e.toString());
    }
  }

  static Future<AutomationResult> _toggleWifi(AutomationTask task) async {
    try {
      await _platform.invokeMethod('toggleWifi');
      return AutomationResult(
        success: true,
        message: 'Opened WiFi controls',
      );
    } catch (e) {
      return AutomationResult(success: false, message: e.toString());
    }
  }

  static Future<AutomationResult> _toggleBluetooth(AutomationTask task) async {
    try {
      await _platform.invokeMethod('toggleBluetooth');
      return AutomationResult(
        success: true,
        message: 'Opened Bluetooth controls',
      );
    } catch (e) {
      return AutomationResult(success: false, message: e.toString());
    }
  }

  // ── Helpers ────────────────────────────────────────────────

  static bool _contains(String text, List<String> keywords) {
    return keywords.any((k) => text.contains(k));
  }

  static String _extractAppName(String command) {
    for (final app in APP_PACKAGES.keys) {
      if (command.toLowerCase().contains(app)) {
        return app;
      }
    }
    return '';
  }

  static String? _extractUrl(String command) {
    final pattern = RegExp(r'https?://[^\s]+|www\.[^\s]+|[a-z0-9.-]+\.(com|net|org|io)\b');
    final match = pattern.firstMatch(command);
    if (match != null) {
      var url = match.group(0) ?? '';
      if (!url.startsWith('http')) {
        url = 'https://$url';
      }
      return url;
    }
    return null;
  }

  static String? _extractTime(String command) {
    final pattern = RegExp(r'(\d{1,2}):?(\d{2})?\s*(am|pm|a\.m|p\.m)?');
    final match = pattern.firstMatch(command);
    return match?.group(0);
  }
}

// lib/services/feature_settings.dart
// Complete settings wrapper — all platforms, model config, NO call guard

import 'package:shared_preferences/shared_preferences.dart';

class FeatureSettings {
  static late SharedPreferences _prefs;

  final bool offlineOnly;
  final bool autoReplyEnabled;
  final bool notificationsEnabled;
  final bool voiceEnabled;
  final bool alarmsEnabled;
  final bool notesEnabled;
  final bool mediaEnabled;
  final bool automationEnabled;
  final bool contactsEnabled;

  const FeatureSettings({
    this.offlineOnly = true,
    this.autoReplyEnabled = false,
    this.notificationsEnabled = true,
    this.voiceEnabled = true,
    this.alarmsEnabled = true,
    this.notesEnabled = true,
    this.mediaEnabled = true,
    this.automationEnabled = true,
    this.contactsEnabled = true,
  });

  factory FeatureSettings.defaults() => const FeatureSettings(
        offlineOnly: true,
        autoReplyEnabled: true,
        notificationsEnabled: true,
        voiceEnabled: true,
        alarmsEnabled: true,
        notesEnabled: true,
        mediaEnabled: true,
        automationEnabled: true,
        contactsEnabled: true,
      );

  static Future<FeatureSettings> load() async {
    await init();
    return FeatureSettings(
      offlineOnly: isOfflineOnly(),
      autoReplyEnabled: isAutoReplyEnabled(),
      notificationsEnabled: isNotificationsEnabled(),
      voiceEnabled: isVoiceEnabled(),
      alarmsEnabled: isAlarmsEnabled(),
      notesEnabled: isNotesEnabled(),
      mediaEnabled: isMediaEnabled(),
      automationEnabled: isAutomationEnabled(),
      contactsEnabled: isContactsEnabled(),
    );
  }

  static Future<void> init() async {
    _prefs = await SharedPreferences.getInstance();
  }

  // ── Auto-reply master switch ──────────────────────────────
  static bool isAutoReplyEnabled() =>
      _prefs.getBool('auto_reply') ?? false;
  static Future<void> setAutoReplyEnabled(bool v) =>
      _prefs.setBool('auto_reply', v);

  // ── Platform toggles ──────────────────────────────────────
  static bool isWhatsappEnabled() =>
      _prefs.getBool('whatsapp_enabled') ?? true;
  static Future<void> setWhatsappEnabled(bool v) =>
      _prefs.setBool('whatsapp_enabled', v);

  static bool isInstagramEnabled() =>
      _prefs.getBool('instagram_enabled') ?? false;
  static Future<void> setInstagramEnabled(bool v) =>
      _prefs.setBool('instagram_enabled', v);

  static bool isTelegramEnabled() =>
      _prefs.getBool('telegram_enabled') ?? false;
  static Future<void> setTelegramEnabled(bool v) =>
      _prefs.setBool('telegram_enabled', v);

  static bool isDiscordEnabled() =>
      _prefs.getBool('discord_enabled') ?? false;
  static Future<void> setDiscordEnabled(bool v) =>
      _prefs.setBool('discord_enabled', v);

  static bool isLinkedinEnabled() =>
      _prefs.getBool('linkedin_enabled') ?? false;
  static Future<void> setLinkedinEnabled(bool v) =>
      _prefs.setBool('linkedin_enabled', v);

  static bool isSnapchatEnabled() =>
      _prefs.getBool('snapchat_enabled') ?? false;
  static Future<void> setSnapchatEnabled(bool v) =>
      _prefs.setBool('snapchat_enabled', v);

  static bool isSmsEnabled() =>
      _prefs.getBool('sms_enabled') ?? true;
  static Future<void> setSmsEnabled(bool v) =>
      _prefs.setBool('sms_enabled', v);

  static bool isOfflineOnly() =>
      _prefs.getBool('offline_only') ?? true;
  static Future<void> setOfflineOnly(bool v) =>
      _prefs.setBool('offline_only', v);

  static bool isNotificationsEnabled() =>
      _prefs.getBool('notifications_enabled') ?? true;
  static Future<void> setNotificationsEnabled(bool v) =>
      _prefs.setBool('notifications_enabled', v);

  static bool isVoiceEnabled() =>
      _prefs.getBool('voice_enabled') ?? true;
  static Future<void> setVoiceEnabled(bool v) =>
      _prefs.setBool('voice_enabled', v);

  static bool isAlarmsEnabled() =>
      _prefs.getBool('alarms_enabled') ?? true;
  static Future<void> setAlarmsEnabled(bool v) =>
      _prefs.setBool('alarms_enabled', v);

  static bool isNotesEnabled() =>
      _prefs.getBool('notes_enabled') ?? true;
  static Future<void> setNotesEnabled(bool v) =>
      _prefs.setBool('notes_enabled', v);

  static bool isMediaEnabled() =>
      _prefs.getBool('media_enabled') ?? true;
  static Future<void> setMediaEnabled(bool v) =>
      _prefs.setBool('media_enabled', v);

  static bool isAutomationEnabled() =>
      _prefs.getBool('automation_enabled') ?? true;
  static Future<void> setAutomationEnabled(bool v) =>
      _prefs.setBool('automation_enabled', v);

  static bool isContactsEnabled() =>
      _prefs.getBool('contacts_enabled') ?? true;
  static Future<void> setContactsEnabled(bool v) =>
      _prefs.setBool('contacts_enabled', v);

  /// Check if a named platform is enabled
  static bool isPlatformEnabled(String platform) {
      switch (platform.toLowerCase().trim()) {
      case 'whatsapp':   return isWhatsappEnabled();
      case 'instagram':  return isInstagramEnabled();
      case 'telegram':   return isTelegramEnabled();
      case 'discord':    return isDiscordEnabled();
      case 'linkedin':   return isLinkedinEnabled();
      case 'snapchat':   return isSnapchatEnabled();
      case 'sms':        return isSmsEnabled();
      default:           return false;
    }
  }

  // ── Reply persona ─────────────────────────────────────────
  static String getUserName() =>
      _prefs.getString('reply_user_name') ?? 'Me';
  static Future<void> setUserName(String v) =>
      _prefs.setString('reply_user_name', v);

  static String getReplyTone() =>
      _prefs.getString('reply_tone') ?? 'casual';
  static Future<void> setReplyTone(String v) =>
      _prefs.setString('reply_tone', v);

  // ── Local model (Ollama / MLC Chat / llama.cpp) ───────────
  static String getOllamaUrl() =>
      _prefs.getString('ollama_url') ?? 'http://127.0.0.1:11434';
  static Future<void> setOllamaUrl(String v) =>
      _prefs.setString('ollama_url', v);

  static String getOllamaModel() =>
      _prefs.getString('ollama_model') ?? 'gemma4:e2b';
  static Future<void> setOllamaModel(String v) =>
      _prefs.setString('ollama_model', v);

  static String getApiFormat() =>
      _prefs.getString('api_format') ?? 'ollama';
  static Future<void> setApiFormat(String v) =>
      _prefs.setString('api_format', v);

  // ── Gemini fallback ───────────────────────────────────────
  static String getGeminiApiKey() =>
      _prefs.getString('gemini_api_key') ?? '';
  static Future<void> setGeminiApiKey(String v) =>
      _prefs.setString('gemini_api_key', v);

  // ── Diagnostics ───────────────────────────────────────────
  static Map<String, dynamic> dump() => {
    'auto_reply':        isAutoReplyEnabled(),
    'whatsapp_enabled':  isWhatsappEnabled(),
    'instagram_enabled': isInstagramEnabled(),
    'telegram_enabled':  isTelegramEnabled(),
    'discord_enabled':   isDiscordEnabled(),
    'linkedin_enabled':  isLinkedinEnabled(),
    'snapchat_enabled':  isSnapchatEnabled(),
    'sms_enabled':       isSmsEnabled(),
    'reply_user_name':   getUserName(),
    'reply_tone':        getReplyTone(),
    'ollama_url':        getOllamaUrl(),
    'ollama_model':      getOllamaModel(),
    'api_format':        getApiFormat(),
    'gemini_api_key':    getGeminiApiKey().isNotEmpty ? '***set***' : '(not set)',
  };
}

// lib/services/feature_settings.dart
// Complete settings wrapper — all platforms, model config, NO call guard

import 'package:shared_preferences/shared_preferences.dart';

class FeatureSettings {
  static late SharedPreferences _prefs;

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

// lib/screens/settings_screen.dart
// COMPLETE REPLACEMENT — all platforms, model settings, persona, Call Guard REMOVED

import 'package:flutter/material.dart';
import 'package:jarvis_app/ai/model_detector.dart';
import 'package:jarvis_app/services/feature_settings.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});
  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  // ── State ─────────────────────────────────────────────────
  bool _autoReply    = false;
  bool _whatsapp     = true;
  bool _instagram    = false;
  bool _telegram     = false;
  bool _discord      = false;
  bool _linkedin     = false;
  bool _snapchat     = false;
  bool _sms          = true;

  String _userName   = 'Me';
  String _tone       = 'casual';
  String _ollamaUrl  = '';
  String _ollamaModel = '';
  String _geminiKey  = '';
  String _apiFormat  = 'ollama';
  String _detectedModel = 'Tap to detect';
  bool   _detecting  = false;

  final _nameCtrl   = TextEditingController();
  final _urlCtrl    = TextEditingController();
  final _modelCtrl  = TextEditingController();
  final _geminiCtrl = TextEditingController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final geminiKey = await FeatureSettings.getGeminiApiKey();
    setState(() {
      _autoReply  = FeatureSettings.isAutoReplyEnabled();
      _whatsapp   = FeatureSettings.isWhatsappEnabled();
      _instagram  = FeatureSettings.isInstagramEnabled();
      _telegram   = FeatureSettings.isTelegramEnabled();
      _discord    = FeatureSettings.isDiscordEnabled();
      _linkedin   = FeatureSettings.isLinkedinEnabled();
      _snapchat   = FeatureSettings.isSnapchatEnabled();
      _sms        = FeatureSettings.isSmsEnabled();
      _userName   = FeatureSettings.getUserName();
      _tone       = FeatureSettings.getReplyTone();
      _ollamaUrl  = FeatureSettings.getOllamaUrl();
      _ollamaModel = FeatureSettings.getOllamaModel();
      _geminiKey  = geminiKey;
      _apiFormat  = FeatureSettings.getApiFormat();
    });
    _nameCtrl.text   = _userName;
    _urlCtrl.text    = _ollamaUrl;
    _modelCtrl.text  = _ollamaModel;
    _geminiCtrl.text = _geminiKey;
  }

  @override
  void dispose() {
    _nameCtrl.dispose();
    _urlCtrl.dispose();
    _modelCtrl.dispose();
    _geminiCtrl.dispose();
    super.dispose();
  }

  // ── Model detection ───────────────────────────────────────
  Future<void> _runDetect() async {
    setState(() { _detecting = true; _detectedModel = 'Detecting...'; });
    final result = await ModelDetector.autoDetectAndSave();
    setState(() {
      _detecting     = false;
      _detectedModel = result ?? 'No local model found';
      _ollamaUrl     = FeatureSettings.getOllamaUrl();
      _ollamaModel   = FeatureSettings.getOllamaModel();
      _apiFormat     = FeatureSettings.getApiFormat();
      _urlCtrl.text  = _ollamaUrl;
      _modelCtrl.text = _ollamaModel;
    });
  }

  // ── Build ─────────────────────────────────────────────────
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('JARVIS Settings')),
      body: ListView(
        children: [

          // ── MASTER SWITCH ───────────────────────────────────
          _sectionHeader('Auto Reply'),
          SwitchListTile(
            title: const Text('Enable auto-reply'),
            subtitle: const Text('JARVIS replies to incoming messages'),
            value: _autoReply,
            onChanged: (v) async {
              await FeatureSettings.setAutoReplyEnabled(v);
              setState(() => _autoReply = v);
            },
          ),

          // ── PLATFORMS ──────────────────────────────────────
          _sectionHeader('Platforms'),
          _platformTile('WhatsApp',  Icons.chat,           _whatsapp,
              (v) async { await FeatureSettings.setWhatsappEnabled(v);  setState(() => _whatsapp  = v); }),
          _platformTile('SMS',       Icons.sms,            _sms,
              (v) async { await FeatureSettings.setSmsEnabled(v);       setState(() => _sms       = v); }),
          _platformTile('Instagram', Icons.camera_alt,     _instagram,
              (v) async { await FeatureSettings.setInstagramEnabled(v); setState(() => _instagram = v); }),
          _platformTile('Telegram',  Icons.send,           _telegram,
              (v) async { await FeatureSettings.setTelegramEnabled(v);  setState(() => _telegram  = v); }),
          _platformTile('Discord',   Icons.headset_mic,    _discord,
              (v) async { await FeatureSettings.setDiscordEnabled(v);   setState(() => _discord   = v); }),
          _platformTile('LinkedIn',  Icons.work,           _linkedin,
              (v) async { await FeatureSettings.setLinkedinEnabled(v);  setState(() => _linkedin  = v); }),
          _platformTile('Snapchat',  Icons.camera,         _snapchat,
              (v) async { await FeatureSettings.setSnapchatEnabled(v);  setState(() => _snapchat  = v); }),

          // ── PERSONA ────────────────────────────────────────
          _sectionHeader('Reply Persona'),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: TextField(
              controller: _nameCtrl,
              decoration: const InputDecoration(
                labelText: 'Your name (used in replies)',
                border: OutlineInputBorder(),
                hintText: 'e.g. Arjun',
              ),
              onChanged: (v) => FeatureSettings.setUserName(v),
            ),
          ),
          _sectionHeader('Reply Tone', sub: true),
          ...['casual', 'friendly', 'formal', 'brief'].map((t) =>
            RadioListTile<String>(
              title: Text(t[0].toUpperCase() + t.substring(1)),
              subtitle: Text(_toneDesc(t)),
              value: t,
              groupValue: _tone,
              onChanged: (v) async {
                if (v == null) return;
                await FeatureSettings.setReplyTone(v);
                setState(() => _tone = v);
              },
            ),
          ),

          // ── LOCAL MODEL ────────────────────────────────────
          _sectionHeader('Local AI Model'),
          ListTile(
            leading: const Icon(Icons.search),
            title: const Text('Auto-detect model'),
            subtitle: Text(_detectedModel),
            trailing: _detecting
                ? const SizedBox(
                    width: 20, height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.refresh, size: 20),
            onTap: _detecting ? null : _runDetect,
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
            child: TextField(
              controller: _urlCtrl,
              decoration: const InputDecoration(
                labelText: 'Model server URL',
                border: OutlineInputBorder(),
                hintText: 'http://127.0.0.1:11434',
              ),
              onChanged: (v) => FeatureSettings.setOllamaUrl(v),
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
            child: TextField(
              controller: _modelCtrl,
              decoration: const InputDecoration(
                labelText: 'Model name',
                border: OutlineInputBorder(),
                hintText: 'gemma4:e2b',
              ),
              onChanged: (v) => FeatureSettings.setOllamaModel(v),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 2),
            child: Text('API Format: $_apiFormat',
                style: const TextStyle(fontSize: 12, color: Colors.grey)),
          ),

          // ── GEMINI FALLBACK ────────────────────────────────
          _sectionHeader('Gemini Fallback (optional)'),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: TextField(
              controller: _geminiCtrl,
              obscureText: true,
              decoration: const InputDecoration(
                labelText: 'Gemini API key',
                border: OutlineInputBorder(),
                hintText: 'Only needed if local model is unavailable',
              ),
              onChanged: (v) => FeatureSettings.setGeminiApiKey(v),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
            child: Text(
              'Get a free key at: aistudio.google.com/apikey',
              style: TextStyle(
                  fontSize: 12,
                  color: Theme.of(context).colorScheme.primary),
            ),
          ),

          const SizedBox(height: 32),
        ],
      ),
    );
  }

  // ── Helpers ───────────────────────────────────────────────
  Widget _sectionHeader(String title, {bool sub = false}) => Padding(
    padding: EdgeInsets.fromLTRB(16, sub ? 8 : 20, 16, 4),
    child: Text(
      title.toUpperCase(),
      style: TextStyle(
        fontSize: 11,
        fontWeight: FontWeight.w600,
        color: Theme.of(context).colorScheme.primary,
        letterSpacing: 1.2,
      ),
    ),
  );

  Widget _platformTile(
      String label, IconData icon, bool value, Function(bool) onChanged) =>
      SwitchListTile(
        secondary: Icon(icon),
        title: Text(label),
        value: value,
        onChanged: onChanged,
      );

  String _toneDesc(String t) {
    switch (t) {
      case 'casual':   return 'Like texting a close friend';
      case 'friendly': return 'Warm but not too casual';
      case 'formal':   return 'Polite and professional';
      case 'brief':    return '1–5 words is fine';
      default:         return '';
    }
  }
}

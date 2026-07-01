// lib/screens/offline_assistant_screen.dart
// JARVIS OFFLINE ASSISTANT — Full screen with:
//  • Chat with AI (English + Telugu, no server)
//  • Quick-add reminders/alarms from chat
//  • Notes from voice/text
//  • Laptop sync status badge
//  • All stored locally on phone

import 'package:flutter/material.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:speech_to_text/speech_to_text.dart';
import '../ai/offline_ai.dart';
import '../db/local_db.dart';
import '../models/offline_models.dart';
import '../services/device_automation_service.dart';
import '../services/device_data_service.dart';
import '../services/reminder_engine.dart';
import '../services/laptop_sync.dart';
import '../theme/app_theme.dart';
import '../widgets/jarvis_widgets.dart';
import 'talkback_screen.dart';

class OfflineAssistantScreen extends StatefulWidget {
  const OfflineAssistantScreen({super.key});

  @override
  State<OfflineAssistantScreen> createState() =>
      _OfflineAssistantScreenState();
}

class _OfflineAssistantScreenState extends State<OfflineAssistantScreen>
    with TickerProviderStateMixin {

  final _ai       = OfflineAI();
  final _ctrl     = TextEditingController();
  final _scroll   = ScrollController();
  final _tts      = FlutterTts();
  final _stt      = SpeechToText();
  final _automation = DeviceAutomationService();
  final _deviceData = DeviceDataService();

  List<_Msg>  _msgs       = [];
  bool        _loading    = false;
  bool        _listening  = false;
  bool        _ttsEnabled = true;
  String      _sttText    = '';

  late AnimationController _micCtrl;

  @override
  void initState() {
    super.initState();
    _micCtrl = AnimationController(vsync: this,
        duration: const Duration(milliseconds: 800))..repeat(reverse: true);
    _initTTS();
    _loadHistory();
  }

  @override
  void dispose() {
    _micCtrl.dispose();
    _ctrl.dispose();
    _scroll.dispose();
    _tts.stop();
    super.dispose();
  }

  Future<void> _initTTS() async {
    await _tts.setLanguage('en-IN');
    await _tts.setSpeechRate(0.9);
    await _tts.setVolume(1.0);
    await _tts.setPitch(1.0);
  }

  Future<void> _loadHistory() async {
    final history = await localDB.getHistory(limit: 20);
    setState(() {
      _msgs = history.reversed.map((h) => _Msg(
        text: h['message'] as String,
        isUser: h['role'] == 'user',
      )).toList();
    });
    _toBottom();
  }

  // ── Send message ─────────────────────────────────────────

  Future<void> _send([String? override]) async {
    final text = (override ?? _ctrl.text).trim();
    if (text.isEmpty || _loading) return;

    _ctrl.clear();
    setState(() {
      _msgs.add(_Msg(text: text, isUser: true));
      _loading = true;
    });
    _toBottom();

    await localDB.saveMessage('user', text);

    final deviceReply = await _handleDeviceAction(text);
    final resp = deviceReply ?? await _ai.process(text);

    // Handle special actions
    if (resp.action == AIAction.reminderSet && resp.data != null) {
      final id  = resp.data!['id'] as int;
      final r   = (await localDB.getReminders())
          .firstWhere((r) => r.id == id, orElse: () =>
              ReminderModel(title: '', remindAt: DateTime.now()));
      if (r.id != null) await ReminderEngine.scheduleReminder(r);
    }

    await localDB.saveMessage('assistant', resp.text);

    setState(() {
      _msgs.add(_Msg(text: resp.text, isUser: false,
          action: resp.action));
      _loading = false;
    });
    _toBottom();

    if (_ttsEnabled) {
      await _tts.speak(resp.text);
    }
  }

  Future<AIResponse?> _handleDeviceAction(String input) async {
    final lower = input.toLowerCase().trim();

    if (lower.startsWith('open ')) {
      final app = lower.replaceFirst('open ', '').trim();
      const packages = <String, String>{
        'whatsapp': 'com.whatsapp',
        'instagram': 'com.instagram.android',
        'telegram': 'org.telegram.messenger',
        'gmail': 'com.google.android.gm',
        'email': 'com.google.android.gm',
        'youtube': 'com.google.android.youtube',
        'maps': 'com.google.android.apps.maps',
        'chrome': 'com.android.chrome',
        'settings': 'com.android.settings',
        'contacts': 'com.android.contacts',
      };
      final packageName = packages[app];
      if (packageName != null) {
        await _automation.openApp(packageName);
        return AIResponse(text: 'Opening $app now.', action: AIAction.none);
      }
    }

    if (lower.startsWith('search ')) {
      final query = input.substring(7).trim();
      if (query.isNotEmpty) {
        await _automation.searchWeb(query);
        return AIResponse(text: 'Searching for $query.', action: AIAction.none);
      }
    }

    if (lower.startsWith('call ') || lower.startsWith('dial ')) {
      final target = input.substring(input.indexOf(' ') + 1).trim();
      final contacts = await _deviceData.getContacts(limit: 1000);
      final match = _findContact(contacts, target);
      final number = match?['number']?.toString() ??
          target.replaceAll(RegExp(r'[^0-9+]'), '');
      if (number.isNotEmpty) {
        await _deviceData.openDialer(number);
        return AIResponse(
          text: 'Opening dialer for ${match?['name'] ?? number}.',
          action: AIAction.none,
        );
      }
    }

    if (lower.startsWith('sms ') || lower.startsWith('text ')) {
      final payload = input.substring(input.indexOf(' ') + 1).trim();
      final split = payload.indexOf(':');
      if (split > 0) {
        final target = payload.substring(0, split).trim();
        final message = payload.substring(split + 1).trim();
        final contacts = await _deviceData.getContacts(limit: 1000);
        final match = _findContact(contacts, target);
        final number = match?['number']?.toString() ??
            target.replaceAll(RegExp(r'[^0-9+]'), '');
        if (number.isNotEmpty && message.isNotEmpty) {
          await _automation.composeSms(number, message);
          return AIResponse(
            text: 'Opening SMS draft for ${match?['name'] ?? number}.',
            action: AIAction.none,
          );
        }
      }
    }

    if (lower.startsWith('whatsapp ')) {
      final payload = input.substring('whatsapp '.length).trim();
      final split = payload.indexOf(':');
      if (split > 0) {
        final target = payload.substring(0, split).trim();
        final message = payload.substring(split + 1).trim();
        final contacts = await _deviceData.getContacts(limit: 1000);
        final match = _findContact(contacts, target);
        final number = match?['number']?.toString() ??
            target.replaceAll(RegExp(r'[^0-9+]'), '');
        if (number.isNotEmpty && message.isNotEmpty) {
          await _automation.composeWhatsApp(number: number, text: message);
          return AIResponse(
            text: 'Opening WhatsApp draft for ${match?['name'] ?? number}.',
            action: AIAction.none,
          );
        }
      }
    }

    if (lower.startsWith('email ')) {
      final payload = input.substring('email '.length).trim();
      final split = payload.indexOf(':');
      if (split > 0) {
        final email = payload.substring(0, split).trim();
        final body = payload.substring(split + 1).trim();
        if (email.contains('@')) {
          await _automation.composeEmail(email: email, body: body);
          return AIResponse(
            text: 'Opening email draft for $email.',
            action: AIAction.none,
          );
        }
      }
    }

    return null;
  }

  Map<String, dynamic>? _findContact(List<Map<String, dynamic>> contacts, String query) {
    final q = query.toLowerCase();
    for (final contact in contacts) {
      final name = (contact['name'] ?? '').toString().toLowerCase();
      final number = (contact['number'] ?? '').toString();
      if (name == q || name.contains(q) || number.contains(query)) {
        return contact;
      }
    }
    return null;
  }

  // ── Voice input ───────────────────────────────────────────

  Future<void> _toggleListen() async {
    if (_listening) {
      await _stt.stop();
      setState(() => _listening = false);
      if (_sttText.isNotEmpty) _send(_sttText);
      return;
    }

    final available = await _stt.initialize(
      onError: (e) => setState(() => _listening = false),
    );

    if (!available) {
      _showSnack('Microphone not available');
      return;
    }

    setState(() { _listening = true; _sttText = ''; });

    await _stt.listen(
      onResult: (r) {
        setState(() {
          _sttText = r.recognizedWords;
          if (r.finalResult) {
            _listening = false;
            _stt.stop();
            if (_sttText.isNotEmpty) _send(_sttText);
          }
        });
      },
      localeId: 'en_IN',   // handles Telugu-English mix
      cancelOnError: true,
      listenFor: const Duration(seconds: 15),
    );
  }

  void _toBottom() {
    Future.delayed(const Duration(milliseconds: 100), () {
      if (_scroll.hasClients) {
        _scroll.animateTo(_scroll.position.maxScrollExtent,
            duration: const Duration(milliseconds: 300),
            curve: Curves.easeOut);
      }
    });
  }

  void _showSnack(String msg) {
    ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(msg,
            style: J.shareTech(12)), backgroundColor: J.bg3));
  }

  @override
  Widget build(BuildContext context) {
    return Column(children: [

      // Header
      _buildHeader(),

      // Messages
      Expanded(
        child: _msgs.isEmpty
            ? _buildEmptyState()
            : ListView.builder(
                controller: _scroll,
                padding: const EdgeInsets.fromLTRB(14, 14, 14, 8),
                itemCount: _msgs.length + (_loading ? 1 : 0),
                itemBuilder: (_, i) {
                  if (i == _msgs.length) {
                    return Padding(
                      padding: EdgeInsets.only(bottom: 12),
                      child: TypingIndicator(),
                    );
                  }
                  return _buildBubble(_msgs[i]);
                },
              ),
      ),

      // Voice listening indicator
      if (_listening) _buildListeningBar(),

      // Input row
      _buildInput(),
    ]);
  }

  // ── Header ────────────────────────────────────────────────

  Widget _buildHeader() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: const BoxDecoration(
        color: J.bg1,
        border: Border(bottom: BorderSide(color: J.border0)),
      ),
      child: Row(children: [
        ArcReactor(size: 40),
        const SizedBox(width: 12),
        Expanded(child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('OFFLINE AI', style: J.orbitron(12, spacing: 2)),
            Row(children: [
              Container(width: 5, height: 5,
                  decoration: const BoxDecoration(
                      shape: BoxShape.circle, color: J.green)),
              const SizedBox(width: 5),
              Text('100% on-device', style: J.shareTech(10, color: J.t3)),
              const SizedBox(width: 12),
              // Laptop sync status
              AnimatedBuilder(
                animation: const AlwaysStoppedAnimation(0),
                builder: (_, __) => Row(children: [
                  Container(width: 5, height: 5,
                      decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: LaptopSync.isConnected ? J.cyan : J.t4)),
                  const SizedBox(width: 5),
                  Text(
                    LaptopSync.isConnected ? 'Laptop synced' : 'Laptop offline',
                    style: J.shareTech(10,
                        color: LaptopSync.isConnected ? J.cyan : J.t4),
                  ),
                ]),
              ),
            ]),
          ],
        )),

        // TTS toggle
        GestureDetector(
          onTap: () => setState(() => _ttsEnabled = !_ttsEnabled),
          child: Icon(
            _ttsEnabled ? Icons.volume_up_outlined : Icons.volume_off_outlined,
            color: _ttsEnabled ? J.cyan : J.t3,
            size: 18,
          ),
        ),
        const SizedBox(width: 12),
        GestureDetector(
          onTap: () {
            Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const TalkBackScreen()),
            );
          },
          child: const Icon(
            Icons.record_voice_over_outlined,
            color: J.green,
            size: 18,
          ),
        ),
      ]),
    );
  }

  // ── Chat bubble ───────────────────────────────────────────

  Widget _buildBubble(_Msg msg) {
    return Padding(
      padding: EdgeInsets.only(
        left: msg.isUser ? 48 : 0,
        right: msg.isUser ? 0 : 48,
        bottom: 10,
      ),
      child: Column(
        crossAxisAlignment: msg.isUser
            ? CrossAxisAlignment.end
            : CrossAxisAlignment.start,
        children: [
          if (!msg.isUser)
            Padding(
              padding: const EdgeInsets.only(left: 4, bottom: 4),
              child: Row(children: [
                Container(width: 5, height: 5,
                    decoration: const BoxDecoration(
                        shape: BoxShape.circle, color: J.cyan)),
                const SizedBox(width: 6),
                Text('JARVIS', style: J.orbitron(8, color: J.cyan, spacing: 2)),

                // Action badge
                if (msg.action == AIAction.reminderSet) ...[
                  const SizedBox(width: 8),
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      border: Border.all(color: J.green.withValues(alpha: 0.4)),
                      color: J.green.withValues(alpha: 0.08),
                    ),
                    child: Text('REMINDER SET',
                        style: J.orbitron(7, color: J.green, spacing: 1)),
                  ),
                ],
                if (msg.action == AIAction.noteSaved) ...[
                  const SizedBox(width: 8),
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      border: Border.all(color: J.amber.withValues(alpha: 0.4)),
                      color: J.amber.withValues(alpha: 0.08),
                    ),
                    child: Text('NOTE SAVED',
                        style: J.orbitron(7, color: J.amber, spacing: 1)),
                  ),
                ],
                if (msg.action == AIAction.identityReveal) ...[
                  const SizedBox(width: 8),
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      border: Border.all(color: J.cyan.withValues(alpha: 0.4)),
                      color: J.cyan.withValues(alpha: 0.06),
                    ),
                    child: Text('IDENTITY',
                        style: J.orbitron(7, color: J.cyan, spacing: 1)),
                  ),
                ],
              ]),
            ),

          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: BoxDecoration(
              color: msg.isUser ? J.bg4 : J.bg2,
              border: Border.all(
                color: msg.isUser ? J.border1 : J.border0.withValues(alpha: 0.5),
              ),
            ),
            child: Text(msg.text, style: J.rajdhani(14,
                color: msg.isUser ? J.t1 : J.t2)),
          ),
        ],
      ),
    );
  }

  // ── Listening bar ─────────────────────────────────────────

  Widget _buildListeningBar() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      color: J.cyan.withValues(alpha: 0.06),
      child: Row(children: [
        AnimatedBuilder(
          animation: _micCtrl,
          builder: (_, __) => Container(
            width: 8, height: 8,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: J.cyan.withValues(alpha: 0.5 + _micCtrl.value * 0.5),
              boxShadow: [BoxShadow(
                  color: J.cyan.withValues(alpha: 0.3 + _micCtrl.value * 0.3),
                  blurRadius: 8)],
            ),
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: Text(
            _sttText.isNotEmpty ? _sttText : 'Listening...',
            style: J.shareTech(12, color: J.cyan),
          ),
        ),
        GestureDetector(
          onTap: _toggleListen,
          child: const Icon(Icons.stop_circle_outlined,
              color: J.cyan, size: 20),
        ),
      ]),
    );
  }

  // ── Input ─────────────────────────────────────────────────

  Widget _buildInput() {
    return Container(
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 14),
      decoration: const BoxDecoration(
        color: J.bg1,
        border: Border(top: BorderSide(color: J.border0)),
      ),
      child: SafeArea(
        top: false,
        child: Row(children: [
          // Mic button
          GestureDetector(
            onTap: _toggleListen,
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              width: 44, height: 44,
              decoration: BoxDecoration(
                color: _listening
                    ? J.cyan.withValues(alpha: 0.15)
                    : J.bg3,
                border: Border.all(
                    color: _listening ? J.cyan : J.border0),
              ),
              child: Icon(
                _listening ? Icons.mic : Icons.mic_none_outlined,
                color: _listening ? J.cyan : J.t3,
                size: 18,
              ),
            ),
          ),
          const SizedBox(width: 8),

          // Text input
          Expanded(
            child: Container(
              decoration: BoxDecoration(
                border: Border.all(color: J.border0),
                color: J.bg2,
              ),
              child: TextField(
                controller: _ctrl,
                style: J.rajdhani(15),
                maxLines: 3, minLines: 1,
                decoration: InputDecoration(
                  hintText: 'English or Telugu...',
                  border: InputBorder.none,
                  contentPadding: const EdgeInsets.symmetric(
                      horizontal: 12, vertical: 10),
                  hintStyle: J.shareTech(12, color: J.t4),
                ),
                onSubmitted: (_) => _send(),
              ),
            ),
          ),
          const SizedBox(width: 8),

          // Send button
          GestureDetector(
            onTap: _send,
            child: Container(
              width: 44, height: 44,
              decoration: BoxDecoration(
                color: J.cyan.withValues(alpha: 0.9),
                border: Border.all(color: J.cyan),
              ),
              child: const Icon(Icons.send, color: J.bg0, size: 18),
            ),
          ),
        ]),
      ),
    );
  }

  // ── Empty state ───────────────────────────────────────────

  Widget _buildEmptyState() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            ArcReactor(size: 80),
            const SizedBox(height: 20),
            Text('OFFLINE AI READY',
                style: J.orbitron(13, color: J.t3, spacing: 3)),
            const SizedBox(height: 8),
            Text('No internet or laptop needed',
                style: J.rajdhani(14, color: J.t3)),
            const SizedBox(height: 28),
            Wrap(spacing: 8, runSpacing: 8, children: [
              _QuickChip('Remind me at 8am'),
              _QuickChip('Set alarm tomorrow'),
              _QuickChip('Note cheyyi'),
              _QuickChip('Evaru nuvu?'),
              _QuickChip('Who are you?'),
              _QuickChip('Show reminders'),
              _QuickChip('Open WhatsApp'),
              _QuickChip('Call John'),
              _QuickChip('SMS Mom: I am on my way'),
            ].map((c) => GestureDetector(
              onTap: () => _send(c.label),
              child: c,
            )).toList()),
          ],
        ),
      ),
    );
  }
}


// ── Data classes ──────────────────────────────────────────────

class _Msg {
  final String   text;
  final bool     isUser;
  final AIAction action;
  _Msg({required this.text, required this.isUser,
        this.action = AIAction.none});
}

class _QuickChip extends StatelessWidget {
  final String label;
  const _QuickChip(this.label);

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
      decoration: BoxDecoration(
        border: Border.all(color: J.border1),
        color: J.bg3,
      ),
      child: Text(label, style: J.shareTech(11, color: J.t2)),
    );
  }
}

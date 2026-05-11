// lib/screens/talkback_screen.dart
//
// The full-screen TalkBack interface for JARVIS
// ─────────────────────────────────────────────
// Features:
//  • Big animated mic button
//  • Live sound wave visualizer
//  • Live transcript display
//  • Chat history
//  • Continuous mode toggle
//  • Wake word toggle ("Hey Jarvis")
//  • Voice settings (speed, pitch, volume)

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../ai/offline_ai.dart';
import '../services/talkback_service.dart';
import '../services/device_automation_service.dart';
import '../services/device_data_service.dart';
import '../widgets/talkback_button.dart';

// Reuse colors from your theme
const _bg        = Color(0xFF010A12);
const _bgCard    = Color(0xFF061420);
const _bgPanel   = Color(0xFF0A1E2E);
const _cyan      = Color(0xFF00E5FF);
const _blue      = Color(0xFF0066FF);
const _green     = Color(0xFF00FFAA);
const _border    = Color(0xFF0D3348);
const _textPri   = Color(0xFFB0EEFF);
const _textSec   = Color(0xFF4A7A8A);
const _textDim   = Color(0xFF1E4A5A);


class TalkBackScreen extends StatefulWidget {
  const TalkBackScreen({super.key});

  @override
  State<TalkBackScreen> createState() => _TalkBackScreenState();
}

class _TalkBackScreenState extends State<TalkBackScreen> with TickerProviderStateMixin {
  late final TalkBackService _talkback;
  final OfflineAI _offlineAi = OfflineAI();
  final DeviceAutomationService _automation = DeviceAutomationService();
  final DeviceDataService _device = DeviceDataService();
  final List<_Msg> _history = [];
  final _scroll = ScrollController();

  late AnimationController _fadeCtrl;

  @override
  void initState() {
    super.initState();
    _fadeCtrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 800));
    _fadeCtrl.forward();

    _talkback = TalkBackService();

    // Wire up the speech → AI → speak pipeline
    _talkback.onUserSpeech = _handleUserSpeech;

    _talkback.initialize().then((ok) {
      if (ok && mounted) {
        _talkback.speak("JARVIS TalkBack ready. Tap the microphone to speak.");
      }
    });
  }

  @override
  void dispose() {
    _talkback.dispose();
    _fadeCtrl.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _handleUserSpeech(String text) async {
    // Add user message to history
    setState(() => _history.add(_Msg(role: 'user', text: text)));
    _scrollDown();

    try {
      final handled = await _handleLocalCommand(text);
      if (handled) return;
      final result = await _offlineAi.process(text);
      final response = result.text;
      setState(() => _history.add(_Msg(role: 'jarvis', text: response)));
      _scrollDown();
      await _talkback.respondWithSpeech(response);
    } catch (e) {
      const fallback =
          'I hit a local error while handling that command. Please try again.';
      setState(() => _history.add(_Msg(role: 'jarvis', text: fallback)));
      await _talkback.respondWithSpeech(fallback);
    }
  }

  Future<bool> _handleLocalCommand(String text) async {
    final lower = text.toLowerCase().trim();

    if (lower.startsWith('call ') || lower.startsWith('dial ')) {
      final query = text.substring(text.indexOf(' ') + 1).trim();
      final number = query.replaceAll(RegExp(r'[^0-9+]'), '');
      if (number.isNotEmpty) {
        await _device.openDialer(number);
        await _talkback.respondWithSpeech('Opening dialer for $number');
        return true;
      }
      final contact = await _findBestContact(query);
      if (contact != null) {
        final name = contact['name'] ?? 'your contact';
        final phone = contact['number'] ?? '';
        if (phone.toString().isNotEmpty) {
          await _device.openDialer(phone.toString());
          await _talkback.respondWithSpeech('Opening dialer for $name');
        } else {
          await _talkback.respondWithSpeech('No number found for $name');
        }
      } else {
        await _talkback.respondWithSpeech('I could not find that contact.');
      }
      return true;
    }

    if (lower.startsWith('open ')) {
      final app = lower.replaceFirst('open ', '').trim();
      final packages = <String, String>{
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
        await _talkback.respondWithSpeech('Opening $app');
        return true;
      }
    }

    if (lower.startsWith('search ')) {
      final query = text.substring(7).trim();
      if (query.isNotEmpty) {
        await _automation.searchWeb(query);
        await _talkback.respondWithSpeech('Searching for $query');
        return true;
      }
    }

    if (lower.startsWith('sms ') || lower.startsWith('text ')) {
      final payload = text.substring(text.indexOf(' ') + 1).trim();
      final splitIndex = payload.indexOf(':');
      if (splitIndex > 0) {
        final targetQuery = payload.substring(0, splitIndex).trim();
        final body = payload.substring(splitIndex + 1).trim();
        final contact = await _findBestContact(targetQuery);
        final number = contact?['number']?.toString() ??
            targetQuery.replaceAll(RegExp(r'[^0-9+]'), '');
        if (number.isNotEmpty && body.isNotEmpty) {
          await _automation.composeSms(number, body);
          await _talkback.respondWithSpeech('Opening SMS for ${contact?['name'] ?? number}');
          return true;
        }
      }
    }

    if (lower.startsWith('whatsapp ')) {
      final payload = text.substring('whatsapp '.length).trim();
      final splitIndex = payload.indexOf(':');
      if (splitIndex > 0) {
        final targetQuery = payload.substring(0, splitIndex).trim();
        final body = payload.substring(splitIndex + 1).trim();
        final contact = await _findBestContact(targetQuery);
        final number = contact?['number']?.toString() ??
            targetQuery.replaceAll(RegExp(r'[^0-9+]'), '');
        if (number.isNotEmpty && body.isNotEmpty) {
          await _automation.composeWhatsApp(number: number, text: body);
          await _talkback.respondWithSpeech(
            'Opening WhatsApp for ${contact?['name'] ?? number}',
          );
          return true;
        }
      }
    }

    if (lower.startsWith('email ')) {
      final payload = text.substring('email '.length).trim();
      final splitIndex = payload.indexOf(':');
      if (splitIndex > 0) {
        final target = payload.substring(0, splitIndex).trim();
        final body = payload.substring(splitIndex + 1).trim();
        if (target.contains('@')) {
          await _automation.composeEmail(email: target, body: body);
          await _talkback.respondWithSpeech('Opening email draft for $target');
          return true;
        }
      }
    }

    if (lower.contains('sync')) {
      await _device.syncAllToPc();
      await _talkback.respondWithSpeech('Sync started. I will send your data to the PC.');
      return true;
    }

    if (lower.contains('usage') || lower.contains('screen time')) {
      final summary = await _device.getUsageSummary(days: 1);
      if (summary['error'] == 'USAGE_STATS_PERMISSION_REQUIRED') {
        await _device.openUsageAccessSettings();
        await _talkback.respondWithSpeech('Please grant Usage Access for JARVIS. I opened the settings.');
        return true;
      }
      final totalMs = (summary['total_ms'] ?? 0) as num;
      final apps = (summary['apps'] as List?) ?? [];
      final top = apps.isNotEmpty ? apps.first as Map : null;
      final topName = top?['app_name'] ?? 'Unknown app';
      final topMs = (top?['total_ms'] ?? 0) as num;
      await _talkback.respondWithSpeech(
        'Your screen time today is ${_formatMs(totalMs)}. '
        'Top app is $topName for ${_formatMs(topMs)}.'
      );
      return true;
    }

    if (lower.contains('call time') || lower.contains('call stats')) {
      final stats = await _device.getCallStats(days: 1);
      final totalCalls = stats['total_calls'] ?? 0;
      final totalSec = stats['total_duration_sec'] ?? 0;
      await _talkback.respondWithSpeech(
        'You made $totalCalls calls today for a total of ${_formatSeconds(totalSec)}.'
      );
      return true;
    }

    if (lower.contains('voice usage') || lower.contains('mic usage')) {
      final usage = await _talkback.getVoiceUsage();
      final sessions = usage['sessions'] ?? 0;
      final totalMs = usage['total_ms'] ?? 0;
      await _talkback.respondWithSpeech(
        'Voice usage: $sessions sessions, total ${_formatMs(totalMs)}.'
      );
      return true;
    }

    return false;
  }

  Future<Map<String, dynamic>?> _findBestContact(String query) async {
    if (query.isEmpty) return null;
    final contacts = await _device.getContacts(limit: 1000);
    final q = query.toLowerCase();
    Map<String, dynamic>? exact;
    for (final c in contacts) {
      final name = (c['name'] ?? '').toString().toLowerCase();
      if (name == q) { exact = c; break; }
      if (exact == null && name.contains(q)) exact = c;
    }
    return exact;
  }

  String _formatMs(num ms) {
    final totalSec = (ms / 1000).round();
    return _formatSeconds(totalSec);
  }

  String _formatSeconds(num sec) {
    final s = sec.round();
    final h = s ~/ 3600;
    final m = (s % 3600) ~/ 60;
    final r = s % 60;
    if (h > 0) return '${h}h ${m}m';
    if (m > 0) return '${m}m ${r}s';
    return '${r}s';
  }

  void _scrollDown() {
    Future.delayed(const Duration(milliseconds: 150), () {
      if (_scroll.hasClients) {
        _scroll.animateTo(
          _scroll.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  void _showSettings() {
    showModalBottomSheet(
      context: context,
      backgroundColor: _bgCard,
      isScrollControlled: true,
      builder: (_) => _SettingsSheet(talkback: _talkback),
    );
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: _talkback,
      builder: (context, _) {
        return Scaffold(
          backgroundColor: _bg,
          appBar: AppBar(
            backgroundColor: _bg,
            elevation: 0,
            title: Row(mainAxisSize: MainAxisSize.min, children: [
              _StatusDot(active: _talkback.initialized),
              const SizedBox(width: 8),
              Text('TALKBACK', style: GoogleFonts.orbitron(
                fontSize: 14, color: _cyan, letterSpacing: 4, fontWeight: FontWeight.w700,
              )),
            ]),
            actions: [
              // Continuous mode toggle
              GestureDetector(
                onTap: () {
                  if (_talkback.continuousMode) {
                    _talkback.stopContinuousMode();
                  } else {
                    _talkback.startContinuousMode();
                  }
                },
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 8),
                  child: Row(mainAxisSize: MainAxisSize.min, children: [
                    Icon(Icons.loop, size: 16,
                      color: _talkback.continuousMode ? _cyan : _textSec),
                    const SizedBox(width: 4),
                    Text('AUTO', style: GoogleFonts.orbitron(
                      fontSize: 8, letterSpacing: 1.5,
                      color: _talkback.continuousMode ? _cyan : _textSec,
                    )),
                  ]),
                ),
              ),
              IconButton(
                icon: const Icon(Icons.tune_outlined, color: _textSec, size: 20),
                onPressed: _showSettings,
              ),
            ],
          ),

          body: Stack(children: [
            // ── Background grid ──
            Positioned.fill(child: CustomPaint(painter: _GridPainter())),

            FadeTransition(
              opacity: _fadeCtrl,
              child: Column(children: [

                // ── Chat history ──
                Expanded(
                  child: _history.isEmpty
                      ? _EmptyState()
                      : ListView.builder(
                          controller: _scroll,
                          padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
                          itemCount: _history.length,
                          itemBuilder: (_, i) => _HistoryBubble(msg: _history[i]),
                        ),
                ),

                // ── Transcript live display ──
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: TranscriptBubble(talkback: _talkback),
                ),

                const SizedBox(height: 12),

                // ── Sound wave ──
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24),
                  child: SoundWaveVisualizer(talkback: _talkback, height: 44),
                ),

                const SizedBox(height: 20),

                // ── Mic button ──
                TalkBackButton(talkback: _talkback, size: 76),

                const SizedBox(height: 12),

                // ── Wake word status ──
                GestureDetector(
                  onTap: () => _talkback.setWakeWordEnabled(!_talkback.wakeWordEnabled),
                  child: Row(mainAxisSize: MainAxisSize.min, children: [
                    _StatusDot(active: _talkback.wakeWordEnabled, color: _green),
                    const SizedBox(width: 6),
                    Text(
                      _talkback.wakeWordEnabled
                          ? 'WAKE WORD: ON — say "Hey Jarvis"'
                          : 'WAKE WORD: OFF — tap to enable',
                      style: GoogleFonts.orbitron(
                        fontSize: 9, letterSpacing: 1.5,
                        color: _talkback.wakeWordEnabled ? _green : _textSec,
                      ),
                    ),
                  ]),
                ),

                const SizedBox(height: 28),
              ]),
            ),
          ]),
        );
      },
    );
  }
}


// ══════════════════════════════════════════
//  SETTINGS BOTTOM SHEET
// ══════════════════════════════════════════
class _SettingsSheet extends StatefulWidget {
  final TalkBackService talkback;
  const _SettingsSheet({required this.talkback});

  @override
  State<_SettingsSheet> createState() => _SettingsSheetState();
}

class _SettingsSheetState extends State<_SettingsSheet> {
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(20, 20, 20, 36),
      decoration: const BoxDecoration(
        color: _bgCard,
        border: Border(top: BorderSide(color: _border)),
      ),
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
        // Handle
        Center(child: Container(width: 40, height: 3,
          decoration: BoxDecoration(color: _border, borderRadius: BorderRadius.circular(2)))),
        const SizedBox(height: 16),

        Text('VOICE SETTINGS', style: GoogleFonts.orbitron(
          fontSize: 12, color: _cyan, letterSpacing: 2.5)),
        const SizedBox(height: 20),

        // Volume
        _SliderRow(
          label: 'VOLUME',
          value: widget.talkback.volume,
          min: 0, max: 1,
          divisions: 10,
          onChanged: (v) { widget.talkback.setVolume(v); setState(() {}); },
          valueLabel: '${(widget.talkback.volume * 100).toInt()}%',
        ),
        const SizedBox(height: 16),

        // Speech rate
        _SliderRow(
          label: 'SPEECH RATE',
          value: widget.talkback.speechRate,
          min: 0.1, max: 1.0,
          divisions: 9,
          onChanged: (v) { widget.talkback.setSpeechRate(v); setState(() {}); },
          valueLabel: widget.talkback.speechRate < 0.35 ? 'SLOW'
              : widget.talkback.speechRate < 0.65 ? 'NORMAL' : 'FAST',
        ),
        const SizedBox(height: 16),

        // Pitch
        _SliderRow(
          label: 'VOICE PITCH',
          value: widget.talkback.pitch,
          min: 0.5, max: 2.0,
          divisions: 15,
          onChanged: (v) { widget.talkback.setPitch(v); setState(() {}); },
          valueLabel: widget.talkback.pitch < 0.85 ? 'LOW'
              : widget.talkback.pitch < 1.25 ? 'NORMAL' : 'HIGH',
        ),

        const SizedBox(height: 24),

        // Test voice button
        GestureDetector(
          onTap: () {
            Navigator.pop(context);
            widget.talkback.testVoice();
          },
          child: Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(vertical: 13),
            decoration: BoxDecoration(
              color: _cyan.withOpacity(0.08),
              border: Border.all(color: _cyan.withOpacity(0.4)),
            ),
            child: Center(child: Row(mainAxisSize: MainAxisSize.min, children: [
              const Icon(Icons.play_circle_outline, color: _cyan, size: 16),
              const SizedBox(width: 8),
              Text('TEST VOICE', style: GoogleFonts.orbitron(fontSize: 11, letterSpacing: 2, color: _cyan)),
            ])),
          ),
        ),
      ]),
    );
  }
}

class _SliderRow extends StatelessWidget {
  final String label, valueLabel;
  final double value, min, max;
  final int divisions;
  final ValueChanged<double> onChanged;

  const _SliderRow({
    required this.label, required this.value, required this.min,
    required this.max, required this.divisions, required this.onChanged,
    required this.valueLabel,
  });

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
        Text(label, style: GoogleFonts.orbitron(fontSize: 9, letterSpacing: 2, color: _textSec)),
        Text(valueLabel, style: GoogleFonts.orbitron(fontSize: 10, color: _cyan)),
      ]),
      SliderTheme(
        data: SliderTheme.of(context).copyWith(
          activeTrackColor: _cyan,
          inactiveTrackColor: _border,
          thumbColor: _cyan,
          thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 6),
          overlayShape: SliderComponentShape.noOverlay,
          trackHeight: 2,
        ),
        child: Slider(value: value, min: min, max: max, divisions: divisions, onChanged: onChanged),
      ),
    ]);
  }
}


// ══════════════════════════════════════════
//  HISTORY BUBBLE
// ══════════════════════════════════════════
class _HistoryBubble extends StatelessWidget {
  final _Msg msg;
  const _HistoryBubble({super.key, required this.msg});

  @override
  Widget build(BuildContext context) {
    final isUser = msg.role == 'user';
    final color  = isUser ? _cyan : _green;

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
        children: [
          if (!isUser) ...[
            Container(
              padding: const EdgeInsets.all(6),
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                border: Border.all(color: _green.withOpacity(0.5)),
                color: _green.withOpacity(0.07),
              ),
              child: const Icon(Icons.smart_toy_outlined, color: _green, size: 14),
            ),
            const SizedBox(width: 8),
          ],
          Flexible(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              decoration: BoxDecoration(
                color: color.withOpacity(0.07),
                border: Border.all(color: color.withOpacity(0.2)),
              ),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(
                  isUser ? 'YOU' : 'JARVIS',
                  style: GoogleFonts.orbitron(fontSize: 8, letterSpacing: 2, color: color.withOpacity(0.6)),
                ),
                const SizedBox(height: 4),
                Text(msg.text, style: GoogleFonts.shareTech(
                  fontSize: 14, color: _textPri, height: 1.5)),
              ]),
            ),
          ),
          if (isUser) ...[
            const SizedBox(width: 8),
            Container(
              padding: const EdgeInsets.all(6),
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                border: Border.all(color: _cyan.withOpacity(0.5)),
                color: _cyan.withOpacity(0.07),
              ),
              child: const Icon(Icons.person_outline, color: _cyan, size: 14),
            ),
          ],
        ],
      ),
    );
  }
}


// ── Supporting types & painters ──
class _Msg {
  final String role, text;
  _Msg({required this.role, required this.text});
}

class _EmptyState extends StatelessWidget {
  @override
  Widget build(BuildContext context) => Center(
    child: Column(mainAxisSize: MainAxisSize.min, children: [
      Icon(Icons.mic_none_outlined, color: _textDim, size: 48),
      const SizedBox(height: 12),
      Text('TAP THE MIC TO SPEAK', style: GoogleFonts.orbitron(
        fontSize: 11, letterSpacing: 3, color: _textSec)),
      const SizedBox(height: 6),
      Text('Or enable Wake Word and say "Hey Jarvis"',
        style: GoogleFonts.shareTech(fontSize: 12, color: _textDim)),
    ]),
  );
}

class _StatusDot extends StatefulWidget {
  final bool active;
  final Color? color;
  const _StatusDot({this.active = true, this.color});

  @override
  State<_StatusDot> createState() => _StatusDotState();
}

class _StatusDotState extends State<_StatusDot> with SingleTickerProviderStateMixin {
  late AnimationController _c;
  @override void initState() {
    super.initState();
    _c = AnimationController(vsync: this, duration: const Duration(seconds: 2))..repeat(reverse: true);
  }
  @override void dispose() { _c.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    final col = widget.color ?? (widget.active ? _cyan : _textSec);
    return AnimatedBuilder(
      animation: _c,
      builder: (_, __) => Container(
        width: 7, height: 7,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: col.withOpacity(widget.active ? 0.5 + _c.value * 0.5 : 0.2),
          boxShadow: widget.active ? [
            BoxShadow(color: col.withOpacity(_c.value * 0.5), blurRadius: 5)
          ] : null,
        ),
      ),
    );
  }
}

class _GridPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final p = Paint()
      ..color = const Color(0xFF0066FF).withOpacity(0.04)
      ..strokeWidth = 0.5;
    for (double x = 0; x < size.width; x += 40) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), p);
    }
    for (double y = 0; y < size.height; y += 40) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), p);
    }
  }
  @override
  bool shouldRepaint(_) => false;
}

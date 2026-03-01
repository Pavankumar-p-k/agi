// lib/screens/talkback_screen.dart
//
// The full-screen TalkBack interface for JARVIS
// ─────────────────────────────────────────────
// Features:
//  • Big animated mic button
//  • Live sound wave visualizer
//  • Live transcript display
//  • Chat history
//  • Manual tap-to-talk mode
//  • Wake word toggle ("Hey Jarvis")
//  • Voice settings (speed, pitch, volume)

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';
import '../services/talkback_service.dart';
import '../services/api_service.dart';
import '../widgets/talkback_button.dart';

// Reuse colors from your theme
const _bg = Color(0xFF010A12);
const _bgCard = Color(0xFF061420);
const _cyan = Color(0xFF00E5FF);
const _green = Color(0xFF00FFAA);
const _border = Color(0xFF0D3348);
const _textPri = Color(0xFFB0EEFF);
const _textSec = Color(0xFF4A7A8A);
const _textDim = Color(0xFF1E4A5A);

class TalkBackScreen extends StatefulWidget {
  const TalkBackScreen({super.key});

  @override
  State<TalkBackScreen> createState() => _TalkBackScreenState();
}

class _TalkBackScreenState extends State<TalkBackScreen>
    with TickerProviderStateMixin {
  late TalkBackService _talkback;
  Function(String text)? _previousOnUserSpeech;
  late Future<void> Function(String text) _speechHandler;
  final ApiService _api = ApiService();
  final List<_Msg> _history = [];
  final _scroll = ScrollController();

  late AnimationController _fadeCtrl;

  @override
  void initState() {
    super.initState();
    _fadeCtrl = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 800));
    _fadeCtrl.forward();

    _talkback = context.read<TalkBackService>();
    _previousOnUserSpeech = _talkback.onUserSpeech;
    _speechHandler = _handleUserSpeech;
    _talkback.onUserSpeech = _speechHandler;

    // Wire up the speech → AI → speak pipeline
    _talkback.initialize().then((ok) {
      if (ok && mounted && _history.isEmpty) {
        _talkback.speak("JARVIS TalkBack ready. Tap the microphone to speak.");
      }
    });
  }

  @override
  void dispose() {
    if (_talkback.onUserSpeech == _speechHandler) {
      _talkback.onUserSpeech = _previousOnUserSpeech;
    }
    _fadeCtrl.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _handleUserSpeech(String text) async {
    // Add user message to history
    setState(() => _history.add(_Msg(role: 'user', text: text)));
    _scrollDown();

    try {
      final result = await _api.chat(text);
      final response =
          result['response'] as String? ?? 'I had trouble with that.';
      setState(() => _history.add(_Msg(role: 'jarvis', text: response)));
      _scrollDown();
      // Speak the response
      await _talkback.respondWithSpeech(response);
    } catch (e) {
      const fallback =
          'I cannot reach the server right now. Please check your connection.';
      setState(() => _history.add(_Msg(role: 'jarvis', text: fallback)));
      await _talkback.respondWithSpeech(fallback);
    }
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
              Text('TALKBACK',
                  style: GoogleFonts.orbitron(
                    fontSize: 14,
                    color: _cyan,
                    letterSpacing: 4,
                    fontWeight: FontWeight.w700,
                  )),
            ]),
            actions: [
              IconButton(
                icon:
                    const Icon(Icons.tune_outlined, color: _textSec, size: 20),
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
                          itemBuilder: (_, i) =>
                              _HistoryBubble(msg: _history[i]),
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
                  onTap: () =>
                      _talkback.setWakeWordEnabled(!_talkback.wakeWordEnabled),
                  child: Row(mainAxisSize: MainAxisSize.min, children: [
                    _StatusDot(
                        active: _talkback.wakeWordEnabled, color: _green),
                    const SizedBox(width: 6),
                    Text(
                      _talkback.wakeWordEnabled
                          ? 'WAKE WORD: ON — say "Hey Jarvis"'
                          : 'WAKE WORD: OFF — tap to enable',
                      style: GoogleFonts.orbitron(
                        fontSize: 9,
                        letterSpacing: 1.5,
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
      child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Handle
            Center(
                child: Container(
                    width: 40,
                    height: 3,
                    decoration: BoxDecoration(
                        color: _border,
                        borderRadius: BorderRadius.circular(2)))),
            const SizedBox(height: 16),

            Text('VOICE SETTINGS',
                style: GoogleFonts.orbitron(
                    fontSize: 12, color: _cyan, letterSpacing: 2.5)),
            const SizedBox(height: 20),

            // Volume
            _SliderRow(
              label: 'VOLUME',
              value: widget.talkback.volume,
              min: 0,
              max: 1,
              divisions: 10,
              onChanged: (v) {
                widget.talkback.setVolume(v);
                setState(() {});
              },
              valueLabel: '${(widget.talkback.volume * 100).toInt()}%',
            ),
            const SizedBox(height: 16),

            // Speech rate
            _SliderRow(
              label: 'SPEECH RATE',
              value: widget.talkback.speechRate,
              min: 0.1,
              max: 1.0,
              divisions: 9,
              onChanged: (v) {
                widget.talkback.setSpeechRate(v);
                setState(() {});
              },
              valueLabel: widget.talkback.speechRate < 0.35
                  ? 'SLOW'
                  : widget.talkback.speechRate < 0.65
                      ? 'NORMAL'
                      : 'FAST',
            ),
            const SizedBox(height: 16),

            const SizedBox(height: 8),
            Text(
              'VOICE PROFILE: MALE (LOCKED)',
              style: GoogleFonts.orbitron(
                fontSize: 9,
                letterSpacing: 2,
                color: _green,
              ),
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
                child: Center(
                    child: Row(mainAxisSize: MainAxisSize.min, children: [
                  const Icon(Icons.play_circle_outline, color: _cyan, size: 16),
                  const SizedBox(width: 8),
                  Text('TEST VOICE',
                      style: GoogleFonts.orbitron(
                          fontSize: 11, letterSpacing: 2, color: _cyan)),
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
    required this.label,
    required this.value,
    required this.min,
    required this.max,
    required this.divisions,
    required this.onChanged,
    required this.valueLabel,
  });

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
        Text(label,
            style: GoogleFonts.orbitron(
                fontSize: 9, letterSpacing: 2, color: _textSec)),
        Text(valueLabel,
            style: GoogleFonts.orbitron(fontSize: 10, color: _cyan)),
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
        child: Slider(
            value: value,
            min: min,
            max: max,
            divisions: divisions,
            onChanged: onChanged),
      ),
    ]);
  }
}

// ══════════════════════════════════════════
//  HISTORY BUBBLE
// ══════════════════════════════════════════
class _HistoryBubble extends StatelessWidget {
  final _Msg msg;
  const _HistoryBubble({required this.msg});

  @override
  Widget build(BuildContext context) {
    final isUser = msg.role == 'user';
    final color = isUser ? _cyan : _green;

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment:
            isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
        children: [
          if (!isUser) ...[
            Container(
              padding: const EdgeInsets.all(6),
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                border: Border.all(color: _green.withOpacity(0.5)),
                color: _green.withOpacity(0.07),
              ),
              child:
                  const Icon(Icons.smart_toy_outlined, color: _green, size: 14),
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
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      isUser ? 'YOU' : 'JARVIS',
                      style: GoogleFonts.orbitron(
                          fontSize: 8,
                          letterSpacing: 2,
                          color: color.withOpacity(0.6)),
                    ),
                    const SizedBox(height: 4),
                    Text(msg.text,
                        style: GoogleFonts.shareTech(
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
          Text('TAP THE MIC TO SPEAK',
              style: GoogleFonts.orbitron(
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

class _StatusDotState extends State<_StatusDot>
    with SingleTickerProviderStateMixin {
  late AnimationController _c;
  @override
  void initState() {
    super.initState();
    _c = AnimationController(vsync: this, duration: const Duration(seconds: 2))
      ..repeat(reverse: true);
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final col = widget.color ?? (widget.active ? _cyan : _textSec);
    return AnimatedBuilder(
      animation: _c,
      builder: (_, __) => Container(
        width: 7,
        height: 7,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: col.withOpacity(widget.active ? 0.5 + _c.value * 0.5 : 0.2),
          boxShadow: widget.active
              ? [
                  BoxShadow(
                      color: col.withOpacity(_c.value * 0.5), blurRadius: 5)
                ]
              : null,
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

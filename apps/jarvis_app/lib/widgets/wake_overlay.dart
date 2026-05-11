// lib/widgets/wake_overlay.dart
//
// When the wake word fires, this full-screen overlay animates in,
// shows "Hey Jarvis" was detected, then hands off to TalkBack.
// Drop this at the root of your app widget tree.

import 'dart:async';
import 'dart:math';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../services/wake_service.dart';
import '../services/talkback_service.dart';

const _bg    = Color(0xFF010A12);
const _cyan  = Color(0xFF00E5FF);
const _green = Color(0xFF00FFAA);
const _textPri = Color(0xFFB0EEFF);
const _textSec = Color(0xFF4A7A8A);

class WakeOverlayWrapper extends StatefulWidget {
  final Widget child;
  final WakeService wakeService;
  final TalkBackService talkback;

  const WakeOverlayWrapper({
    super.key,
    required this.child,
    required this.wakeService,
    required this.talkback,
  });

  @override
  State<WakeOverlayWrapper> createState() => _WakeOverlayWrapperState();
}

class _WakeOverlayWrapperState extends State<WakeOverlayWrapper>
    with TickerProviderStateMixin {

  bool _showOverlay = false;
  late AnimationController _slideCtrl;
  late AnimationController _pulseCtrl;
  late Animation<Offset>   _slideAnim;
  late Animation<double>   _fadeAnim;

  Timer? _autoHideTimer;

  @override
  void initState() {
    super.initState();

    _slideCtrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 500));
    _pulseCtrl = AnimationController(vsync: this, duration: const Duration(seconds: 1))
      ..repeat(reverse: true);

    _slideAnim = Tween<Offset>(begin: const Offset(0, -1), end: Offset.zero)
        .animate(CurvedAnimation(parent: _slideCtrl, curve: Curves.easeOut));
    _fadeAnim  = CurvedAnimation(parent: _slideCtrl, curve: Curves.easeOut);

    // Wire wake word callback
    widget.wakeService.onWakeDetected = _onWakeDetected;
  }

  @override
  void dispose() {
    _slideCtrl.dispose();
    _pulseCtrl.dispose();
    _autoHideTimer?.cancel();
    super.dispose();
  }

  void _onWakeDetected() async {
    setState(() => _showOverlay = true);
    _slideCtrl.forward(from: 0);

    // Start listening with TalkBack
    await Future.delayed(const Duration(milliseconds: 600));
    await widget.talkback.speak("Yes?");
    await widget.talkback.startListening();

    // Wire TalkBack to hide overlay when done
    widget.talkback.onStateChange = (state) {
      if (state == TalkBackState.idle && _showOverlay) {
        _hideOverlay();
      }
    };

    // Auto-hide after 15s if nothing happens
    _autoHideTimer?.cancel();
    _autoHideTimer = Timer(const Duration(seconds: 15), _hideOverlay);
  }

  void _hideOverlay() {
    if (!mounted) return;
    _slideCtrl.reverse().then((_) {
      if (mounted) setState(() => _showOverlay = false);
    });
    _autoHideTimer?.cancel();
  }

  @override
  Widget build(BuildContext context) {
    return Stack(children: [
      widget.child,

      if (_showOverlay)
        Positioned.fill(
          child: GestureDetector(
            onTap: _hideOverlay,
            child: Container(color: Colors.black.withOpacity(0.6)),
          ),
        ),

      if (_showOverlay)
        Positioned(
          top: 0, left: 0, right: 0,
          child: SlideTransition(
            position: _slideAnim,
            child: FadeTransition(
              opacity: _fadeAnim,
              child: SafeArea(
                child: _WakeBanner(
                  talkback: widget.talkback,
                  pulseCtrl: _pulseCtrl,
                  onDismiss: _hideOverlay,
                ),
              ),
            ),
          ),
        ),
    ]);
  }
}


class _WakeBanner extends StatelessWidget {
  final TalkBackService talkback;
  final AnimationController pulseCtrl;
  final VoidCallback onDismiss;

  const _WakeBanner({
    required this.talkback,
    required this.pulseCtrl,
    required this.onDismiss,
  });

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: talkback,
      builder: (ctx, _) {
        final isListening = talkback.state == TalkBackState.listening;
        final isSpeaking  = talkback.state == TalkBackState.speaking;

        return Container(
          margin: const EdgeInsets.all(12),
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: const Color(0xFF061420),
            border: Border.all(color: _cyan.withOpacity(0.5), width: 1.5),
            boxShadow: [
              BoxShadow(color: _cyan.withOpacity(0.15), blurRadius: 24, spreadRadius: 4),
            ],
          ),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            // Header
            Row(children: [
              AnimatedBuilder(
                animation: pulseCtrl,
                builder: (_, __) => Container(
                  width: 10, height: 10,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: _cyan.withOpacity(0.5 + pulseCtrl.value * 0.5),
                    boxShadow: [BoxShadow(
                      color: _cyan.withOpacity(pulseCtrl.value * 0.5), blurRadius: 8)],
                  ),
                ),
              ),
              const SizedBox(width: 10),
              Text('J.A.R.V.I.S', style: GoogleFonts.orbitron(
                fontSize: 14, color: _cyan, letterSpacing: 4, fontWeight: FontWeight.w900)),
              const Spacer(),
              GestureDetector(
                onTap: onDismiss,
                child: const Icon(Icons.close, color: _textSec, size: 18),
              ),
            ]),

            const SizedBox(height: 12),

            // Sound bars
            _MiniWave(talkback: talkback),

            const SizedBox(height: 12),

            // Status text
            Text(
              isListening ? 'LISTENING...'
                : isSpeaking ? 'SPEAKING...'
                : talkback.state == TalkBackState.processing ? 'THINKING...'
                : 'READY',
              style: GoogleFonts.orbitron(
                fontSize: 11,
                color: isListening ? _cyan : isSpeaking ? _green : _textSec,
                letterSpacing: 3,
              ),
            ),

            // Transcript
            if (talkback.transcript.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(
                talkback.transcript,
                style: GoogleFonts.shareTech(fontSize: 14, color: _textPri, height: 1.4),
                textAlign: TextAlign.center,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ],

            if (isSpeaking && talkback.lastSpoken.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(
                talkback.lastSpoken,
                style: GoogleFonts.shareTech(fontSize: 13, color: _green.withOpacity(0.8), height: 1.4),
                textAlign: TextAlign.center,
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ]),
        );
      },
    );
  }
}


// Mini sound bar for the overlay banner
class _MiniWave extends StatefulWidget {
  final TalkBackService talkback;
  const _MiniWave({required this.talkback});

  @override
  State<_MiniWave> createState() => _MiniWaveState();
}

class _MiniWaveState extends State<_MiniWave> with SingleTickerProviderStateMixin {
  late AnimationController _c;
  final _rng = Random();
  final List<double> _bars = List.generate(16, (_) => 0.15);

  @override
  void initState() {
    super.initState();
    _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 100))
      ..addListener(_update)
      ..repeat();
  }

  @override
  void dispose() { _c.dispose(); super.dispose(); }

  void _update() {
    if (!mounted) return;
    final active = widget.talkback.state == TalkBackState.listening ||
                   widget.talkback.state == TalkBackState.speaking;
    setState(() {
      for (int i = 0; i < _bars.length; i++) {
        final target = active ? 0.1 + _rng.nextDouble() * 0.9 : 0.15;
        _bars[i] = (_bars[i] * 0.6 + target * 0.4).clamp(0.05, 1.0);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final color = widget.talkback.state == TalkBackState.speaking ? _green : _cyan;
    return SizedBox(
      height: 28,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: _bars.map((v) => Container(
          margin: const EdgeInsets.symmetric(horizontal: 2),
          width: 3,
          height: (28 * v).clamp(3.0, 28.0),
          decoration: BoxDecoration(
            color: color.withOpacity(0.4 + v * 0.6),
            borderRadius: BorderRadius.circular(2),
          ),
        )).toList(),
      ),
    );
  }
}

// lib/widgets/talkback_button.dart
//
// The animated microphone button + sound wave visualizer
// Drop it anywhere in your app and pass a TalkBackService

import 'dart:math';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../services/talkback_service.dart';

// ══════════════════════════════════════════
//  MAIN MIC BUTTON
// ══════════════════════════════════════════
class TalkBackButton extends StatefulWidget {
  final TalkBackService talkback;
  final double size;
  const TalkBackButton({super.key, required this.talkback, this.size = 72});

  @override
  State<TalkBackButton> createState() => _TalkBackButtonState();
}

class _TalkBackButtonState extends State<TalkBackButton>
    with TickerProviderStateMixin {
  late AnimationController _pulseCtrl;
  late AnimationController _ringCtrl;
  late AnimationController _waveCtrl;
  late Animation<double>   _pulseAnim;

  @override
  void initState() {
    super.initState();

    _pulseCtrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 900))
      ..repeat(reverse: true);
    _ringCtrl  = AnimationController(vsync: this, duration: const Duration(milliseconds: 1500))
      ..repeat();
    _waveCtrl  = AnimationController(vsync: this, duration: const Duration(milliseconds: 600))
      ..repeat(reverse: true);

    _pulseAnim = CurvedAnimation(parent: _pulseCtrl, curve: Curves.easeInOut);

    widget.talkback.addListener(_onStateChange);
  }

  @override
  void dispose() {
    widget.talkback.removeListener(_onStateChange);
    _pulseCtrl.dispose();
    _ringCtrl.dispose();
    _waveCtrl.dispose();
    super.dispose();
  }

  void _onStateChange() => setState(() {});

  void _onTap() {
    final tb = widget.talkback;
    switch (tb.state) {
      case TalkBackState.idle:
        tb.startListening();
      case TalkBackState.listening:
        tb.stopListening();
      case TalkBackState.speaking:
        tb.stopSpeaking();
      default:
        break;
    }
  }

  Color get _stateColor {
    switch (widget.talkback.state) {
      case TalkBackState.listening:   return const Color(0xFF00E5FF);
      case TalkBackState.speaking:    return const Color(0xFF00FFAA);
      case TalkBackState.processing:  return const Color(0xFF0066FF);
      case TalkBackState.error:       return const Color(0xFFFF1744);
      default:                        return const Color(0xFF1A6680);
    }
  }

  String get _stateLabel {
    switch (widget.talkback.state) {
      case TalkBackState.listening:   return 'LISTENING';
      case TalkBackState.speaking:    return 'SPEAKING';
      case TalkBackState.processing:  return 'THINKING';
      case TalkBackState.error:       return 'ERROR';
      default:                        return 'TAP TO SPEAK';
    }
  }

  bool get _isActive =>
    widget.talkback.state == TalkBackState.listening ||
    widget.talkback.state == TalkBackState.speaking;

  @override
  Widget build(BuildContext context) {
    final s = widget.size;
    return GestureDetector(
      onTap: _onTap,
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        SizedBox(
          width: s * 1.8,
          height: s * 1.8,
          child: Stack(alignment: Alignment.center, children: [
            // Outer pulsing ring (only when active)
            if (_isActive)
              AnimatedBuilder(
                animation: _pulseAnim,
                builder: (_, __) => Container(
                  width: s * (1.4 + _pulseAnim.value * 0.4),
                  height: s * (1.4 + _pulseAnim.value * 0.4),
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    border: Border.all(
                      color: _stateColor.withOpacity(0.15 + _pulseAnim.value * 0.2),
                      width: 1.5,
                    ),
                  ),
                ),
              ),

            // Middle rotating ring (only when active)
            if (_isActive)
              AnimatedBuilder(
                animation: _ringCtrl,
                builder: (_, __) => Transform.rotate(
                  angle: _ringCtrl.value * 2 * pi,
                  child: CustomPaint(
                    size: Size(s * 1.2, s * 1.2),
                    painter: _DashedRingPainter(color: _stateColor),
                  ),
                ),
              ),

            // Core button
            AnimatedBuilder(
              animation: _pulseAnim,
              builder: (_, __) => Container(
                width: s,
                height: s,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: const Color(0xFF061420),
                  border: Border.all(color: _stateColor.withOpacity(0.8), width: 1.5),
                  boxShadow: _isActive ? [
                    BoxShadow(
                      color: _stateColor.withOpacity(0.25 + _pulseAnim.value * 0.2),
                      blurRadius: 16 + _pulseAnim.value * 12,
                      spreadRadius: 2,
                    ),
                  ] : null,
                ),
                child: Center(child: _MicIcon(state: widget.talkback.state, color: _stateColor)),
              ),
            ),
          ]),
        ),

        const SizedBox(height: 6),
        Text(
          _stateLabel,
          style: GoogleFonts.orbitron(
            fontSize: 9,
            letterSpacing: 2,
            color: _stateColor.withOpacity(0.8),
          ),
        ),
      ]),
    );
  }
}

// ── Mic icon changes by state ──
class _MicIcon extends StatelessWidget {
  final TalkBackState state;
  final Color color;
  const _MicIcon({required this.state, required this.color});

  @override
  Widget build(BuildContext context) {
    switch (state) {
      case TalkBackState.speaking:
        return Icon(Icons.volume_up_outlined, color: color, size: 28);
      case TalkBackState.processing:
        return SizedBox(
          width: 20, height: 20,
          child: CircularProgressIndicator(color: color, strokeWidth: 1.5),
        );
      default:
        return Icon(Icons.mic_outlined, color: color, size: 28);
    }
  }
}

// ── Dashed ring painter ──
class _DashedRingPainter extends CustomPainter {
  final Color color;
  _DashedRingPainter({required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2 - 1;
    final paint  = Paint()
      ..color = color.withOpacity(0.5)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5
      ..strokeCap = StrokeCap.round;

    const dashCount = 12;
    const dashLength = 0.2;
    for (int i = 0; i < dashCount; i++) {
      final startAngle = (i / dashCount) * 2 * pi;
      canvas.drawArc(
        Rect.fromCircle(center: center, radius: radius),
        startAngle, dashLength, false, paint,
      );
    }
  }

  @override
  bool shouldRepaint(_) => false;
}


// ══════════════════════════════════════════
//  SOUND WAVE VISUALIZER
// ══════════════════════════════════════════
class SoundWaveVisualizer extends StatefulWidget {
  final TalkBackService talkback;
  final double height;
  final double width;
  const SoundWaveVisualizer({
    super.key,
    required this.talkback,
    this.height = 48,
    this.width = double.infinity,
  });

  @override
  State<SoundWaveVisualizer> createState() => _SoundWaveVisualizerState();
}

class _SoundWaveVisualizerState extends State<SoundWaveVisualizer>
    with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  final _random = Random();
  final List<double> _bars = List.generate(28, (_) => 0.1);

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 80))
      ..addListener(_updateBars)
      ..repeat();
    widget.talkback.addListener(_onStateChange);
  }

  @override
  void dispose() {
    _ctrl.dispose();
    widget.talkback.removeListener(_onStateChange);
    super.dispose();
  }

  void _onStateChange() => setState(() {});

  void _updateBars() {
    if (!mounted) return;
    final active = widget.talkback.state == TalkBackState.listening ||
                   widget.talkback.state == TalkBackState.speaking;

    setState(() {
      for (int i = 0; i < _bars.length; i++) {
        if (active) {
          // Animate towards random target
          final target = 0.1 + _random.nextDouble() * 0.9;
          _bars[i] = (_bars[i] * 0.7 + target * 0.3).clamp(0.05, 1.0);
        } else {
          // Decay to baseline
          _bars[i] = (_bars[i] * 0.85).clamp(0.05, 1.0);
        }
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final isActive = widget.talkback.state == TalkBackState.listening ||
                     widget.talkback.state == TalkBackState.speaking;
    final color = widget.talkback.state == TalkBackState.speaking
        ? const Color(0xFF00FFAA)
        : const Color(0xFF00E5FF);

    return SizedBox(
      width: widget.width,
      height: widget.height,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceEvenly,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: _bars.asMap().entries.map((e) {
          final i = e.key; final v = e.value;
          // Center bars taller
          final centerBoost = 1.0 - (((i - _bars.length / 2).abs()) / (_bars.length / 2)) * 0.4;
          final barH = (widget.height * v * centerBoost).clamp(4.0, widget.height);
          return AnimatedContainer(
            duration: const Duration(milliseconds: 80),
            width: 3,
            height: barH,
            decoration: BoxDecoration(
              color: isActive
                  ? color.withOpacity(0.4 + v * 0.6)
                  : const Color(0xFF1A4A5A).withOpacity(0.4 + v * 0.3),
              borderRadius: BorderRadius.circular(2),
              boxShadow: isActive && v > 0.5 ? [
                BoxShadow(color: color.withOpacity(v * 0.3), blurRadius: 4),
              ] : null,
            ),
          );
        }).toList(),
      ),
    );
  }
}


// ══════════════════════════════════════════
//  LIVE TRANSCRIPT BUBBLE
// ══════════════════════════════════════════
class TranscriptBubble extends StatelessWidget {
  final TalkBackService talkback;
  const TranscriptBubble({super.key, required this.talkback});

  @override
  Widget build(BuildContext context) {
    final text = talkback.state == TalkBackState.listening
        ? talkback.transcript
        : talkback.state == TalkBackState.speaking
            ? talkback.lastSpoken
            : null;

    if (text == null || text.isEmpty) return const SizedBox.shrink();

    final isUser    = talkback.state == TalkBackState.listening;
    final color     = isUser ? const Color(0xFF00E5FF) : const Color(0xFF00FFAA);
    final label     = isUser ? 'YOU' : 'JARVIS';

    return AnimatedOpacity(
      opacity: 1.0,
      duration: const Duration(milliseconds: 300),
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: color.withOpacity(0.05),
          border: Border.all(color: color.withOpacity(0.25)),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(label, style: GoogleFonts.orbitron(fontSize: 9, letterSpacing: 2, color: color.withOpacity(0.7))),
          const SizedBox(height: 4),
          Text(
            text,
            style: GoogleFonts.shareTech(
              fontSize: 14,
              color: const Color(0xFFB0EEFF),
              height: 1.5,
            ),
            maxLines: 4,
            overflow: TextOverflow.ellipsis,
          ),
        ]),
      ),
    );
  }
}

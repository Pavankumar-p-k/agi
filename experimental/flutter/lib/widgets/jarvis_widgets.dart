// lib/widgets/jarvis_widgets.dart
import 'dart:math';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../theme/app_theme.dart';

// ── HUD Ring Animation ──
class HudRing extends StatefulWidget {
  final double size;
  final Widget? child;
  const HudRing({super.key, this.size = 160, this.child});

  @override
  State<HudRing> createState() => _HudRingState();
}

class _HudRingState extends State<HudRing> with TickerProviderStateMixin {
  late AnimationController _c1, _c2, _c3, _pulse;

  @override
  void initState() {
    super.initState();
    _c1    = AnimationController(vsync: this, duration: const Duration(seconds: 12))..repeat();
    _c2    = AnimationController(vsync: this, duration: const Duration(seconds: 8))..repeat(reverse: true);
    _c3    = AnimationController(vsync: this, duration: const Duration(seconds: 5))..repeat();
    _pulse = AnimationController(vsync: this, duration: const Duration(seconds: 2))..repeat(reverse: true);
  }

  @override
  void dispose() {
    _c1.dispose(); _c2.dispose(); _c3.dispose(); _pulse.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: widget.size,
      height: widget.size,
      child: Stack(
        alignment: Alignment.center,
        children: [
          RotationTransition(
            turns: _c1,
            child: _Ring(size: widget.size, color: JarvisColors.cyan, strokeWidth: 1.5),
          ),
          RotationTransition(
            turns: Tween(begin: 0.0, end: -1.0).animate(_c2),
            child: _Ring(size: widget.size * 0.76, color: JarvisColors.blue, strokeWidth: 1),
          ),
          RotationTransition(
            turns: _c3,
            child: _Ring(size: widget.size * 0.52, color: JarvisColors.cyan, strokeWidth: 1),
          ),
          AnimatedBuilder(
            animation: _pulse,
            builder: (_, __) => Container(
              width: widget.size * 0.28,
              height: widget.size * 0.28,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: RadialGradient(colors: [
                  JarvisColors.cyan.withValues(alpha: 0.3 + _pulse.value * 0.3),
                  JarvisColors.blue.withValues(alpha: 0.1),
                ]),
                boxShadow: [
                  BoxShadow(
                    color: JarvisColors.cyan.withValues(alpha: 0.3 + _pulse.value * 0.3),
                    blurRadius: 16 + _pulse.value * 12,
                    spreadRadius: 2,
                  ),
                ],
              ),
              child: widget.child,
            ),
          ),
        ],
      ),
    );
  }
}

class _Ring extends StatelessWidget {
  final double size;
  final Color color;
  final double strokeWidth;
  const _Ring({required this.size, required this.color, required this.strokeWidth});

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      size: Size(size, size),
      painter: _RingPainter(color: color, strokeWidth: strokeWidth),
    );
  }
}

class _RingPainter extends CustomPainter {
  final Color color;
  final double strokeWidth;
  _RingPainter({required this.color, required this.strokeWidth});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2 - strokeWidth;
    final paint  = Paint()
      ..color = color.withValues(alpha: 0.25)
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth;

    canvas.drawCircle(center, radius, paint);

    // Draw 3 bright arc segments
    final arcPaint = Paint()
      ..color = color.withValues(alpha: 0.8)
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth
      ..strokeCap = StrokeCap.round;

    for (int i = 0; i < 3; i++) {
      final start = (i * 2 * pi / 3);
      canvas.drawArc(
        Rect.fromCircle(center: center, radius: radius),
        start, 0.4, false, arcPaint,
      );
    }
  }

  @override
  bool shouldRepaint(_) => false;
}


// ── JARVIS Panel (bordered card) ──
class JPanel extends StatelessWidget {
  final Widget child;
  final String? label;
  final EdgeInsets? padding;
  final Color? borderColor;
  final Color? accentColor;
  final double? width;

  const JPanel({
    super.key,
    required this.child,
    this.label,
    this.padding,
    this.borderColor,
    this.accentColor,
    this.width,
  });

  @override
  Widget build(BuildContext context) {
    final accent = accentColor ?? JarvisColors.cyan;
    return Container(
      width: width,
      decoration: BoxDecoration(
        color: JarvisColors.bgCard,
        border: Border.all(color: borderColor ?? JarvisColors.border, width: 1),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          // top accent line
          Container(
            height: 2,
            decoration: BoxDecoration(
              gradient: LinearGradient(colors: [
                Colors.transparent,
                accent,
                Colors.transparent,
              ]),
            ),
          ),
          if (label != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 10, 12, 0),
              child: Text(
                '// $label',
                style: GoogleFonts.orbitron(
                  fontSize: 10, letterSpacing: 2,
                  color: accent.withValues(alpha: 0.7),
                ),
              ),
            ),
          Padding(
            padding: padding ?? const EdgeInsets.all(12),
            child: child,
          ),
        ],
      ),
    );
  }
}


// ── Metric Bar ──
class MetricBar extends StatefulWidget {
  final String label;
  final double value;   // 0.0 – 1.0
  final Color? color;

  const MetricBar({super.key, required this.label, required this.value, this.color});

  @override
  State<MetricBar> createState() => _MetricBarState();
}

class _MetricBarState extends State<MetricBar> with SingleTickerProviderStateMixin {
  late AnimationController _c;
  late Animation<double> _anim;

  @override
  void initState() {
    super.initState();
    _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 1200));
    _anim = Tween<double>(begin: 0, end: widget.value).animate(
      CurvedAnimation(parent: _c, curve: Curves.easeOut),
    );
    _c.forward();
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final col = widget.color ?? JarvisColors.cyan;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(widget.label, style: GoogleFonts.orbitron(fontSize: 9, letterSpacing: 1.5, color: JarvisColors.textSecondary)),
            AnimatedBuilder(
              animation: _anim,
              builder: (_, __) => Text(
                '${(_anim.value * 100).toStringAsFixed(1)}%',
                style: GoogleFonts.orbitron(fontSize: 11, color: col),
              ),
            ),
          ],
        ),
        const SizedBox(height: 4),
        AnimatedBuilder(
          animation: _anim,
          builder: (_, __) => Stack(children: [
            Container(height: 3, color: JarvisColors.bgPanel),
            FractionallySizedBox(
              widthFactor: _anim.value.clamp(0, 1),
              child: Container(
                height: 3,
                decoration: BoxDecoration(
                  gradient: LinearGradient(colors: [
                    JarvisColors.blue,
                    col,
                  ]),
                  boxShadow: [BoxShadow(color: col.withValues(alpha: 0.4), blurRadius: 4)],
                ),
              ),
            ),
          ]),
        ),
      ],
    );
  }
}

// ── Metric Card ──
class MetricCard extends StatelessWidget {
  final String label;
  final String value;
  final String? sub;
  final Color? accent;
  final IconData? icon;

  const MetricCard({
    super.key,
    required this.label,
    required this.value,
    this.sub,
    this.accent,
    this.icon,
  });

  @override
  Widget build(BuildContext context) {
    final col = accent ?? JarvisColors.cyan;
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: JarvisColors.bgPanel,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: col.withValues(alpha: 0.3), width: 1),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          if (icon != null) ...[
            Icon(icon, size: 14, color: col),
            const SizedBox(width: 6),
          ],
          Expanded(child: Text(label, style: J.shareTech(9, color: JarvisColors.textSecondary))),
          Text(value, style: J.orbitron(16, weight: FontWeight.w700, color: col)),
        ]),
        if (sub != null) ...[
          const SizedBox(height: 6),
          Text(sub!, style: J.shareTech(10, color: JarvisColors.textSecondary)),
        ],
      ]),
    );
  }
}


// ── Status Dot ──
class StatusDot extends StatefulWidget {
  final bool active;
  final Color? color;
  const StatusDot({super.key, this.active = true, this.color});

  @override
  State<StatusDot> createState() => _StatusDotState();
}

class _StatusDotState extends State<StatusDot> with SingleTickerProviderStateMixin {
  late AnimationController _c;

  @override
  void initState() {
    super.initState();
    _c = AnimationController(vsync: this, duration: const Duration(seconds: 2))..repeat(reverse: true);
  }

  @override
  void dispose() { _c.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    final col = widget.color ?? (widget.active ? JarvisColors.green : JarvisColors.textSecondary);
    return AnimatedBuilder(
      animation: _c,
      builder: (_, __) => Container(
        width: 8, height: 8,
        decoration: BoxDecoration(
          color: col.withValues(alpha: widget.active ? 0.6 + _c.value * 0.4 : 0.3),
          shape: BoxShape.circle,
          boxShadow: widget.active ? [
            BoxShadow(color: col.withValues(alpha: _c.value * 0.6), blurRadius: 6, spreadRadius: 1),
          ] : null,
        ),
      ),
    );
  }
}


// ── JARVIS Button ──
class JButton extends StatelessWidget {
  final String label;
  final VoidCallback? onTap;
  final IconData? icon;
  final Color? color;
  final bool outlined;
  final bool filled;
  final double? width;

  const JButton({
    super.key,
    required this.label,
    this.onTap,
    this.icon,
    this.color,
    this.outlined = false,
    this.filled = false,
    this.width,
  });

  @override
  Widget build(BuildContext context) {
    final col = color ?? JarvisColors.cyan;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: width,
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
        decoration: BoxDecoration(
          color: filled ? col.withValues(alpha: 0.18) : (outlined ? Colors.transparent : col.withValues(alpha: 0.12)),
          border: Border.all(color: col.withValues(alpha: 0.5), width: 1),
        ),
        child: Row(
          mainAxisSize: width != null ? MainAxisSize.max : MainAxisSize.min,
          mainAxisAlignment: width != null ? MainAxisAlignment.center : MainAxisAlignment.start,
          children: [
            if (icon != null) ...[Icon(icon, size: 14, color: col), const SizedBox(width: 8)],
            Text(label, style: GoogleFonts.orbitron(fontSize: 11, letterSpacing: 2, color: col)),
          ],
        ),
      ),
    );
  }
}


// â”€â”€ Cyber Button (compact action) â”€â”€
class CyberButton extends StatelessWidget {
  final String label;
  final VoidCallback? onTap;
  final IconData? icon;
  final Color? color;
  final bool filled;
  final double? width;

  const CyberButton({
    super.key,
    required this.label,
    this.onTap,
    this.icon,
    this.color,
    this.filled = false,
    this.width,
  });

  @override
  Widget build(BuildContext context) {
    final col = color ?? J.cyan;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: width,
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
        decoration: BoxDecoration(
          color: filled ? col.withValues(alpha: 0.18) : J.bg3,
          border: Border.all(color: col.withValues(alpha: 0.6), width: 1),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            if (icon != null) ...[
              Icon(icon, size: 12, color: col),
              const SizedBox(width: 6),
            ],
            Text(label, style: J.orbitron(8, color: col, spacing: 1)),
          ],
        ),
      ),
    );
  }
}


// â”€â”€ Arc Reactor (offline AI header icon) â”€â”€
class ArcReactor extends StatelessWidget {
  final double size;
  const ArcReactor({super.key, this.size = 64});

  @override
  Widget build(BuildContext context) {
    return HudRing(size: size);
  }
}


// â”€â”€ Typing Indicator â”€â”€
class TypingIndicator extends StatefulWidget {
  const TypingIndicator({super.key});

  @override
  State<TypingIndicator> createState() => _TypingIndicatorState();
}

class _TypingIndicatorState extends State<TypingIndicator>
    with SingleTickerProviderStateMixin {
  late AnimationController _c;

  @override
  void initState() {
    super.initState();
    _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 900))
      ..repeat();
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _c,
      builder: (_, __) {
        double phase(int i) {
          final v = (_c.value + i * 0.2) % 1.0;
          return (0.3 + (1 - (v - 0.5).abs() * 2).clamp(0.0, 1.0) * 0.7);
        }

        return Row(
          mainAxisSize: MainAxisSize.min,
          children: List.generate(3, (i) => Container(
            width: 6,
            height: 6,
            margin: const EdgeInsets.only(right: 6),
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: J.cyan.withValues(alpha: phase(i)),
            ),
          )),
        );
      },
    );
  }
}


// ── Loading shimmer ──
class JLoading extends StatefulWidget {
  final double height;
  final double? width;
  const JLoading({super.key, this.height = 40, this.width});

  @override
  State<JLoading> createState() => _JLoadingState();
}

class _JLoadingState extends State<JLoading> with SingleTickerProviderStateMixin {
  late AnimationController _c;

  @override
  void initState() {
    super.initState();
    _c = AnimationController(vsync: this, duration: const Duration(seconds: 1))..repeat();
  }

  @override
  void dispose() { _c.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _c,
      builder: (_, __) => Container(
        height: widget.height,
        width: widget.width ?? double.infinity,
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment(-1 + _c.value * 3, 0),
            end: Alignment(1 + _c.value * 3, 0),
            colors: [
              JarvisColors.bgCard,
              JarvisColors.bgPanel,
              JarvisColors.border.withValues(alpha: 0.5),
              JarvisColors.bgPanel,
              JarvisColors.bgCard,
            ],
          ),
        ),
      ),
    );
  }
}


// ── Scanline overlay ──
class ScanlineOverlay extends StatelessWidget {
  final Widget child;
  const ScanlineOverlay({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    return Stack(children: [
      child,
      IgnorePointer(
        child: CustomPaint(
          size: MediaQuery.of(context).size,
          painter: _ScanlinePainter(),
        ),
      ),
    ]);
  }
}

class _ScanlinePainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = JarvisColors.cyan.withValues(alpha: 0.015)
      ..strokeWidth = 1;

    for (double y = 0; y < size.height; y += 4) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), paint);
    }
  }

  @override
  bool shouldRepaint(_) => false;
}

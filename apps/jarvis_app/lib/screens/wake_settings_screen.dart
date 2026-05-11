// lib/screens/wake_settings_screen.dart
//
// Settings screen for the background wake service.
// Shows: on/off toggle, battery status, wake count, permission guide.

import 'dart:async';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../services/wake_service.dart';
import '../services/talkback_service.dart';

const _bg      = Color(0xFF010A12);
const _bgCard  = Color(0xFF061420);
const _bgPanel = Color(0xFF0A1E2E);
const _cyan    = Color(0xFF00E5FF);
const _blue    = Color(0xFF0066FF);
const _green   = Color(0xFF00FFAA);
const _orange  = Color(0xFFFF6A00);
const _red     = Color(0xFFFF1744);
const _border  = Color(0xFF0D3348);
const _textPri = Color(0xFFB0EEFF);
const _textSec = Color(0xFF4A7A8A);


class WakeSettingsScreen extends StatefulWidget {
  final WakeService    wakeService;
  final TalkBackService? talkback;

  const WakeSettingsScreen({
    super.key,
    required this.wakeService,
    this.talkback,
  });

  @override
  State<WakeSettingsScreen> createState() => _WakeSettingsScreenState();
}

class _WakeSettingsScreenState extends State<WakeSettingsScreen>
    with TickerProviderStateMixin {

  late AnimationController _pulseCtrl;
  Timer? _refreshTimer;

  @override
  void initState() {
    super.initState();
    _pulseCtrl = AnimationController(
        vsync: this, duration: const Duration(seconds: 2))
      ..repeat(reverse: true);

    // Refresh battery status every few seconds
    _refreshTimer = Timer.periodic(const Duration(seconds: 5), (_) async {
      await widget.wakeService.isBatteryExempt();
      if (mounted) setState(() {});
    });

    widget.wakeService.addListener(_onServiceChange);
  }

  @override
  void dispose() {
    _pulseCtrl.dispose();
    _refreshTimer?.cancel();
    widget.wakeService.removeListener(_onServiceChange);
    super.dispose();
  }

  void _onServiceChange() => setState(() {});

  Future<void> _toggleService() async {
    if (widget.wakeService.serviceRunning) {
      await widget.wakeService.stop();
    } else {
      // Ask for battery exemption first if not already granted
      if (!widget.wakeService.batteryExempt) {
        await _showBatteryDialog();
      }
      await widget.wakeService.start();
    }
  }

  Future<void> _showBatteryDialog() async {
    await showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: _bgCard,
        shape: const RoundedRectangleBorder(
          side: BorderSide(color: _border),
          borderRadius: BorderRadius.zero,
        ),
        title: Text('BATTERY OPTIMIZATION',
          style: GoogleFonts.orbitron(fontSize: 13, color: _cyan, letterSpacing: 2)),
        content: Text(
          'For JARVIS to wake in the background, you need to disable battery optimization for this app.\n\nThis allows JARVIS to keep listening for your wake word even when the screen is off.',
          style: GoogleFonts.shareTech(fontSize: 13, color: _textPri, height: 1.6),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: Text('SKIP', style: GoogleFonts.orbitron(fontSize: 10, color: _textSec)),
          ),
          TextButton(
            onPressed: () async {
              Navigator.pop(ctx);
              await widget.wakeService.requestBatteryExemption();
            },
            child: Text('DISABLE OPTIMIZATION',
              style: GoogleFonts.orbitron(fontSize: 10, color: _cyan)),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final ws = widget.wakeService;

    return Scaffold(
      backgroundColor: _bg,
      appBar: AppBar(
        backgroundColor: _bg,
        elevation: 0,
        title: Text('WAKE SERVICE', style: GoogleFonts.orbitron(
          fontSize: 14, color: _cyan, letterSpacing: 4)),
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [

          // ── Big on/off toggle ──
          _BigToggleCard(
            running: ws.serviceRunning,
            onToggle: _toggleService,
            pulseCtrl: _pulseCtrl,
          ),

          const SizedBox(height: 16),

          // ── Status cards row ──
          Row(children: [
            Expanded(child: _StatCard(
              label: 'WAKE COUNT',
              value: ws.wakeCount.toString(),
              icon: Icons.notifications_active_outlined,
              color: _cyan,
            )),
            const SizedBox(width: 10),
            Expanded(child: _StatCard(
              label: 'LAST WAKE',
              value: ws.lastWakeTime == null
                ? '—'
                : _timeAgo(ws.lastWakeTime!),
              icon: Icons.schedule_outlined,
              color: _blue,
            )),
          ]),

          const SizedBox(height: 16),

          // ── Battery optimization status ──
          _SectionPanel(
            label: 'BATTERY OPTIMIZATION',
            child: Column(children: [
              Row(children: [
                _Dot(active: ws.batteryExempt, color: ws.batteryExempt ? _green : _orange),
                const SizedBox(width: 10),
                Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(
                    ws.batteryExempt ? 'UNRESTRICTED' : 'RESTRICTED',
                    style: GoogleFonts.orbitron(fontSize: 11,
                      color: ws.batteryExempt ? _green : _orange, letterSpacing: 1.5),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    ws.batteryExempt
                      ? 'JARVIS can run freely in the background'
                      : 'Android may kill JARVIS while screen is off',
                    style: GoogleFonts.shareTech(fontSize: 12, color: _textSec),
                  ),
                ])),
              ]),
              if (!ws.batteryExempt) ...[
                const SizedBox(height: 12),
                GestureDetector(
                  onTap: () => widget.wakeService.requestBatteryExemption(),
                  child: Container(
                    width: double.infinity,
                    padding: const EdgeInsets.symmetric(vertical: 11),
                    decoration: BoxDecoration(
                      border: Border.all(color: _orange.withOpacity(0.5)),
                      color: _orange.withOpacity(0.07),
                    ),
                    child: Center(child: Row(mainAxisSize: MainAxisSize.min, children: [
                      const Icon(Icons.battery_alert_outlined, color: _orange, size: 14),
                      const SizedBox(width: 8),
                      Text('FIX — DISABLE BATTERY OPTIMIZATION',
                        style: GoogleFonts.orbitron(fontSize: 9, letterSpacing: 1.5, color: _orange)),
                    ])),
                  ),
                ),
              ],
            ]),
          ),

          const SizedBox(height: 16),

          // ── Wake word info ──
          _SectionPanel(
            label: 'WAKE WORD',
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    border: Border.all(color: _cyan.withOpacity(0.4)),
                    color: _cyan.withOpacity(0.07),
                  ),
                  child: Text('"Hey Jarvis"',
                    style: GoogleFonts.orbitron(fontSize: 14, color: _cyan, fontWeight: FontWeight.w700)),
                ),
                const SizedBox(width: 12),
                Expanded(child: Text(
                  'Say this phrase at any time to activate JARVIS',
                  style: GoogleFonts.shareTech(fontSize: 12, color: _textSec),
                )),
              ]),
              const SizedBox(height: 12),
              const _Divider(),
              const SizedBox(height: 10),
              Text('Other trigger phrases:', style: GoogleFonts.orbitron(
                fontSize: 9, letterSpacing: 1.5, color: _textSec)),
              const SizedBox(height: 8),
              ...['Jarvis', 'Ok Jarvis', 'Hello Jarvis'].map((w) =>
                Padding(padding: const EdgeInsets.only(bottom: 5), child: Row(children: [
                  const Icon(Icons.chevron_right, color: _textDim, size: 14),
                  const SizedBox(width: 4),
                  Text('"$w"', style: GoogleFonts.shareTech(fontSize: 13, color: _textPri)),
                ])),
              ),
            ]),
          ),

          const SizedBox(height: 16),

          // ── How it works ──
          _SectionPanel(
            label: 'HOW IT WORKS',
            child: Column(children: _steps.asMap().entries.map((e) =>
              Padding(padding: const EdgeInsets.only(bottom: 12), child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: 22, height: 22,
                    decoration: BoxDecoration(
                      border: Border.all(color: _cyan.withOpacity(0.4)),
                      color: _cyan.withOpacity(0.07),
                      shape: BoxShape.circle,
                    ),
                    child: Center(child: Text('${e.key + 1}',
                      style: GoogleFonts.orbitron(fontSize: 9, color: _cyan))),
                  ),
                  const SizedBox(width: 10),
                  Expanded(child: Text(e.value,
                    style: GoogleFonts.shareTech(fontSize: 13, color: _textPri, height: 1.4))),
                ],
              )),
            ).toList()),
          ),

          const SizedBox(height: 16),

          // ── Manufacturer-specific guide ──
          _SectionPanel(
            label: 'PHONE-SPECIFIC SETTINGS',
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(
                'Some manufacturers have extra battery restrictions. Tap your brand:',
                style: GoogleFonts.shareTech(fontSize: 12, color: _textSec, height: 1.4),
              ),
              const SizedBox(height: 12),
              Wrap(spacing: 8, runSpacing: 8, children: _brandGuides.entries.map((e) =>
                GestureDetector(
                  onTap: () => _showBrandGuide(e.key, e.value),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
                    decoration: BoxDecoration(
                      border: Border.all(color: _border),
                      color: _bgPanel,
                    ),
                    child: Text(e.key, style: GoogleFonts.orbitron(
                      fontSize: 10, color: _textPri, letterSpacing: 1)),
                  ),
                ),
              ).toList()),
            ]),
          ),

          const SizedBox(height: 32),
        ],
      ),
    );
  }

  void _showBrandGuide(String brand, List<String> steps) {
    showDialog(context: context, builder: (ctx) => AlertDialog(
      backgroundColor: _bgCard,
      shape: const RoundedRectangleBorder(side: BorderSide(color: _border), borderRadius: BorderRadius.zero),
      title: Text('$brand SETTINGS', style: GoogleFonts.orbitron(fontSize: 12, color: _cyan, letterSpacing: 2)),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: steps.asMap().entries.map((e) => Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('${e.key + 1}. ', style: GoogleFonts.orbitron(fontSize: 10, color: _cyan)),
            Expanded(child: Text(e.value, style: GoogleFonts.shareTech(fontSize: 13, color: _textPri, height: 1.4))),
          ]),
        )).toList(),
      ),
      actions: [TextButton(
        onPressed: () => Navigator.pop(ctx),
        child: Text('GOT IT', style: GoogleFonts.orbitron(fontSize: 10, color: _cyan)),
      )],
    ));
  }

  String _timeAgo(DateTime t) {
    final diff = DateTime.now().difference(t);
    if (diff.inSeconds < 60) return '${diff.inSeconds}s ago';
    if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
    return '${diff.inHours}h ago';
  }
}


// ── Supporting widgets ──

class _BigToggleCard extends StatelessWidget {
  final bool running;
  final VoidCallback onToggle;
  final AnimationController pulseCtrl;

  const _BigToggleCard({
    required this.running,
    required this.onToggle,
    required this.pulseCtrl,
  });

  @override
  Widget build(BuildContext context) {
    final col = running ? _cyan : _textSec;
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: _bgCard,
        border: Border.all(color: running ? _cyan.withOpacity(0.3) : _border),
      ),
      child: Column(children: [
        Row(children: [
          // Animated indicator
          AnimatedBuilder(
            animation: pulseCtrl,
            builder: (_, __) => Container(
              width: 12, height: 12,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: col.withOpacity(running ? 0.5 + pulseCtrl.value * 0.5 : 0.2),
                boxShadow: running ? [
                  BoxShadow(color: _cyan.withOpacity(pulseCtrl.value * 0.4), blurRadius: 8),
                ] : null,
              ),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(
              running ? 'ALWAYS LISTENING' : 'WAKE SERVICE OFF',
              style: GoogleFonts.orbitron(fontSize: 13, color: col, letterSpacing: 2,
                fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 3),
            Text(
              running
                ? 'Listening for "Hey Jarvis" in all apps & sleep'
                : 'JARVIS will not respond in the background',
              style: GoogleFonts.shareTech(fontSize: 12, color: _textSec),
            ),
          ])),
          // Toggle switch
          Switch(
            value: running,
            onChanged: (_) => onToggle(),
            activeColor: _cyan,
            activeTrackColor: _cyan.withOpacity(0.25),
            inactiveThumbColor: _textSec,
            inactiveTrackColor: _bgPanel,
          ),
        ]),

        if (running) ...[
          const SizedBox(height: 14),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            decoration: BoxDecoration(
              color: _cyan.withOpacity(0.05),
              border: Border.all(color: _cyan.withOpacity(0.2)),
            ),
            child: Row(children: [
              const Icon(Icons.info_outline, color: _cyan, size: 14),
              const SizedBox(width: 8),
              Expanded(child: Text(
                'A persistent notification keeps the service alive. This is required by Android.',
                style: GoogleFonts.shareTech(fontSize: 11, color: _textSec, height: 1.4),
              )),
            ]),
          ),
        ],
      ]),
    );
  }
}

class _StatCard extends StatelessWidget {
  final String label, value;
  final IconData icon;
  final Color color;
  const _StatCard({required this.label, required this.value, required this.icon, required this.color});

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(14),
    decoration: BoxDecoration(color: _bgCard, border: Border.all(color: _border)),
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        Icon(icon, color: color, size: 14),
        const SizedBox(width: 6),
        Text(label, style: GoogleFonts.orbitron(fontSize: 8, letterSpacing: 1.5, color: _textSec)),
      ]),
      const SizedBox(height: 8),
      Text(value, style: GoogleFonts.orbitron(fontSize: 22, color: color, fontWeight: FontWeight.w700)),
    ]),
  );
}

class _SectionPanel extends StatelessWidget {
  final String label;
  final Widget child;
  const _SectionPanel({required this.label, required this.child});

  @override
  Widget build(BuildContext context) => Container(
    decoration: BoxDecoration(color: _bgCard, border: Border.all(color: _border)),
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Container(height: 2, decoration: const BoxDecoration(
        gradient: LinearGradient(colors: [Colors.transparent, _cyan, Colors.transparent]))),
      Padding(
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 14),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('// $label', style: GoogleFonts.orbitron(
            fontSize: 9, letterSpacing: 2, color: _cyan.withOpacity(0.7))),
          const SizedBox(height: 12),
          child,
        ]),
      ),
    ]),
  );
}

class _Dot extends StatelessWidget {
  final bool active;
  final Color color;
  const _Dot({required this.active, required this.color});

  @override
  Widget build(BuildContext context) => Container(
    width: 8, height: 8,
    decoration: BoxDecoration(
      shape: BoxShape.circle,
      color: color.withOpacity(active ? 0.9 : 0.3),
      boxShadow: active ? [BoxShadow(color: color.withOpacity(0.4), blurRadius: 6)] : null,
    ),
  );
}

class _Divider extends StatelessWidget {
  const _Divider();
  @override
  Widget build(BuildContext context) => Container(
    height: 1,
    decoration: const BoxDecoration(gradient: LinearGradient(
      colors: [Colors.transparent, _border, Colors.transparent])),
  );
}

// ── Static data ──
const _textDim = Color(0xFF1E4A5A);

const _steps = [
  'You enable the Wake Service and Android keeps a foreground process alive.',
  'Android shows a persistent notification because the OS requires it.',
  'The native service listens for voice activity using the device microphone.',
  'When the detector fires, the screen wakes and Flutter receives a wake event.',
  'You still need the assistant UI or TalkBack flow to capture the real command.',
  'Battery restrictions can still stop the service if Android puts the app to sleep.',
];

const _brandGuides = {
  'Samsung': [
    'Settings → Battery → Background usage limits',
    'Tap "Never sleeping apps"',
    'Add JARVIS to the list',
    'Also: Settings → Apps → JARVIS → Battery → Unrestricted',
  ],
  'Xiaomi': [
    'Settings → Apps → Manage apps → JARVIS',
    'Battery saver → No restrictions',
    'Also: Security app → Battery → Power saving → No restrictions for JARVIS',
    'Settings → Battery & performance → App battery saver → JARVIS → No restrictions',
  ],
  'OnePlus': [
    'Settings → Battery → Battery Optimization',
    'Find JARVIS → Don\'t Optimize',
    'Settings → Apps → JARVIS → Battery → Unrestricted',
  ],
  'Huawei': [
    'Settings → Battery → Launch → JARVIS',
    'Disable "Manage automatically"',
    'Enable Auto-launch, Secondary launch, Run in background',
  ],
  'Oppo / Realme': [
    'Settings → Battery → Power saving exclusions → Add JARVIS',
    'Settings → Apps → JARVIS → Battery usage → Allow background activity',
  ],
  'Stock Android': [
    'Settings → Apps → JARVIS → Battery',
    'Select "Unrestricted"',
    'This allows JARVIS to run freely in the background',
  ],
};

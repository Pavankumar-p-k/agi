// lib/screens/automation_screen.dart
//
// The master automation screen — quick tiles + command bar + history
// Covers: messaging, web, apps, system — all in one place

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../services/automation_service.dart';
import 'contacts_screen.dart';

const _bg      = Color(0xFF010A12);
const _bgCard  = Color(0xFF061420);
const _bgPanel = Color(0xFF0A1E2E);
const _cyan    = Color(0xFF00E5FF);
const _green   = Color(0xFF00FFAA);
const _orange  = Color(0xFFFF6A00);
const _blue    = Color(0xFF0066FF);
const _red     = Color(0xFFFF1744);
const _purple  = Color(0xFFAA00FF);
const _border  = Color(0xFF0D3348);
const _textPri = Color(0xFFB0EEFF);
const _textSec = Color(0xFF4A7A8A);
const _textDim = Color(0xFF1E4A5A);


class AutomationScreen extends StatefulWidget {
  const AutomationScreen({super.key});
  @override State<AutomationScreen> createState() => _AutomationScreenState();
}

class _AutomationScreenState extends State<AutomationScreen>
    with SingleTickerProviderStateMixin {

  final _auto = AutomationService();
  final _cmdCtrl = TextEditingController();
  final List<_CmdResult> _history = [];
  bool _running = false;
  late TabController _tabCtrl;

  @override
  void initState() {
    super.initState();
    _tabCtrl = TabController(length: 4, vsync: this);
  }

  @override
  void dispose() { _tabCtrl.dispose(); _cmdCtrl.dispose(); super.dispose(); }

  Future<void> _runCommand(String text) async {
    if (text.trim().isEmpty || _running) return;
    setState(() { _running = true; _cmdCtrl.clear(); });

    final entry = _CmdResult(command: text, time: DateTime.now());
    setState(() => _history.insert(0, entry));

    try {
      final result = await _auto.command(text);
      setState(() {
        entry.response = result['speech'] ?? result['action'] ?? 'Done.';
        entry.success  = result['success'] == true;
        entry.action   = result['action'] ?? '';
      });
    } catch (e) {
      setState(() {
        entry.response = 'Error: ${e.toString()}';
        entry.success  = false;
      });
    }
    setState(() => _running = false);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: _bg,
      appBar: AppBar(
        backgroundColor: _bg, elevation: 0,
        title: Text('AUTOMATION', style: GoogleFonts.orbitron(
          fontSize: 14, color: _cyan, letterSpacing: 4)),
        actions: [
          IconButton(
            icon: const Icon(Icons.contacts_outlined, color: _cyan, size: 20),
            onPressed: () => Navigator.push(context,
                MaterialPageRoute(builder: (_) => const ContactsScreen())),
          ),
        ],
        bottom: TabBar(
          controller: _tabCtrl,
          indicatorColor: _cyan,
          labelStyle: GoogleFonts.orbitron(fontSize: 9, letterSpacing: 1.5),
          tabs: const [
            Tab(text: 'COMMAND'),
            Tab(text: 'MESSAGE'),
            Tab(text: 'WEB'),
            Tab(text: 'SYSTEM'),
          ],
        ),
      ),
      body: TabBarView(controller: _tabCtrl, children: [
        _CommandTab(
          cmdCtrl: _cmdCtrl, running: _running,
          history: _history, onRun: _runCommand),
        _MessageTab(auto: _auto, onResult: _addResult),
        _WebTab(auto: _auto, onResult: _addResult),
        _SystemTab(auto: _auto, onResult: _addResult),
      ]),
    );
  }

  void _addResult(_CmdResult r) => setState(() => _history.insert(0, r));
}


// ════════════════════════════════════════════
//  COMMAND TAB — type or voice any command
// ════════════════════════════════════════════

class _CommandTab extends StatelessWidget {
  final TextEditingController cmdCtrl;
  final bool running;
  final List<_CmdResult> history;
  final Function(String) onRun;
  const _CommandTab({required this.cmdCtrl, required this.running,
    required this.history, required this.onRun});

  @override
  Widget build(BuildContext context) {
    return Column(children: [
      // Quick examples
      Container(
        color: _bgCard,
        padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('// EXAMPLE COMMANDS', style: GoogleFonts.orbitron(
            fontSize: 8, letterSpacing: 2, color: _textDim)),
          const SizedBox(height: 8),
          SingleChildScrollView(scrollDirection: Axis.horizontal,
            child: Row(children: [
              'Send WhatsApp to Rahul saying hello',
              'Open YouTube',
              'Play Coldplay on YouTube',
              'Search Google for Python',
              'Open Netflix',
              'Take a screenshot',
              'Volume up',
            ].map((ex) => GestureDetector(
              onTap: () { cmdCtrl.text = ex; },
              child: Container(
                margin: const EdgeInsets.only(right: 8),
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                decoration: BoxDecoration(
                  border: Border.all(color: _border),
                  color: _bgPanel,
                ),
                child: Text(ex, style: GoogleFonts.shareTech(fontSize: 11, color: _textSec)),
              ),
            )).toList()),
          ),
        ]),
      ),

      // Command input
      Padding(
        padding: const EdgeInsets.all(16),
        child: Row(children: [
          Expanded(
            child: TextField(
              controller: cmdCtrl,
              style: GoogleFonts.shareTech(color: _textPri, fontSize: 14),
              onSubmitted: onRun,
              decoration: InputDecoration(
                hintText: 'Type a command...',
                hintStyle: GoogleFonts.shareTech(color: _textDim, fontSize: 13),
                filled: true, fillColor: _bgCard,
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(4),
                    borderSide: const BorderSide(color: _border)),
                enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(4),
                    borderSide: const BorderSide(color: _border)),
                focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(4),
                    borderSide: const BorderSide(color: _cyan, width: 1.5)),
              ),
            ),
          ),
          const SizedBox(width: 10),
          GestureDetector(
            onTap: () => onRun(cmdCtrl.text),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: running ? _bgPanel : _cyan.withValues(alpha: 0.15),
                border: Border.all(color: running ? _border : _cyan.withValues(alpha: 0.6)),
              ),
              child: running
                ? const SizedBox(width: 18, height: 18,
                    child: CircularProgressIndicator(color: _cyan, strokeWidth: 1.5))
                : const Icon(Icons.play_arrow, color: _cyan, size: 20),
            ),
          ),
        ]),
      ),

      // History
      Expanded(
        child: history.isEmpty
          ? Center(child: Text('COMMAND HISTORY EMPTY',
              style: GoogleFonts.orbitron(fontSize: 10, letterSpacing: 2, color: _textDim)))
          : ListView.builder(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
              itemCount: history.length,
              itemBuilder: (_, i) => _HistoryTile(result: history[i]),
            ),
      ),
    ]);
  }
}


// ════════════════════════════════════════════
//  MESSAGE TAB — send WhatsApp / Instagram
// ════════════════════════════════════════════

class _MessageTab extends StatefulWidget {
  final AutomationService auto;
  final Function(_CmdResult) onResult;
  const _MessageTab({required this.auto, required this.onResult});
  @override State<_MessageTab> createState() => _MessageTabState();
}

class _MessageTabState extends State<_MessageTab> {
  final _contactCtrl = TextEditingController();
  final _msgCtrl     = TextEditingController();
  String _platform   = 'whatsapp';
  bool   _sending    = false;
  String? _result;
  bool?   _success;

  Future<void> _send() async {
    if (_contactCtrl.text.trim().isEmpty || _msgCtrl.text.trim().isEmpty) return;
    setState(() { _sending = true; _result = null; });
    try {
      final r = _platform == 'whatsapp'
          ? await widget.auto.sendWhatsApp(_contactCtrl.text.trim(), _msgCtrl.text.trim())
          : await widget.auto.sendInstagram(_contactCtrl.text.trim(), _msgCtrl.text.trim());
      setState(() { _result = r['success'] == true ? '✓ Sent!' : '✗ ${r['error'] ?? 'Failed'}'; _success = r['success'] == true; });
      widget.onResult(_CmdResult(
        command: '$_platform → ${_contactCtrl.text}: ${_msgCtrl.text}',
        response: _result ?? '', success: _success ?? false, time: DateTime.now(),
        action: _platform));
    } catch (e) {
      setState(() { _result = '✗ $e'; _success = false; });
    }
    setState(() => _sending = false);
  }

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(children: [
        // Platform picker
        _Panel(label: 'PLATFORM', child: Row(children: [
          _PlatChip(label: 'WHATSAPP',  icon: Icons.chat_bubble_outline,  color: _green,  selected: _platform=='whatsapp',  onTap: () => setState(() => _platform='whatsapp')),
          const SizedBox(width: 10),
          _PlatChip(label: 'INSTAGRAM', icon: Icons.photo_camera_outlined, color: _orange, selected: _platform=='instagram', onTap: () => setState(() => _platform='instagram')),
        ])),
        const SizedBox(height: 14),
        // Compose
        _Panel(label: 'COMPOSE', child: Column(children: [
          _Field2(ctrl: _contactCtrl,
            hint: _platform == 'whatsapp' ? 'Contact name or +91xxxxxxxxxx' : '@username or contact name',
            icon: Icons.person_outline),
          const SizedBox(height: 10),
          TextField(
            controller: _msgCtrl, maxLines: 4,
            style: GoogleFonts.shareTech(color: _textPri, fontSize: 13),
            decoration: InputDecoration(
              hintText: 'Type your message...',
              hintStyle: GoogleFonts.shareTech(color: _textDim),
              filled: true, fillColor: _bgPanel,
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(4), borderSide: const BorderSide(color: _border)),
              enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(4), borderSide: const BorderSide(color: _border)),
              focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(4), borderSide: const BorderSide(color: _cyan, width: 1.5)),
            ),
          ),
          if (_result != null) ...[
            const SizedBox(height: 12),
            Container(
              width: double.infinity, padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                border: Border.all(color: (_success == true ? _green : _red).withValues(alpha: 0.5)),
                color: (_success == true ? _green : _red).withValues(alpha: 0.07)),
              child: Text(_result!, style: GoogleFonts.shareTech(fontSize: 13,
                color: _success == true ? _green : _red)),
            ),
          ],
          const SizedBox(height: 14),
          SizedBox(width: double.infinity, child: _Btn(
            label: _sending ? 'SENDING...' : 'SEND MESSAGE',
            icon: Icons.send, onTap: _sending ? null : _send)),
        ])),
        const SizedBox(height: 14),
        _Panel(label: 'TIP', child: Text(
          'You can use voice too! Say:\n"Send WhatsApp to Rahul saying I will be late"\n"Instagram Priya hey are you free tonight"',
          style: GoogleFonts.shareTech(fontSize: 12, color: _textSec, height: 1.6))),
      ]),
    );
  }
}


// ════════════════════════════════════════════
//  WEB TAB
// ════════════════════════════════════════════

class _WebTab extends StatefulWidget {
  final AutomationService auto;
  final Function(_CmdResult) onResult;
  const _WebTab({required this.auto, required this.onResult});
  @override State<_WebTab> createState() => _WebTabState();
}

class _WebTabState extends State<_WebTab> {
  final _inputCtrl = TextEditingController();
  String _mode = 'url';  // url | google | youtube | maps

  Future<void> _go() async {
    final v = _inputCtrl.text.trim();
    if (v.isEmpty) return;
    switch (_mode) {
      case 'url':     widget.auto.openUrl(v.startsWith('http') ? v : 'https://$v'); break;
      case 'google':  widget.auto.googleSearch(v); break;
      case 'youtube': widget.auto.youtubeSearch(v, autoplay: false); break;
      case 'maps':    widget.auto.mapsSearch(v); break;
    }
    widget.onResult(_CmdResult(command: '$_mode: $v', response: 'Opened.', success: true,
        time: DateTime.now(), action: 'web'));
    _inputCtrl.clear();
  }

  @override
  Widget build(BuildContext context) {
    final sites = {
      'YouTube':'https://youtube.com', 'Google':'https://google.com',
      'Netflix':'https://netflix.com', 'Instagram':'https://instagram.com',
      'WhatsApp':'https://web.whatsapp.com', 'Gmail':'https://mail.google.com',
      'Amazon':'https://amazon.in', 'Flipkart':'https://flipkart.com',
      'Maps':'https://maps.google.com', 'GitHub':'https://github.com',
      'ChatGPT':'https://chat.openai.com', 'Wikipedia':'https://wikipedia.org',
      'Hotstar':'https://hotstar.com', 'Prime':'https://primevideo.com',
      'LinkedIn':'https://linkedin.com', 'Twitter':'https://x.com',
    };

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(children: [
        // Mode selector
        _Panel(label: 'MODE', child: Row(children: [
          ...[['url','URL',Icons.link],['google','GOOGLE',Icons.search],
              ['youtube','YOUTUBE',Icons.play_circle_outline],['maps','MAPS',Icons.location_on_outlined]]
            .map((m) => Expanded(child: Padding(
              padding: const EdgeInsets.only(right: 6),
              child: _ModeChip(
                label: m[1] as String,
                icon: m[2] as IconData,
                selected: _mode == m[0],
                onTap: () => setState(() => _mode = m[0] as String),
              ),
            ))),
        ])),
        const SizedBox(height: 14),
        // Input
        _Panel(label: 'INPUT', child: Row(children: [
          Expanded(child: _Field2(ctrl: _inputCtrl,
            hint: _mode == 'url' ? 'Enter URL (e.g. netflix.com)'
                : _mode == 'google' ? 'Search query...'
                : _mode == 'youtube' ? 'Video or channel name...'
                : 'Place or address...',
            icon: _mode == 'url' ? Icons.link : Icons.search)),
          const SizedBox(width: 10),
          _Btn(label: 'GO', icon: Icons.launch, onTap: _go),
        ])),
        const SizedBox(height: 14),
        // Quick sites grid
        _Panel(label: 'QUICK OPEN', child: GridView.count(
          crossAxisCount: 4, shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          crossAxisSpacing: 8, mainAxisSpacing: 8,
          childAspectRatio: 1.2,
          children: sites.entries.map((e) => GestureDetector(
            onTap: () {
              widget.auto.openUrl(e.value);
              widget.onResult(_CmdResult(command: 'Open ${e.key}',
                response: 'Opening ${e.key}', success: true,
                time: DateTime.now(), action: 'open_url'));
            },
            child: Container(
              decoration: BoxDecoration(
                color: _bgPanel, border: Border.all(color: _border)),
              child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                Icon(_siteIcon(e.key), color: _cyan, size: 18),
                const SizedBox(height: 4),
                Text(e.key, style: GoogleFonts.orbitron(fontSize: 7, color: _textSec, letterSpacing: 0.5),
                  textAlign: TextAlign.center),
              ]),
            ),
          )).toList(),
        )),
      ]),
    );
  }

  IconData _siteIcon(String name) {
    switch (name.toLowerCase()) {
      case 'youtube': return Icons.play_circle_outline;
      case 'maps':    return Icons.location_on_outlined;
      case 'gmail':   return Icons.mail_outline;
      case 'github':  return Icons.code;
      default:        return Icons.language_outlined;
    }
  }
}


// ════════════════════════════════════════════
//  SYSTEM TAB
// ════════════════════════════════════════════

class _SystemTab extends StatelessWidget {
  final AutomationService auto;
  final Function(_CmdResult) onResult;
  const _SystemTab({required this.auto, required this.onResult});

  void _exec(String label, Future<void> Function() fn, BuildContext ctx) async {
    await fn();
    onResult(_CmdResult(command: label, response: '$label executed',
        success: true, time: DateTime.now(), action: 'system'));
  }

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(children: [
        // Volume
        _Panel(label: 'VOLUME', child: Row(children: [
          Expanded(child: _SysBtn(icon: Icons.volume_down_outlined, label: 'DOWN', color: _blue,
            onTap: () => _exec('Volume Down', () => auto.setVolume('down'), context))),
          const SizedBox(width: 10),
          Expanded(child: _SysBtn(icon: Icons.volume_mute_outlined, label: 'MUTE', color: _textSec,
            onTap: () => _exec('Mute', () => auto.setVolume('mute'), context))),
          const SizedBox(width: 10),
          Expanded(child: _SysBtn(icon: Icons.volume_up_outlined, label: 'UP', color: _cyan,
            onTap: () => _exec('Volume Up', () => auto.setVolume('up'), context))),
        ])),
        const SizedBox(height: 14),
        // PC Control
        _Panel(label: 'PC CONTROL', child: Column(children: [
          Row(children: [
            Expanded(child: _SysBtn(icon: Icons.camera_alt_outlined, label: 'SCREENSHOT', color: _green,
              onTap: () async {
                final p = await auto.takeScreenshot();
                onResult(_CmdResult(command: 'Screenshot', response: 'Saved: $p',
                    success: true, time: DateTime.now(), action: 'screenshot'));
              })),
            const SizedBox(width: 10),
            Expanded(child: _SysBtn(icon: Icons.lock_outline, label: 'LOCK SCREEN', color: _orange,
              onTap: () => _exec('Lock Screen', auto.lockScreen, context))),
          ]),
          const SizedBox(height: 10),
          Row(children: [
            Expanded(child: _SysBtn(icon: Icons.bedtime_outlined, label: 'SLEEP', color: _purple,
              onTap: () => _exec('Sleep', auto.sleep, context))),
            const SizedBox(width: 10),
            Expanded(child: _SysBtn(icon: Icons.power_settings_new, label: 'SHUTDOWN', color: _red,
              onTap: () => _confirmShutdown(context))),
          ]),
        ])),
        const SizedBox(height: 14),
        // App launcher
        _Panel(label: 'APP LAUNCHER', child: Wrap(
          spacing: 8, runSpacing: 8,
          children: ['Chrome','Notepad','Calculator','Spotify','VS Code',
                     'File Explorer','Task Manager','Discord','Telegram'].map((app) =>
            GestureDetector(
              onTap: () async {
                await auto.launchApp(app);
                onResult(_CmdResult(command: 'Open $app', response: 'Opening $app',
                    success: true, time: DateTime.now(), action: 'open_app'));
              },
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
                decoration: BoxDecoration(color: _bgPanel, border: Border.all(color: _border)),
                child: Text(app, style: GoogleFonts.orbitron(fontSize: 9, color: _textPri, letterSpacing: 1)),
              ),
            ),
          ).toList(),
        )),
      ]),
    );
  }

  void _confirmShutdown(BuildContext context) {
    showDialog(context: context, builder: (ctx) => AlertDialog(
      backgroundColor: _bgCard,
      shape: const RoundedRectangleBorder(side: BorderSide(color: _border), borderRadius: BorderRadius.zero),
      title: Text('SHUTDOWN PC?', style: GoogleFonts.orbitron(fontSize: 12, color: _red, letterSpacing: 2)),
      content: Text('PC will shut down in 60 seconds.',
        style: GoogleFonts.shareTech(color: _textPri, fontSize: 13)),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx),
          child: Text('CANCEL', style: GoogleFonts.orbitron(fontSize: 10, color: _textSec))),
        TextButton(onPressed: () async {
          Navigator.pop(ctx);
          await auto.shutdown();
          onResult(_CmdResult(command: 'Shutdown', response: 'Shutting down in 60s',
              success: true, time: DateTime.now(), action: 'shutdown'));
        }, child: Text('SHUTDOWN', style: GoogleFonts.orbitron(fontSize: 10, color: _red))),
      ],
    ));
  }
}

// ── Small helper widgets ──────────────────────────────────

class _Panel extends StatelessWidget {
  final String label; final Widget child;
  const _Panel({required this.label, required this.child});

  @override
  Widget build(BuildContext context) => Container(
    decoration: BoxDecoration(color: _bgCard, border: Border.all(color: _border)),
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Container(height: 1.5, decoration: const BoxDecoration(
        gradient: LinearGradient(colors: [Colors.transparent, _cyan, Colors.transparent]))),
      Padding(
        padding: const EdgeInsets.fromLTRB(14, 10, 14, 14),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('// $label', style: GoogleFonts.orbitron(
            fontSize: 9, letterSpacing: 2, color: _cyan.withValues(alpha: 0.6))),
          const SizedBox(height: 10),
          child,
        ]),
      ),
    ]),
  );
}

class _PlatChip extends StatelessWidget {
  final String label; final IconData icon; final Color color;
  final bool selected; final VoidCallback onTap;
  const _PlatChip({required this.label, required this.icon, required this.color,
    required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) => Expanded(child: GestureDetector(
    onTap: onTap,
    child: AnimatedContainer(
      duration: const Duration(milliseconds: 200),
      padding: const EdgeInsets.symmetric(vertical: 11),
      decoration: BoxDecoration(
        color: selected ? color.withValues(alpha: 0.1) : Colors.transparent,
        border: Border.all(color: selected ? color : _border)),
      child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
        Icon(icon, size: 14, color: selected ? color : _textSec),
        const SizedBox(width: 6),
        Text(label, style: GoogleFonts.orbitron(fontSize: 9, letterSpacing: 1.5,
            color: selected ? color : _textSec)),
      ]),
    ),
  ));
}

class _ModeChip extends StatelessWidget {
  final String label; final IconData icon; final bool selected; final VoidCallback onTap;
  const _ModeChip({required this.label, required this.icon, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) => GestureDetector(
    onTap: onTap,
    child: AnimatedContainer(
      duration: const Duration(milliseconds: 150),
      padding: const EdgeInsets.symmetric(vertical: 8),
      decoration: BoxDecoration(
        color: selected ? _cyan.withValues(alpha: 0.1) : _bgPanel,
        border: Border.all(color: selected ? _cyan : _border)),
      child: Column(children: [
        Icon(icon, size: 14, color: selected ? _cyan : _textSec),
        const SizedBox(height: 3),
        Text(label, style: GoogleFonts.orbitron(fontSize: 7, letterSpacing: 1,
            color: selected ? _cyan : _textSec)),
      ]),
    ),
  );
}

class _SysBtn extends StatelessWidget {
  final IconData icon; final String label; final Color color; final VoidCallback onTap;
  const _SysBtn({required this.icon, required this.label, required this.color, required this.onTap});

  @override
  Widget build(BuildContext context) => GestureDetector(
    onTap: onTap,
    child: Container(
      padding: const EdgeInsets.symmetric(vertical: 14),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.07),
        border: Border.all(color: color.withValues(alpha: 0.35))),
      child: Column(children: [
        Icon(icon, color: color, size: 20),
        const SizedBox(height: 6),
        Text(label, style: GoogleFonts.orbitron(fontSize: 8, color: color, letterSpacing: 1.5)),
      ]),
    ),
  );
}

class _Field2 extends StatelessWidget {
  final TextEditingController ctrl; final String hint; final IconData icon;
  const _Field2({required this.ctrl, required this.hint, required this.icon});

  @override
  Widget build(BuildContext context) => TextField(
    controller: ctrl,
    style: GoogleFonts.shareTech(color: _textPri, fontSize: 14),
    decoration: InputDecoration(
      hintText: hint, hintStyle: GoogleFonts.shareTech(color: _textDim, fontSize: 13),
      prefixIcon: Icon(icon, size: 16, color: _textSec),
      filled: true, fillColor: _bgPanel,
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(4), borderSide: const BorderSide(color: _border)),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(4), borderSide: const BorderSide(color: _border)),
      focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(4), borderSide: const BorderSide(color: _cyan, width: 1.5)),
    ),
  );
}

class _Btn extends StatelessWidget {
  final String label; final IconData? icon; final VoidCallback? onTap;
  const _Btn({required this.label, this.icon, required this.onTap});

  @override
  Widget build(BuildContext context) => GestureDetector(
    onTap: onTap,
    child: Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 13),
      decoration: BoxDecoration(
        color: _cyan.withValues(alpha: onTap != null ? 0.1 : 0.04),
        border: Border.all(color: _cyan.withValues(alpha: onTap != null ? 0.5 : 0.2))),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        if (icon != null) ...[Icon(icon, color: _cyan, size: 14), const SizedBox(width: 6)],
        Text(label, style: GoogleFonts.orbitron(fontSize: 10, color: _cyan, letterSpacing: 2)),
      ]),
    ),
  );
}

class _HistoryTile extends StatelessWidget {
  final _CmdResult result;
  const _HistoryTile({required this.result});

  @override
  Widget build(BuildContext context) {
    final col = result.success ? _green : _red;
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: _bgCard, border: Border.all(color: col.withValues(alpha: 0.2))),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Icon(result.success ? Icons.check_circle_outline : Icons.error_outline,
                size: 12, color: col),
            const SizedBox(width: 6),
            Expanded(child: Text(result.command, style: GoogleFonts.shareTech(
                fontSize: 12, color: _textPri), overflow: TextOverflow.ellipsis)),
            Text(_fmt(result.time), style: GoogleFonts.orbitron(fontSize: 8, color: _textSec, letterSpacing: 1)),
          ]),
          if (result.response.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(result.response, style: GoogleFonts.shareTech(fontSize: 12, color: col.withValues(alpha: 0.8))),
          ],
        ]),
      ),
    );
  }

  String _fmt(DateTime t) =>
      '${t.hour.toString().padLeft(2,'0')}:${t.minute.toString().padLeft(2,'0')}';
}

class _CmdResult {
  final String command;
  final DateTime time;
  String response;
  bool success;
  String action;
  _CmdResult({required this.command, this.response = '', this.success = false,
    required this.time, this.action = ''});
}

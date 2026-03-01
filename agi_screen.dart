// lib/screens/agi_screen.dart
//
// JARVIS AGI DASHBOARD
// Shows the AGI brain's live activity:
//  • Live decision feed (what JARVIS is doing autonomously)
//  • Pattern visualizer (what it learned about you)
//  • Active goals + progress bars
//  • Prediction confidence display
//  • Self-improvement stats
//  • Controls (confidence threshold, DND, enable/disable)

import 'dart:async';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../services/agi_service.dart';

const _bg     = Color(0xFF010A12);
const _bgCard = Color(0xFF061420);
const _bgP    = Color(0xFF0A1E2E);
const _cyan   = Color(0xFF00E5FF);
const _green  = Color(0xFF00FFAA);
const _orange = Color(0xFFFF6A00);
const _red    = Color(0xFFFF1744);
const _purple = Color(0xFFAA00FF);
const _blue   = Color(0xFF0066FF);
const _yellow = Color(0xFFFFD600);
const _border = Color(0xFF0D3348);
const _tpri   = Color(0xFFB0EEFF);
const _tsec   = Color(0xFF4A7A8A);
const _tdim   = Color(0xFF1E4A5A);


class AGIScreen extends StatefulWidget {
  const AGIScreen({super.key});
  @override State<AGIScreen> createState() => _AGIScreenState();
}

class _AGIScreenState extends State<AGIScreen> with TickerProviderStateMixin {
  final _svc = AGIService();
  Map<String, dynamic> _status = {};
  List<dynamic> _goals = [];
  List<dynamic> _decisions = [];
  List<dynamic> _predictions = [];
  Map<String, dynamic> _patterns = {};
  bool _loading = true;
  Timer? _refreshTimer;
  late TabController _tabs;
  late AnimationController _pulseCtrl;

  @override
  void initState() {
    super.initState();
    _tabs      = TabController(length: 4, vsync: this);
    _pulseCtrl = AnimationController(vsync: this, duration: const Duration(seconds: 2))
      ..repeat(reverse: true);
    _load();
    _refreshTimer = Timer.periodic(const Duration(seconds: 10), (_) => _load());
  }

  @override
  void dispose() {
    _tabs.dispose();
    _pulseCtrl.dispose();
    _refreshTimer?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final results = await Future.wait([
        _svc.getStatus(),
        _svc.getGoals(),
        _svc.getDecisions(20),
        _svc.getPredictions(),
        _svc.getPatterns(),
      ]);
      if (!mounted) return;
      setState(() {
        _status      = results[0] as Map<String,dynamic>;
        _goals       = (results[1] as Map)['goals'] as List? ?? [];
        _decisions   = (results[2] as Map)['decisions'] as List? ?? [];
        _predictions = (results[3] as Map)['predictions'] as List? ?? [];
        _patterns    = results[4] as Map<String,dynamic>;
        _loading     = false;
      });
    } catch(e) {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final loopCount    = _status['loop_count'] ?? 0;
    final autonomous   = _status['autonomous_enabled'] ?? true;
    final activeGoals  = _status['active_goals'] ?? 0;
    final decisions    = _status['decisions_made'] ?? 0;
    final successRate  = (_status['reflector_stats'] as Map?)?.entries
        .firstWhere((e) => e.key == 'action_stats', orElse: () => MapEntry('',{})).value;

    return Scaffold(
      backgroundColor: _bg,
      appBar: AppBar(
        backgroundColor: _bg, elevation: 0,
        title: Row(mainAxisSize: MainAxisSize.min, children: [
          AnimatedBuilder(animation: _pulseCtrl, builder: (_, __) => Container(
            width: 8, height: 8,
            decoration: BoxDecoration(
              shape: BoxShape.circle, color: _cyan,
              boxShadow: [BoxShadow(color: _cyan.withOpacity(0.3 + _pulseCtrl.value * 0.5), blurRadius: 8)]),
          )),
          const SizedBox(width: 10),
          Text('AGI BRAIN', style: GoogleFonts.orbitron(
            fontSize: 14, color: _cyan, letterSpacing: 4)),
          const SizedBox(width: 8),
          if (autonomous)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
              decoration: BoxDecoration(color: _green.withOpacity(0.1),
                border: Border.all(color: _green.withOpacity(0.4))),
              child: Text('AUTO', style: GoogleFonts.orbitron(fontSize: 8, color: _green)),
            ),
        ]),
        actions: [
          IconButton(icon: const Icon(Icons.refresh_outlined, color: _tsec, size: 20),
            onPressed: _load),
        ],
        bottom: TabBar(
          controller: _tabs, indicatorColor: _cyan, indicatorWeight: 1,
          labelStyle: GoogleFonts.orbitron(fontSize: 9, letterSpacing: 1.5),
          tabs: const [
            Tab(text: 'STATUS'), Tab(text: 'GOALS'),
            Tab(text: 'PATTERNS'), Tab(text: 'DECISIONS'),
          ],
        ),
      ),

      body: _loading
        ? const Center(child: CircularProgressIndicator(color: _cyan, strokeWidth: 1.5))
        : TabBarView(controller: _tabs, children: [
            _StatusTab(status: _status, predictions: _predictions, svc: _svc, onRefresh: _load),
            _GoalsTab(goals: _goals, svc: _svc, onRefresh: _load),
            _PatternsTab(patterns: _patterns),
            _DecisionsTab(decisions: _decisions),
          ]),
    );
  }
}


// ══════════════════════════════════════════════
//  STATUS TAB
// ══════════════════════════════════════════════

class _StatusTab extends StatelessWidget {
  final Map status; final List predictions;
  final AGIService svc; final VoidCallback onRefresh;
  const _StatusTab({required this.status, required this.predictions,
    required this.svc, required this.onRefresh});

  @override
  Widget build(BuildContext context) {
    final memStats = status['memory_stats'] as Map? ?? {};
    final reflStats = status['reflector_stats'] as Map? ?? {};
    final worldState = status['world_state'] as Map? ?? {};
    final hour = worldState['mood'] ?? 'neutral';

    return ListView(padding: const EdgeInsets.all(16), children: [
      // Stats grid
      _SectionLabel('AGI METRICS'),
      GridView.count(shrinkWrap:true, physics: const NeverScrollableScrollPhysics(),
        crossAxisCount: 3, mainAxisSpacing: 8, crossAxisSpacing: 8,
        childAspectRatio: 1.4,
        children: [
          _Metric('LOOP', '${status['loop_count']??0}', _cyan),
          _Metric('GOALS', '${status['active_goals']??0}', _green),
          _Metric('DECISIONS', '${status['decisions_made']??0}', _blue),
          _Metric('EVENTS', '${memStats['events']??0}', _orange),
          _Metric('REFLECTIONS', '${memStats['reflections']??0}', _purple),
          _Metric('SUCCESS', '${((memStats['success_rate']??0)*100).round()}%', _yellow),
        ],
      ),
      const SizedBox(height: 16),

      // Live predictions
      _SectionLabel('LIVE PREDICTIONS'),
      if (predictions.isEmpty)
        _Empty('No predictions right now')
      else
        ...predictions.map((p) => _PredCard(pred: p)).toList(),

      const SizedBox(height: 16),

      // Controls
      _SectionLabel('CONTROLS'),
      _ControlPanel(status: status, svc: svc, onRefresh: onRefresh),
      const SizedBox(height: 16),

      // World state
      _SectionLabel('WORLD STATE'),
      _WorldStateCard(state: worldState),
    ]);
  }
}

class _PredCard extends StatelessWidget {
  final Map pred;
  const _PredCard({required this.pred});
  @override
  Widget build(BuildContext context) {
    final conf = (pred['confidence'] as num?)?.toDouble() ?? 0.0;
    final type = pred['type'] as String? ?? '';
    final typeColor = type == 'alert' ? _red : type == 'scheduled' ? _yellow : _cyan;
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(color: _bgCard, border: Border.all(color: _border)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Container(padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            decoration: BoxDecoration(color: typeColor.withOpacity(0.1),
              border: Border.all(color: typeColor.withOpacity(0.4))),
            child: Text(type.toUpperCase(), style: GoogleFonts.orbitron(
              fontSize: 7, color: typeColor, letterSpacing: 1.5))),
          const SizedBox(width: 8),
          Expanded(child: Text(pred['action']?.toString().toUpperCase() ?? '',
            style: GoogleFonts.orbitron(fontSize: 10, color: _tpri, letterSpacing: 1))),
          Text('${(conf*100).round()}%',
            style: GoogleFonts.orbitron(fontSize: 11, color: _green, fontWeight: FontWeight.w700)),
        ]),
        const SizedBox(height: 6),
        Text(pred['reason']?.toString() ?? '',
          style: GoogleFonts.shareTech(fontSize: 12, color: _tsec)),
        const SizedBox(height: 6),
        ClipRRect(child: LinearProgressIndicator(
          value: conf, minHeight: 2,
          backgroundColor: _bgP,
          valueColor: AlwaysStoppedAnimation(typeColor),
        )),
      ]),
    );
  }
}

class _ControlPanel extends StatefulWidget {
  final Map status; final AGIService svc; final VoidCallback onRefresh;
  const _ControlPanel({required this.status, required this.svc, required this.onRefresh});
  @override State<_ControlPanel> createState() => _ControlPanelState();
}
class _ControlPanelState extends State<_ControlPanel> {
  double _threshold = 0.65;
  bool   _dnd = false;

  @override
  void initState() {
    super.initState();
    _threshold = (widget.status['confidence_threshold'] as num?)?.toDouble() ?? 0.65;
  }

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(14),
    decoration: BoxDecoration(color: _bgCard, border: Border.all(color: _border)),
    child: Column(children: [
      Row(children: [
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('CONFIDENCE THRESHOLD', style: GoogleFonts.orbitron(fontSize: 9, color: _tsec, letterSpacing: 1.5)),
          Text('${(_threshold*100).round()}% min to auto-act',
            style: GoogleFonts.shareTech(fontSize: 11, color: _tpri)),
        ])),
        Text('${(_threshold*100).round()}%',
          style: GoogleFonts.orbitron(fontSize: 14, color: _cyan, fontWeight: FontWeight.w700)),
      ]),
      SliderTheme(
        data: SliderTheme.of(context).copyWith(
          activeTrackColor: _cyan, inactiveTrackColor: _bgP,
          thumbColor: _cyan, trackHeight: 2,
          thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 6),
          overlayShape: SliderComponentShape.noOverlay,
        ),
        child: Slider(value: _threshold, min: 0.3, max: 0.95, divisions: 13,
          onChanged: (v) => setState(() => _threshold = v),
          onChangeEnd: (v) async {
            await widget.svc.configure(confidenceThreshold: v);
            widget.onRefresh();
          }),
      ),
      const Divider(color: _border, height: 16),
      Row(children: [
        Expanded(child: Text('DO NOT DISTURB',
          style: GoogleFonts.orbitron(fontSize: 9, color: _tsec, letterSpacing: 1.5))),
        Switch(value: _dnd, onChanged: (v) async {
          setState(() => _dnd = v);
          await widget.svc.configure(dndMode: v);
          widget.onRefresh();
        }, activeColor: _red, activeTrackColor: _red.withOpacity(0.2),
          inactiveThumbColor: _tsec, inactiveTrackColor: _bgP),
      ]),
    ]),
  );
}

class _WorldStateCard extends StatelessWidget {
  final Map state;
  const _WorldStateCard({required this.state});
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(12),
    decoration: BoxDecoration(color: _bgCard, border: Border.all(color: _border)),
    child: Row(mainAxisAlignment: MainAxisAlignment.spaceAround, children: [
      _WItem('HOUR', '${state['hour'] ?? '-'}:00', _cyan),
      _WItem('MOOD', (state['mood'] ?? 'neutral').toUpperCase(), _green),
      _WItem('DAY', (state['weekend']==true) ? 'WEEKEND' : 'WEEKDAY', _orange),
    ]),
  );
}
class _WItem extends StatelessWidget {
  final String label, value; final Color color;
  const _WItem(this.label, this.value, this.color);
  @override
  Widget build(BuildContext context) => Column(children: [
    Text(label, style: GoogleFonts.orbitron(fontSize: 8, color: _tsec, letterSpacing: 1.5)),
    const SizedBox(height: 4),
    Text(value, style: GoogleFonts.orbitron(fontSize: 14, color: color, fontWeight: FontWeight.w700)),
  ]);
}


// ══════════════════════════════════════════════
//  GOALS TAB
// ══════════════════════════════════════════════

class _GoalsTab extends StatelessWidget {
  final List goals; final AGIService svc; final VoidCallback onRefresh;
  const _GoalsTab({required this.goals, required this.svc, required this.onRefresh});

  @override
  Widget build(BuildContext context) {
    final active = goals.where((g) => g['status'] == 'active').toList();
    final done   = goals.where((g) => g['status'] == 'done').toList();

    return ListView(padding: const EdgeInsets.all(16), children: [
      // Add goal button
      GestureDetector(
        onTap: () => _showAddGoal(context),
        child: Container(
          width: double.infinity, padding: const EdgeInsets.symmetric(vertical: 13),
          decoration: BoxDecoration(border: Border.all(color: _cyan.withOpacity(0.4)),
            color: _cyan.withOpacity(0.05)),
          child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
            const Icon(Icons.add, color: _cyan, size: 16),
            const SizedBox(width: 8),
            Text('SET NEW GOAL FOR JARVIS', style: GoogleFonts.orbitron(
              fontSize: 10, color: _cyan, letterSpacing: 2)),
          ]),
        ),
      ),
      const SizedBox(height: 16),

      if (active.isNotEmpty) ...[
        _SectionLabel('ACTIVE GOALS (${active.length})'),
        ...active.map((g) => _GoalCard(goal: g)).toList(),
      ],
      if (done.isNotEmpty) ...[
        _SectionLabel('COMPLETED'),
        ...done.take(5).map((g) => _GoalCard(goal: g)).toList(),
      ],
      if (goals.isEmpty)
        _Empty('No goals yet.\nTell JARVIS what to work on.'),
    ]);
  }

  void _showAddGoal(BuildContext ctx) {
    final ctrl = TextEditingController();
    showDialog(context: ctx, builder: (_) => Dialog(
      backgroundColor: _bgCard,
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(border: Border.all(color: _cyan.withOpacity(0.3))),
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('// NEW GOAL', style: GoogleFonts.orbitron(fontSize: 11, color: _cyan, letterSpacing: 2)),
          const SizedBox(height: 14),
          TextField(controller: ctrl, maxLines: 3,
            style: GoogleFonts.shareTech(color: _tpri, fontSize: 14),
            decoration: InputDecoration(
              hintText: 'e.g. "Remind me to exercise every day this week"',
              hintStyle: GoogleFonts.shareTech(color: _tdim, fontSize: 12),
              filled: true, fillColor: _bgP,
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(4),
                borderSide: const BorderSide(color: _border)),
              focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(4),
                borderSide: const BorderSide(color: _cyan, width: 1.5)),
              enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(4),
                borderSide: const BorderSide(color: _border)),
            )),
          const SizedBox(height: 14),
          Row(children: [
            Expanded(child: GestureDetector(
              onTap: () => Navigator.pop(ctx),
              child: Container(padding: const EdgeInsets.symmetric(vertical: 10),
                decoration: BoxDecoration(border: Border.all(color: _tsec.withOpacity(0.3))),
                child: Center(child: Text('CANCEL', style: GoogleFonts.orbitron(fontSize: 9, color: _tsec)))),
            )),
            const SizedBox(width: 10),
            Expanded(child: GestureDetector(
              onTap: () async {
                if (ctrl.text.isEmpty) return;
                Navigator.pop(ctx);
                await svc.createGoal(ctrl.text);
                onRefresh();
              },
              child: Container(padding: const EdgeInsets.symmetric(vertical: 10),
                decoration: BoxDecoration(color: _cyan.withOpacity(0.1),
                  border: Border.all(color: _cyan.withOpacity(0.4))),
                child: Center(child: Text('SET GOAL', style: GoogleFonts.orbitron(fontSize: 9, color: _cyan)))),
            )),
          ]),
        ]),
      ),
    ));
  }
}

class _GoalCard extends StatelessWidget {
  final Map goal;
  const _GoalCard({required this.goal});
  @override
  Widget build(BuildContext context) {
    final steps   = (goal['steps'] as List?)?.length ?? 0;
    final current = goal['current_step'] as int? ?? 0;
    final status  = goal['status'] as String? ?? 'active';
    final progress = steps > 0 ? current / steps : 0.0;
    final color   = status == 'done' ? _green : status == 'failed' ? _red : _cyan;

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(color: _bgCard, border: Border.all(color: color.withOpacity(0.25))),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Container(height: 1.5, decoration: BoxDecoration(
          gradient: LinearGradient(colors: [Colors.transparent, color, Colors.transparent]))),
        Padding(padding: const EdgeInsets.all(12), child: Column(
          crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Container(padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(color: color.withOpacity(0.1),
                  border: Border.all(color: color.withOpacity(0.4))),
                child: Text(status.toUpperCase(), style: GoogleFonts.orbitron(
                  fontSize: 7, color: color, letterSpacing: 1.5))),
              const SizedBox(width: 8),
              Expanded(child: Text(goal['description']?.toString() ?? '',
                style: GoogleFonts.shareTech(fontSize: 13, color: _tpri),
                maxLines: 2, overflow: TextOverflow.ellipsis)),
            ]),
            const SizedBox(height: 8),
            Row(children: [
              Expanded(child: ClipRRect(child: LinearProgressIndicator(
                value: progress.clamp(0.0, 1.0), minHeight: 3,
                backgroundColor: _bgP,
                valueColor: AlwaysStoppedAnimation(color)))),
              const SizedBox(width: 10),
              Text('$current / $steps', style: GoogleFonts.orbitron(fontSize: 9, color: _tsec)),
            ]),
          ],
        )),
      ]),
    );
  }
}


// ══════════════════════════════════════════════
//  PATTERNS TAB
// ══════════════════════════════════════════════

class _PatternsTab extends StatelessWidget {
  final Map patterns;
  const _PatternsTab({required this.patterns});
  @override
  Widget build(BuildContext context) {
    final pData    = patterns['patterns'] as Map? ?? {};
    final habitSum = patterns['habit_summary'] as Map? ?? {};
    final topIntents = (habitSum['top_intents'] as List?)?.take(5).toList() ?? [];
    final streak   = habitSum['streak_days'] ?? 0;
    final activeH  = habitSum['active_hours'] as List? ?? [];

    return ListView(padding: const EdgeInsets.all(16), children: [
      _SectionLabel('USAGE STREAK'),
      Container(padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(color: _bgCard, border: Border.all(color: _border)),
        child: Row(children: [
          Text('🔥', style: const TextStyle(fontSize: 32)),
          const SizedBox(width: 12),
          Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('$streak DAYS', style: GoogleFonts.orbitron(
              fontSize: 24, color: _orange, fontWeight: FontWeight.w900,
              shadows: [Shadow(color: _orange.withOpacity(0.4), blurRadius: 12)])),
            Text('consecutive usage streak', style: GoogleFonts.shareTech(fontSize: 12, color: _tsec)),
          ]),
        ]),
      ),
      const SizedBox(height: 16),

      if (topIntents.isNotEmpty) ...[
        _SectionLabel('WHAT YOU DO MOST'),
        ...topIntents.map((item) {
          final intent = (item as List?)?.first?.toString() ?? '';
          final count  = (item as List?)?.last ?? 0;
          return Container(
            margin: const EdgeInsets.only(bottom: 6),
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
            decoration: BoxDecoration(color: _bgCard, border: Border.all(color: _border)),
            child: Row(children: [
              Text(intent, style: GoogleFonts.orbitron(fontSize: 11, color: _tpri, letterSpacing: 1)),
              const Spacer(),
              Text('$count×', style: GoogleFonts.orbitron(fontSize: 11, color: _cyan)),
            ]),
          );
        }).toList(),
      ],

      const SizedBox(height: 16),
      if (activeH.isNotEmpty) ...[
        _SectionLabel('MOST ACTIVE HOURS'),
        Container(padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(color: _bgCard, border: Border.all(color: _border)),
          child: Row(mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: activeH.take(3).map((h) {
              final hour  = (h as Map)['hour'] ?? 0;
              final count = (h as Map)['count'] ?? 0;
              return Column(children: [
                Text('${hour.toString().padLeft(2,'0')}:00',
                  style: GoogleFonts.orbitron(fontSize: 14, color: _cyan, fontWeight: FontWeight.w700)),
                const SizedBox(height: 3),
                Text('$count events', style: GoogleFonts.shareTech(fontSize: 10, color: _tsec)),
              ]);
            }).toList()),
        ),
      ],
    ]);
  }
}


// ══════════════════════════════════════════════
//  DECISIONS TAB
// ══════════════════════════════════════════════

class _DecisionsTab extends StatelessWidget {
  final List decisions;
  const _DecisionsTab({required this.decisions});
  @override
  Widget build(BuildContext context) {
    if (decisions.isEmpty) return _Empty('No autonomous decisions yet.\nJARVIS will start acting soon.');
    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: decisions.length,
      itemBuilder: (_, i) {
        final d = decisions[decisions.length - 1 - i] as Map;
        final success = d['success'] == true || d['success'] == 1;
        final conf = (d['confidence'] as num?)?.toDouble() ?? 0.0;
        final ts = d['timestamp'] != null
          ? DateTime.fromMillisecondsSinceEpoch((d['timestamp'] * 1000).round())
          : null;
        return Container(
          margin: const EdgeInsets.only(bottom: 8),
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(color: _bgCard, border: Border.all(
            color: success ? _green.withOpacity(0.2) : _red.withOpacity(0.2))),
          child: Row(children: [
            Icon(success ? Icons.check_circle_outline : Icons.cancel_outlined,
              color: success ? _green : _red, size: 16),
            const SizedBox(width: 10),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(d['action']?.toString().toUpperCase() ?? '',
                style: GoogleFonts.orbitron(fontSize: 10, color: _tpri, letterSpacing: 1)),
              if (d['reasoning'] != null)
                Text(d['reasoning'].toString(),
                  style: GoogleFonts.shareTech(fontSize: 11, color: _tsec),
                  maxLines: 1, overflow: TextOverflow.ellipsis),
            ])),
            const SizedBox(width: 8),
            Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
              Text('${(conf*100).round()}%',
                style: GoogleFonts.orbitron(fontSize: 10, color: _cyan)),
              if (ts != null)
                Text('${ts.hour}:${ts.minute.toString().padLeft(2,'0')}',
                  style: GoogleFonts.shareTech(fontSize: 10, color: _tdim)),
            ]),
          ]),
        );
      },
    );
  }
}


// ── Shared helpers ────────────────────────────────────────────

class _Metric extends StatelessWidget {
  final String label, value; final Color color;
  const _Metric(this.label, this.value, this.color);
  @override
  Widget build(BuildContext context) => Container(
    decoration: BoxDecoration(color: _bgCard, border: Border.all(color: _border)),
    child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
      Text(value, style: GoogleFonts.orbitron(fontSize: 18, color: color, fontWeight: FontWeight.w900,
        shadows: [Shadow(color: color.withOpacity(0.4), blurRadius: 10)])),
      const SizedBox(height: 3),
      Text(label, style: GoogleFonts.orbitron(fontSize: 7, color: _tsec, letterSpacing: 1)),
    ]),
  );
}

class _SectionLabel extends StatelessWidget {
  final String text;
  const _SectionLabel(this.text);
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 8, top: 4),
    child: Text('// $text', style: GoogleFonts.orbitron(
      fontSize: 9, letterSpacing: 2, color: _cyan.withOpacity(0.6))),
  );
}

class _Empty extends StatelessWidget {
  final String msg;
  const _Empty(this.msg);
  @override
  Widget build(BuildContext context) => Center(
    child: Padding(padding: const EdgeInsets.all(32),
      child: Text(msg, textAlign: TextAlign.center,
        style: GoogleFonts.shareTech(fontSize: 13, color: _tsec, height: 1.8))));
}
